import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getProjectSummary, reviewProject } from "../api/projects";
import { deleteProjectForce, projectDependents } from "../api/datasets";
import { listProjectVolumes } from "../api/volumes";
import { useAuth } from "../auth/AuthContext";
import { useAsync, type AsyncState } from "../hooks/useAsync";
import ProjectSummaryCard from "../components/ProjectSummaryCard";
import DatasetsCard from "../components/DatasetsCard";
import DeleteButton from "../components/DeleteButton";
import ProjectEditForm from "../components/ProjectEditForm";
import AssignmentPlanEditor from "../components/AssignmentPlanEditor";
import StatusBadge from "../components/StatusBadge";
import type { Volume } from "../types/volume";


export default function ProjectDetailPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const { isManager } = useAuth();
  const navigate = useNavigate();
  const summary = useAsync(() => getProjectSummary(projectId), [projectId]);
  const volumes = useAsync(() => listProjectVolumes(projectId), [projectId]);

  const [reviewing, setReviewing] = useState(false);
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const reloadAll = () => {
    summary.reload();
    volumes.reload();
  };

  const doReview = async (reviewed: boolean) => {
    setReviewing(true);
    setNotice(null);
    try {
      await reviewProject(projectId, reviewed);
      summary.reload();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Review update failed");
    } finally {
      setReviewing(false);
    }
  };

  if (summary.loading) return <p className="muted">Loading…</p>;
  if (summary.error) return <div className="error">{summary.error}</div>;
  if (!summary.data) return null;

  const { project, progress, workload } = summary.data;
  const reviewed = project.manager_reviewed;

  return (
    <>
      <div className="row spread">
        <h1>{project.title}</h1>
        <div className="row">
          <StatusBadge value={project.status} />
          <button
            type="button"
            className="secondary"
            onClick={() => setEditing((v) => !v)}
          >
            {editing ? "Close" : "Edit project"}
          </button>
          <DeleteButton
            label={`project "${project.title}"`}
            dependents={() => projectDependents(projectId)}
            onDelete={(force) => deleteProjectForce(projectId, force)}
            onDone={() => navigate("/projects")}
          />
        </div>
      </div>
      <p className="muted">
        {project.dataset_count} dataset{project.dataset_count === 1 ? "" : "s"} ·{" "}
        {project.annotation_type.replace(/_/g, " ")} ·{" "}
        {project.annotation_target} · deadline {project.deadline ?? "—"}
      </p>

      {editing && (
        <ProjectEditForm
          project={project}
          onSaved={() => {
            setEditing(false);
            summary.reload();
          }}
        />
      )}

      <ReviewBanner
        reviewed={reviewed}
        reviewedBy={project.reviewed_by_username}
        isManager={isManager}
        busy={reviewing}
        onReview={doReview}
      />

      <ProjectSummaryCard progress={progress} />

      <div className="card">
        <div className="row spread">
          <h3>Datasets &amp; volume pairs</h3>
          <Link to={`/register-data?project=${projectId}`}>
            <button className="secondary">+ Register more data</button>
          </Link>
        </div>
        <p className="muted">
          A project holds one or more datasets; each dataset holds its image +
          mask volume pairs.
        </p>
      </div>

      <DatasetsCard
        datasets={project.datasets ?? []}
        volumes={volumes.data ?? []}
        onChanged={reloadAll}
      />

      {/* Volumes registered before datasets existed have no dataset link. */}
      {(volumes.data ?? []).some((v) => !v.dataset) && (
        <div className="card">
          <h3>Ungrouped volumes</h3>
          <p className="muted">
            These were registered before datasets existed. Open one to assign it
            to a dataset.
          </p>
          <VolumeList volumes={volumes} isManager={isManager} />
        </div>
      )}

      {isManager && (
        <>
          <div className="card">
            <h3>Task assignment plan</h3>
            {notice && <p className="muted">{notice}</p>}
            {!reviewed ? (
              <p className="muted">
                Approve this dataset above to enable assignment.
              </p>
            ) : (
              <AssignmentPlanEditor
                projectId={projectId}
                projectDeadline={project.deadline}
                onSaved={() => {
                  summary.reload();
                  volumes.reload();
                }}
              />
            )}
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

function ReviewBanner({
  reviewed,
  reviewedBy,
  isManager,
  busy,
  onReview,
}: {
  reviewed: boolean;
  reviewedBy: string;
  isManager: boolean;
  busy: boolean;
  onReview: (reviewed: boolean) => void;
}) {
  if (reviewed) {
    return (
      <div className="card">
        <div className="row spread">
          <span>
            <StatusBadge value="approved" />{" "}
            <span className="muted">
              Reviewed{reviewedBy ? ` by ${reviewedBy}` : ""} — assignment
              enabled.
            </span>
          </span>
          {isManager && (
            <button
              className="secondary"
              onClick={() => onReview(false)}
              disabled={busy}
            >
              Undo review
            </button>
          )}
        </div>
      </div>
    );
  }
  return (
    <div className="card" style={{ borderColor: "var(--warn)" }}>
      <div className="row spread">
        <span>
          <StatusBadge value="in_review" />{" "}
          <span className="muted">
            {isManager
              ? "Requester-registered data awaiting your review before assignment."
              : "Awaiting manager review before annotation can be assigned."}
          </span>
        </span>
        {isManager && (
          <button onClick={() => onReview(true)} disabled={busy}>
            {busy ? "Saving…" : "Approve & enable assignment"}
          </button>
        )}
      </div>
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
