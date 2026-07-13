import { useState } from "react";
import { assignTaskToAnnotator, listAnnotators, listProjectTasks } from "../api/tasks";
import { useAsync } from "../hooks/useAsync";
import type { AnnotationTask } from "../types/task";
import StatusBadge from "./StatusBadge";

// Manager-only control to manually assign / reassign each task's annotator.
// Reassigning updates the existing task in place (no duplicate is created).
export default function TaskAssignmentTable({
  projectId,
  onChange,
}: {
  projectId: number;
  onChange?: () => void;
}) {
  const tasks = useAsync(() => listProjectTasks(projectId), [projectId]);
  const annotators = useAsync(listAnnotators, []);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reassign = async (task: AnnotationTask, value: string) => {
    setSavingId(task.id);
    setError(null);
    try {
      await assignTaskToAnnotator(task.id, value ? Number(value) : null);
      tasks.reload();
      onChange?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reassignment failed");
    } finally {
      setSavingId(null);
    }
  };

  if (tasks.loading) return <p className="muted">Loading tasks…</p>;
  const rows = tasks.data ?? [];
  if (rows.length === 0) {
    return (
      <p className="muted">
        No tasks yet. Use “Auto-assign volumes to annotators” above to create a
        task per volume, or split a volume manually first.
      </p>
    );
  }

  return (
    <>
      {error && <div className="error">{error}</div>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Task</th>
              <th>Volume · frames</th>
              <th>Status</th>
              <th>Current annotator</th>
              <th>Assign to</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.id}>
                <td>#{t.id}</td>
                <td>
                  {t.volume_name} · z{t.z_start}–{t.z_end}
                </td>
                <td>
                  <StatusBadge value={t.status} />
                </td>
                <td>{t.assigned_to_username || "—"}</td>
                <td>
                  <select
                    value={t.assigned_to ?? ""}
                    disabled={savingId === t.id || annotators.loading}
                    onChange={(e) => reassign(t, e.target.value)}
                  >
                    <option value="">(unassigned)</option>
                    {(annotators.data ?? []).map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.username}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
