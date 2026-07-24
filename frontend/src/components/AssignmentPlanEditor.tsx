import { useMemo, useState } from "react";
import {
  applyAssignPlan,
  listAnnotators,
  listPlanRows,
  listProjectTasks,
  previewAssignPlan,
} from "../api/tasks";
import { useAsync } from "../hooks/useAsync";
import { DIFFICULTY_LEVELS, PRIORITY_LEVELS, type Level } from "../labels";
import type {
  AnnotationTask,
  PlanEntryInput,
  PlanEntryTask,
} from "../types/task";
import StatusBadge from "./StatusBadge";

// A <select> over 1–5 levels. Falls back to showing an unexpected stored value
// so an out-of-range number is never silently changed just by opening the row.
function LevelSelect({
  levels,
  value,
  disabled,
  onChange,
}: {
  levels: Level[];
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  const known = levels.some((l) => String(l.value) === value);
  return (
    <select
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {!known && value !== "" && <option value={value}>Level {value}</option>}
      {levels.map((l) => (
        <option key={l.value} value={String(l.value)}>
          {l.label}
        </option>
      ))}
    </select>
  );
}

// The manager-editable fields of a single planned task row. Kept as strings for
// the number/date inputs so partially-typed values don't fight the controls.
interface DraftRow {
  annotator_id: number | null;
  priority: string;
  difficulty: string;
  deadline: string; // "" == no deadline
  instructions: string;
}

// A task's own deadline wins; an unset one defaults to the project's overall
// deadline (still just a suggestion — nothing is written until the manager
// actually saves, so it stays live-synced to the project's deadline for any
// row no one has touched yet).
function toDraft(task: AnnotationTask, projectDeadline: string | null): DraftRow {
  return {
    annotator_id: task.assigned_to,
    priority: String(task.priority),
    difficulty: String(task.difficulty),
    deadline: task.deadline ?? projectDeadline ?? "",
    instructions: task.instructions ?? "",
  };
}

function rowsEqual(a: DraftRow, b: DraftRow): boolean {
  return (
    a.annotator_id === b.annotator_id &&
    a.priority === b.priority &&
    a.difficulty === b.difficulty &&
    a.deadline === b.deadline &&
    a.instructions === b.instructions
  );
}

// Turn a dirty draft row into the payload the apply endpoint expects.
function toInput(taskId: number, row: DraftRow): PlanEntryInput {
  return {
    task_id: taskId,
    annotator_id: row.annotator_id,
    priority: Number(row.priority) || 0,
    difficulty: Number(row.difficulty) || 0,
    deadline: row.deadline || null,
    instructions: row.instructions,
  };
}

// Manager-only editor for a project's whole assignment plan. Managers can
// auto-fill a balanced plan, hand-edit each task's annotator, priority,
// difficulty, deadline and instructions, then save the whole plan at once.
export default function AssignmentPlanEditor({
  projectId,
  projectDeadline = null,
  onSaved,
}: {
  projectId: number;
  projectDeadline?: string | null;
  onSaved?: () => void;
}) {
  // Ensures a task exists for every volume (creating any missing ones) and
  // lists them — no annotators proposed here, so the manager sees every
  // volume that needs a plan without first clicking "Auto-fill balanced
  // plan". That button (below) only ever proposes/fills values into rows
  // this already produced.
  const rows = useAsync(() => listPlanRows(projectId), [projectId]);
  const annotators = useAsync(listAnnotators, []);

  // `original` is the last server-known state; `draft` is what the manager is
  // editing. Both are keyed by task id.
  const [original, setOriginal] = useState<Record<number, DraftRow>>({});
  const [draft, setDraft] = useState<Record<number, DraftRow>>({});
  const [order, setOrder] = useState<number[]>([]);
  const [meta, setMeta] = useState<Record<number, AnnotationTask>>({});

  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load server rows into the draft the first time they arrive — every
  // volume already has a row here (see `listPlanRows`), so this is enough to
  // let the manager start editing without touching "Auto-fill" at all.
  const [rowsLoaded, setRowsLoaded] = useState(false);
  if (!rowsLoaded && rows.data) {
    const orig: Record<number, DraftRow> = {};
    const metaMap: Record<number, AnnotationTask> = {};
    for (const t of rows.data.entries) {
      orig[t.id] = toDraft(t, projectDeadline);
      metaMap[t.id] = t;
    }
    setOriginal(orig);
    setDraft(orig);
    setMeta(metaMap);
    setOrder(rows.data.entries.map((t) => t.id));
    setRowsLoaded(true);
  }

  const dirtyIds = useMemo(
    () => order.filter((id) => original[id] && !rowsEqual(draft[id], original[id])),
    [order, draft, original],
  );

  const patch = (id: number, changes: Partial<DraftRow>) => {
    setDraft((d) => ({ ...d, [id]: { ...d[id], ...changes } }));
    setNotice(null);
  };

  // Pull a fresh balanced plan and merge the proposed annotators into the draft
  // for tasks the manager hasn't already given someone.
  const autoFill = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const plan = await previewAssignPlan(projectId);
      const nextDraft: Record<number, DraftRow> = {};
      const nextOrig: Record<number, DraftRow> = {};
      const metaMap: Record<number, AnnotationTask> = {};
      const ids: number[] = [];
      for (const t of plan.entries) {
        const base = toDraft(t, projectDeadline);
        nextOrig[t.id] = base;
        metaMap[t.id] = t;
        ids.push(t.id);
        // Preserve any edits already in the current draft; otherwise adopt the
        // proposed annotator for unassigned tasks.
        const existing = draft[t.id];
        nextDraft[t.id] =
          existing && original[t.id] && !rowsEqual(existing, original[t.id])
            ? existing
            : { ...base, annotator_id: t.proposed_annotator_id };
      }
      setOriginal(nextOrig);
      setDraft(nextDraft);
      setMeta(metaMap);
      setOrder(ids);
      const notes: string[] = [];
      if (plan.created_tasks > 0)
        notes.push(`Created ${plan.created_tasks} new task(s).`);
      if (plan.skipped_volumes > 0)
        notes.push(`${plan.skipped_volumes} volume(s) skipped (no shape).`);
      notes.push("Review the plan below, then Save.");
      setNotice(notes.join(" "));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not build a plan.");
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (dirtyIds.length === 0) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const entries = dirtyIds.map((id) => toInput(id, draft[id]));
      const res = await applyAssignPlan(projectId, entries);
      setNotice(
        `Saved plan: ${res.updated} task(s) updated, ${res.assigned} assigned, ` +
          `${res.remaining_unassigned} still unassigned.`,
      );
      // Reload from the server so statuses/timestamps reflect the commit.
      const fresh = (await listProjectTasks(projectId)) as PlanEntryTask[];
      const orig: Record<number, DraftRow> = {};
      const metaMap: Record<number, AnnotationTask> = {};
      for (const t of fresh) {
        orig[t.id] = toDraft(t, projectDeadline);
        metaMap[t.id] = t;
      }
      setOriginal(orig);
      setDraft(orig);
      setMeta(metaMap);
      setOrder(fresh.map((t) => t.id));
      onSaved?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Saving the plan failed.");
    } finally {
      setBusy(false);
    }
  };

  const discard = () => {
    setDraft(original);
    setError(null);
    setNotice(null);
  };

  if (rows.loading && !rowsLoaded) return <p className="muted">Loading tasks…</p>;
  if (rows.error && !rowsLoaded) return <div className="error">{rows.error}</div>;

  const annotatorOptions = annotators.data ?? [];

  return (
    <>
      <div className="row spread">
        <p className="muted" style={{ margin: 0 }}>
          Every volume is listed below and ready to edit. Auto-fill proposes a
          balanced plan on top of that; every field is editable before you
          save.
        </p>
        <div className="row">
          <button className="secondary" onClick={autoFill} disabled={busy}>
            {busy ? "Working…" : "Auto-fill balanced plan"}
          </button>
          <button
            className="secondary"
            onClick={discard}
            disabled={busy || dirtyIds.length === 0}
          >
            Discard changes
          </button>
          <button onClick={save} disabled={busy || dirtyIds.length === 0}>
            {busy
              ? "Saving…"
              : dirtyIds.length > 0
                ? `Save plan (${dirtyIds.length})`
                : "Save plan"}
          </button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}
      {notice && <p className="muted">{notice}</p>}

      {order.length === 0 ? (
        <p className="muted">
          This project has no volumes yet — register data before building an
          assignment plan.
        </p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Task</th>
                <th>Volume · frames</th>
                <th>Status</th>
                <th>Assign to</th>
                <th>Priority</th>
                <th>Difficulty</th>
                <th>Deadline</th>
                <th>Instructions</th>
              </tr>
            </thead>
            <tbody>
              {order.map((id) => {
                const t = meta[id];
                const row = draft[id];
                if (!t || !row) return null;
                const dirty = original[id] && !rowsEqual(row, original[id]);
                return (
                  <tr
                    key={id}
                    style={
                      dirty
                        ? { background: "var(--warn-bg, rgba(255,196,0,0.08))" }
                        : undefined
                    }
                  >
                    <td>#{t.id}</td>
                    <td>
                      {t.volume_name} · z{t.z_start}–{t.z_end}
                    </td>
                    <td>
                      <StatusBadge value={t.status} />
                    </td>
                    <td>
                      <select
                        value={row.annotator_id ?? ""}
                        disabled={busy || annotators.loading}
                        onChange={(e) =>
                          patch(id, {
                            annotator_id: e.target.value
                              ? Number(e.target.value)
                              : null,
                          })
                        }
                      >
                        <option value="">(unassigned)</option>
                        {annotatorOptions.map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.username}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <LevelSelect
                        levels={PRIORITY_LEVELS}
                        value={row.priority}
                        disabled={busy}
                        onChange={(v) => patch(id, { priority: v })}
                      />
                    </td>
                    <td>
                      <LevelSelect
                        levels={DIFFICULTY_LEVELS}
                        value={row.difficulty}
                        disabled={busy}
                        onChange={(v) => patch(id, { difficulty: v })}
                      />
                    </td>
                    <td>
                      <input
                        type="date"
                        value={row.deadline}
                        disabled={busy}
                        onChange={(e) =>
                          patch(id, { deadline: e.target.value })
                        }
                      />
                    </td>
                    <td>
                      <input
                        type="text"
                        placeholder="Notes for annotator"
                        value={row.instructions}
                        disabled={busy}
                        onChange={(e) =>
                          patch(id, { instructions: e.target.value })
                        }
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
