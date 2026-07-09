import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getProjectSummary } from "../api/projects";
import { listProjectVolumes, registerVolume } from "../api/volumes";
import { assignTasks } from "../api/tasks";
import { useAsync, type AsyncState } from "../hooks/useAsync";
import ProjectSummaryCard from "../components/ProjectSummaryCard";
import StatusBadge from "../components/StatusBadge";
import type { LabelType } from "../types";
import type { Volume } from "../types/volume";

const LABEL_TYPES: LabelType[] = ["none", "prediction", "proofread", "partial"];
const FILE_FORMATS = ["tiff", "zarr", "hdf5", "n5", "other"];

export default function ProjectDetailPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const summary = useAsync(() => getProjectSummary(projectId), [projectId]);
  const volumes = useAsync(() => listProjectVolumes(projectId), [projectId]);

  const [assigning, setAssigning] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const runAssign = async () => {
    setAssigning(true);
    setNotice(null);
    try {
      const res = await assignTasks(projectId);
      setNotice(
        `Assigned ${res.assigned} task(s). ${res.remaining_unassigned} still unassigned.`,
      );
      summary.reload();
      volumes.reload();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Assignment failed");
    } finally {
      setAssigning(false);
    }
  };

  if (summary.loading) return <p className="muted">Loading…</p>;
  if (summary.error) return <div className="error">{summary.error}</div>;
  if (!summary.data) return null;

  const { project, progress, workload, payment } = summary.data;

  return (
    <>
      <div className="row spread">
        <h1>{project.title}</h1>
        <StatusBadge value={project.status} />
      </div>
      <p className="muted">{project.description || "No description."}</p>
      <p className="muted">
        {project.annotation_type.replace(/_/g, " ")} ·{" "}
        {project.annotation_target} · deadline {project.deadline ?? "—"}
      </p>

      <ProjectSummaryCard progress={progress} />

      <div className="card">
        <div className="row spread">
          <h3>Volumes</h3>
        </div>
        <VolumeList
          projectId={projectId}
          reload={() => {
            volumes.reload();
            summary.reload();
          }}
          volumes={volumes}
        />
      </div>

      <div className="card">
        <div className="row spread">
          <h3>Task assignment</h3>
          <button onClick={runAssign} disabled={assigning}>
            {assigning ? "Assigning…" : "Run rule-based assignment"}
          </button>
        </div>
        {notice && <p className="muted">{notice}</p>}
        <div className="row">
          <Link to={`/projects/${projectId}`}>
            <button className="secondary">Refresh</button>
          </Link>
        </div>
      </div>

      <div className="card">
        <h3>Annotator workload</h3>
        {workload.length === 0 ? (
          <p className="muted">No assigned work yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Annotator</th>
                  <th>Active</th>
                  <th>Submitted</th>
                  <th>Approved</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {workload.map((w) => (
                  <tr key={w.annotator_id}>
                    <td>{w.username}</td>
                    <td>{w.active}</td>
                    <td>{w.submitted}</td>
                    <td>{w.approved}</td>
                    <td>{w.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h3>Payment estimate</h3>
        <div className="stat">${payment.total_amount.toFixed(2)}</div>
        <p className="muted">{payment.total_records} record(s)</p>
      </div>
    </>
  );
}

function VolumeList({
  projectId,
  volumes,
  reload,
}: {
  projectId: number;
  volumes: AsyncState<Volume[]>;
  reload: () => void;
}) {
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [imagePath, setImagePath] = useState("");
  const [labelPath, setLabelPath] = useState("");
  const [labelType, setLabelType] = useState<LabelType>("none");
  const [fileFormat, setFileFormat] = useState("tiff");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const form = new FormData();
      form.append("name", name);
      form.append("image_path", imagePath);
      if (labelPath) form.append("label_path", labelPath);
      form.append("label_type", labelType);
      form.append("file_format", fileFormat);
      await registerVolume(projectId, form);
      setName("");
      setImagePath("");
      setLabelPath("");
      setShowForm(false);
      reload();
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="table-wrap">
        {volumes.loading ? (
          <p className="muted">Loading…</p>
        ) : (volumes.data ?? []).length === 0 ? (
          <p className="muted">No volumes registered.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Label</th>
                <th>Shape (z,y,x)</th>
                <th>Tasks</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {(volumes.data ?? []).map((v) => (
                <tr key={v.id}>
                  <td>{v.name}</td>
                  <td>
                    <StatusBadge value={v.label_type} />
                  </td>
                  <td>
                    {v.shape_z ?? "?"},{v.shape_y ?? "?"},{v.shape_x ?? "?"}
                  </td>
                  <td>{v.task_count}</td>
                  <td>{v.status}</td>
                  <td>
                    <Link to={`/volumes/${v.id}`}>Open</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div style={{ marginTop: "0.75rem" }}>
        <button className="secondary" onClick={() => setShowForm((s) => !s)}>
          {showForm ? "Cancel" : "+ Register volume"}
        </button>
      </div>
      {showForm && (
        <form onSubmit={submit} style={{ marginTop: "0.75rem" }}>
          {err && <div className="error">{err}</div>}
          <label className="field">
            <span>Name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label className="field">
            <span>Image path (relative to MITO_DATA_ROOT)</span>
            <input
              value={imagePath}
              onChange={(e) => setImagePath(e.target.value)}
              placeholder="demo_volume.tiff"
              required
            />
          </label>
          <label className="field">
            <span>Label path (optional)</span>
            <input
              value={labelPath}
              onChange={(e) => setLabelPath(e.target.value)}
            />
          </label>
          <div className="row">
            <label className="field" style={{ flex: 1 }}>
              <span>Label type</span>
              <select
                value={labelType}
                onChange={(e) => setLabelType(e.target.value as LabelType)}
              >
                {LABEL_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            <label className="field" style={{ flex: 1 }}>
              <span>File format</span>
              <select
                value={fileFormat}
                onChange={(e) => setFileFormat(e.target.value)}
              >
                {FILE_FORMATS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button type="submit" disabled={busy}>
            {busy ? "Registering…" : "Register"}
          </button>
        </form>
      )}
    </>
  );
}
