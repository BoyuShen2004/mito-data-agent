import { Link, useParams } from "react-router-dom";
import { getTask } from "../api/tasks";
import { useAsync } from "../hooks/useAsync";
import { useAuth } from "../auth/AuthContext";
import StatusBadge from "../components/StatusBadge";
import MetadataCard from "../components/MetadataCard";

export default function TaskDetailPage() {
  const { id } = useParams();
  const taskId = Number(id);
  const { user, isManager } = useAuth();
  const { data: t, loading, error } = useAsync(() => getTask(taskId), [taskId]);

  if (loading) return <p className="muted">Loading…</p>;
  if (error) return <div className="error">{error}</div>;
  if (!t) return null;

  const mine = t.assigned_to === user?.id;
  const canSubmit =
    mine &&
    ["assigned", "in_progress", "revision_requested"].includes(t.status);

  return (
    <>
      <div className="row spread">
        <h1>Task #{t.id}</h1>
        <StatusBadge value={t.status} />
      </div>

      <div className="card">
        <table>
          <tbody>
            <tr>
              <th>Project</th>
              <td>
                {isManager ? (
                  <Link to={`/projects/${t.project}`}>{t.project_title}</Link>
                ) : (
                  t.project_title
                )}
              </td>
            </tr>
            <tr>
              <th>Dataset</th>
              <td>{t.dataset || "—"}</td>
            </tr>
            <tr>
              <th>Volume</th>
              <td>
                {t.source_volume || "—"}
                {t.volume_name ? ` · chunk: ${t.volume_name}` : ""}
              </td>
            </tr>
            <tr>
              <th>Task type</th>
              <td>{t.task_type.replace(/_/g, " ")}</td>
            </tr>
            <tr>
              <th>Assigned to</th>
              <td>{t.assigned_to_username || "—"}</td>
            </tr>
            <tr>
              <th>Frames</th>
              <td>
                z [{t.z_start}, {t.z_end}), y [{t.y_start}, {t.y_end}), x [
                {t.x_start}, {t.x_end})
              </td>
            </tr>
            <tr>
              <th>Image path</th>
              <td>{t.image_location || "—"}</td>
            </tr>
            <tr>
              <th>Existing label</th>
              <td>{t.label_location || "—"}</td>
            </tr>
            <tr>
              <th>Deadline</th>
              <td>{t.deadline ?? "—"}</td>
            </tr>
            <tr>
              <th>Instructions</th>
              <td>{t.instructions || "—"}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <MetadataCard metadata={t.project_metadata} />

      {canSubmit && (
        <div className="card">
          <p>
            Download the image/label externally, complete the annotation, then
            upload your label file.
          </p>
          <Link to={`/tasks/${t.id}/submit`}>
            <button>Submit completed label</button>
          </Link>
        </div>
      )}
    </>
  );
}
