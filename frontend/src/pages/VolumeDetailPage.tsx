import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getVolume, splitVolume, updateVolume } from "../api/volumes";
import { listProjectTasks } from "../api/tasks";
import { useAsync } from "../hooks/useAsync";
import StatusBadge from "../components/StatusBadge";
import TaskTable from "../components/TaskTable";
import type { TaskType } from "../types";

const TASK_TYPES: TaskType[] = [
  "manual_annotation",
  "prediction_proofreading",
  "final_review",
  "qc_review",
];

export default function VolumeDetailPage() {
  const { id } = useParams();
  const volumeId = Number(id);
  const vol = useAsync(() => getVolume(volumeId), [volumeId]);
  const tasks = useAsync(
    () =>
      vol.data
        ? listProjectTasks(vol.data.project).then((all) =>
            all.filter((t) => t.volume === volumeId),
          )
        : Promise.resolve([]),
    [vol.data, volumeId],
  );

  const [zStep, setZStep] = useState(16);
  const [pay, setPay] = useState("0.00");
  const [taskType, setTaskType] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const doSplit = async () => {
    setBusy(true);
    setNotice(null);
    try {
      const res = await splitVolume(volumeId, {
        z_step: zStep,
        payment_amount: pay,
        task_type: taskType || undefined,
      });
      setNotice(`Created ${res.created} task(s).`);
      vol.reload();
      tasks.reload();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Split failed");
    } finally {
      setBusy(false);
    }
  };

  if (vol.loading) return <p className="muted">Loading…</p>;
  if (vol.error) return <div className="error">{vol.error}</div>;
  if (!vol.data) return null;
  const v = vol.data;

  return (
    <>
      <div className="row spread">
        <h1>{v.name}</h1>
        <Link to={`/projects/${v.project}`}>← Back to project</Link>
      </div>

      <div className="card">
        <h3>Volume metadata</h3>
        <table>
          <tbody>
            <tr>
              <th>Image</th>
              <td>{v.image_location || "—"}</td>
            </tr>
            <tr>
              <th>Label</th>
              <td>
                {v.label_location || "—"} <StatusBadge value={v.label_type} />
              </td>
            </tr>
            <tr>
              <th>Shape (z,y,x)</th>
              <td>
                {v.shape_z ?? "?"}, {v.shape_y ?? "?"}, {v.shape_x ?? "?"}
              </td>
            </tr>
            <tr>
              <th>Voxel size (z,y,x)</th>
              <td>
                {v.voxel_size_z ?? "—"}, {v.voxel_size_y ?? "—"},{" "}
                {v.voxel_size_x ?? "—"}
              </td>
            </tr>
            <tr>
              <th>Format</th>
              <td>{v.file_format}</td>
            </tr>
            <tr>
              <th>Status</th>
              <td>{v.status}</td>
            </tr>
          </tbody>
        </table>
        <EditLabelType volume={v} onSaved={vol.reload} />
      </div>

      <div className="card">
        <h3>Split into frame-based tasks</h3>
        <p className="muted">
          Task type is inferred from the label type ({v.label_type}) unless you
          override it below.
        </p>
        {notice && <p className="muted">{notice}</p>}
        <div className="row">
          <label className="field">
            <span>z-step</span>
            <input
              type="number"
              min={1}
              value={zStep}
              onChange={(e) => setZStep(Number(e.target.value))}
            />
          </label>
          <label className="field">
            <span>Payment / task</span>
            <input value={pay} onChange={(e) => setPay(e.target.value)} />
          </label>
          <label className="field">
            <span>Task type override</span>
            <select
              value={taskType}
              onChange={(e) => setTaskType(e.target.value)}
            >
              <option value="">(infer from label)</option>
              {TASK_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </label>
        </div>
        <button onClick={doSplit} disabled={busy || !v.shape_z}>
          {busy ? "Splitting…" : "Split volume"}
        </button>
        {!v.shape_z && (
          <p className="error" style={{ marginTop: "0.75rem" }}>
            This volume has no shape_z; set it before splitting.
          </p>
        )}
      </div>

      <div className="card">
        <h3>Tasks from this volume</h3>
        {tasks.loading ? (
          <p className="muted">Loading…</p>
        ) : (
          <TaskTable tasks={tasks.data ?? []} />
        )}
      </div>
    </>
  );
}

function EditLabelType({
  volume,
  onSaved,
}: {
  volume: { id: number; label_type: string };
  onSaved: () => void;
}) {
  const [labelType, setLabelType] = useState(volume.label_type);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      const form = new FormData();
      form.append("label_type", labelType);
      await updateVolume(volume.id, form);
      onSaved();
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="row" style={{ marginTop: "0.75rem" }}>
      <label className="field" style={{ marginBottom: 0 }}>
        <span>Edit label type</span>
        <select
          value={labelType}
          onChange={(e) => setLabelType(e.target.value)}
        >
          {["none", "prediction", "proofread", "partial"].map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <button className="secondary" onClick={save} disabled={busy}>
        Save
      </button>
    </div>
  );
}
