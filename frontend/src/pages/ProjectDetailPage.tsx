import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getProjectSummary, updateProject } from "../api/projects";
import { listProjectVolumes } from "../api/volumes";
import { assignTasks } from "../api/tasks";
import { useAuth } from "../auth/AuthContext";
import { useAsync, type AsyncState } from "../hooks/useAsync";
import ProjectSummaryCard from "../components/ProjectSummaryCard";
import MetadataCard from "../components/MetadataCard";
import TaskAssignmentTable from "../components/TaskAssignmentTable";
import StatusBadge from "../components/StatusBadge";
import type { DatasetMetadata } from "../types/project";
import type { Volume } from "../types/volume";

const METADATA_FIELDS: { key: keyof DatasetMetadata; label: string }[] = [
  { key: "organism", label: "Organism / species" },
  { key: "tissue", label: "Tissue or organ" },
  { key: "cell_type", label: "Cell type" },
  { key: "imaging_modality", label: "Imaging modality" },
  { key: "imaging_instrument", label: "Imaging instrument / microscope" },
  { key: "experimental_condition", label: "Experimental condition" },
  { key: "sample_condition", label: "Sample condition" },
  { key: "dataset_source", label: "Dataset source" },
  { key: "publication", label: "Publication / reference" },
  { key: "description", label: "Description" },
  { key: "notes", label: "Notes" },
];

export default function ProjectDetailPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const { isManager } = useAuth();
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

  const { project, progress, workload } = summary.data;

  return (
    <>
      <div className="row spread">
        <h1>{project.dataset || project.title}</h1>
        <StatusBadge value={project.status} />
      </div>
      <p className="muted">
        {project.annotation_type.replace(/_/g, " ")} ·{" "}
        {project.annotation_target} · deadline {project.deadline ?? "—"}
      </p>

      <ProjectSummaryCard progress={progress} />

      <MetadataEditor project={project} onSaved={summary.reload} />

      <div className="card">
        <div className="row spread">
          <h3>Volumes / chunks</h3>
          <Link to="/register-data">
            <button className="secondary">+ Register more data</button>
          </Link>
        </div>
        <VolumeList volumes={volumes} isManager={isManager} />
      </div>

      {isManager && (
        <>
          <div className="card">
            <div className="row spread">
              <h3>Task assignment</h3>
              <button onClick={runAssign} disabled={assigning}>
                {assigning ? "Assigning…" : "Auto-assign (rule-based)"}
              </button>
            </div>
            {notice && <p className="muted">{notice}</p>}
            <p className="muted">
              Or manually assign / reassign each task to an annotator below.
            </p>
            <TaskAssignmentTable
              projectId={projectId}
              onChange={() => {
                summary.reload();
                volumes.reload();
              }}
            />
          </div>

          <div className="card">
            <h3>Annotator workload</h3>
            {!workload || workload.length === 0 ? (
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
        </>
      )}
    </>
  );
}

function MetadataEditor({
  project,
  onSaved,
}: {
  project: { id: number; metadata: DatasetMetadata };
  onSaved: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [values, setValues] = useState<DatasetMetadata>(project.metadata ?? {});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    const clean: DatasetMetadata = {};
    for (const [k, v] of Object.entries(values)) {
      if (typeof v === "string" && v.trim()) clean[k] = v.trim();
      else if (v && typeof v !== "string") clean[k] = v;
    }
    try {
      await updateProject(project.id, { metadata: clean });
      setEditing(false);
      onSaved();
    } catch (e2) {
      setErr(e2 instanceof Error ? e2.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  if (!editing) {
    return (
      <>
        <MetadataCard metadata={project.metadata} title="Dataset metadata" />
        <div className="row" style={{ marginTop: "-0.5rem" }}>
          <button className="secondary" onClick={() => setEditing(true)}>
            Edit metadata
          </button>
        </div>
      </>
    );
  }

  return (
    <div className="card">
      <h3>Edit dataset metadata</h3>
      {err && <div className="error">{err}</div>}
      <form onSubmit={save}>
        <div className="grid">
          {METADATA_FIELDS.map((f) => (
            <label className="field" key={f.key}>
              <span>{f.label}</span>
              <input
                value={(values[f.key] as string) ?? ""}
                onChange={(e) =>
                  setValues((v) => ({ ...v, [f.key]: e.target.value }))
                }
              />
            </label>
          ))}
        </div>
        <div className="row">
          <button type="submit" disabled={busy}>
            {busy ? "Saving…" : "Save"}
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setValues(project.metadata ?? {});
              setEditing(false);
            }}
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}

function VolumeList({
  volumes,
  isManager,
}: {
  volumes: AsyncState<Volume[]>;
  isManager: boolean;
}) {
  return (
    <div className="table-wrap">
      {volumes.loading ? (
        <p className="muted">Loading…</p>
      ) : (volumes.data ?? []).length === 0 ? (
        <p className="muted">
          No volumes registered.{" "}
          <Link to="/register-data">Register data</Link> to add chunks/crops.
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Chunk / crop</th>
              <th>Volume</th>
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
                <td>{v.chunk_id || v.name}</td>
                <td>{v.source_volume || "—"}</td>
                <td>
                  <StatusBadge value={v.label_type} />
                </td>
                <td>
                  {v.shape_z ?? "?"},{v.shape_y ?? "?"},{v.shape_x ?? "?"}
                </td>
                <td>{v.task_count}</td>
                <td>{v.status}</td>
                <td>
                  {isManager ? (
                    <Link to={`/volumes/${v.id}`}>Open</Link>
                  ) : (
                    <Link to={`/volumes/${v.id}`}>View</Link>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
