import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  deleteVolume,
  editVolume,
  getVolume,
  splitVolume,
  updateVolume,
  volumeDependents,
} from "../api/volumes";
import DeleteButton from "../components/DeleteButton";
import type { Volume } from "../types/volume";
import { listProjectTasks } from "../api/tasks";
import { useAuth } from "../auth/AuthContext";
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
  const { isManager } = useAuth();
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
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
  const [taskType, setTaskType] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const doSplit = async () => {
    setBusy(true);
    setNotice(null);
    try {
      const res = await splitVolume(volumeId, {
        z_step: zStep,
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
        <div className="row">
          <Link to={`/viewer/volumes/${volumeId}`}>
            <button className="secondary">View data</button>
          </Link>
          <Link to={`/projects/${v.project}`}>View project →</Link>
          <button
            type="button"
            className="secondary"
            onClick={() => setEditing((e) => !e)}
          >
            {editing ? "Close" : "Edit volume"}
          </button>
          <DeleteButton
            label={`volume "${v.name}"`}
            dependents={() => volumeDependents(v.id)}
            onDelete={(force) => deleteVolume(v.id, force)}
            onDone={() => navigate(`/projects/${v.project}`)}
          />
        </div>
      </div>

      {v.dataset_name && (
        <p className="muted">
          Dataset: <strong>{v.dataset_name}</strong>
        </p>
      )}

      {editing && (
        <VolumeEditForm
          volume={v}
          onSaved={() => {
            setEditing(false);
            vol.reload();
          }}
        />
      )}

      <div className="card">
        <h3>Volume metadata</h3>
        <table>
          <tbody>
            <tr>
              <th>Volume (source)</th>
              <td>{v.source_volume || "—"}</td>
            </tr>
            <tr>
              <th>Chunk / crop</th>
              <td>{v.chunk_id || v.name}</td>
            </tr>
            <tr>
              <th>Image (HPC path)</th>
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
        {isManager && <EditLabelType volume={v} onSaved={vol.reload} />}
      </div>

      {isManager && (
        <div className="card">
          <h3>Split into frame-based tasks</h3>
          <p className="muted">
            Task type is inferred from the label type ({v.label_type}) unless
            you override it below.
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
      )}

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

/** Correct a volume after registration: its name, paths, or a wrong pairing. */
function VolumeEditForm({
  volume,
  onSaved,
}: {
  volume: Volume;
  onSaved: () => void;
}) {
  const [name, setName] = useState(volume.name);
  const [chunkId, setChunkId] = useState(volume.chunk_id);
  const [sourceVolume, setSourceVolume] = useState(volume.source_volume);
  const [imagePath, setImagePath] = useState(volume.image_path);
  const [labelPath, setLabelPath] = useState(volume.label_path);
  const [labelType, setLabelType] = useState<string>(volume.label_type);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await editVolume(volume.id, {
        name,
        chunk_id: chunkId,
        source_volume: sourceVolume,
        image_path: imagePath,
        label_path: labelPath,
        label_type: labelType,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card edit-form">
      <h3>Edit volume pair</h3>
      {error && <div className="error">{error}</div>}
      <div className="row">
        <label className="field" style={{ flex: 1 }}>
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field" style={{ flex: 1 }}>
          <span>Chunk / crop id</span>
          <input value={chunkId} onChange={(e) => setChunkId(e.target.value)} />
        </label>
        <label className="field" style={{ flex: 1 }}>
          <span>Source volume</span>
          <input
            value={sourceVolume}
            onChange={(e) => setSourceVolume(e.target.value)}
          />
        </label>
      </div>
      <label className="field">
        <span>Image path</span>
        <input value={imagePath} onChange={(e) => setImagePath(e.target.value)} />
      </label>
      <label className="field">
        <span>Mask / label path — repoint this to fix a wrong pairing</span>
        <input value={labelPath} onChange={(e) => setLabelPath(e.target.value)} />
      </label>
      <label className="field" style={{ maxWidth: "16rem" }}>
        <span>Label type</span>
        <select value={labelType} onChange={(e) => setLabelType(e.target.value)}>
          {["prediction", "proofread", "partial", "none"].map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <button type="button" onClick={save} disabled={busy}>
        {busy ? "Saving…" : "Save volume"}
      </button>
    </div>
  );
}
