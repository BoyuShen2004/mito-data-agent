import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import type { AnnotationTask } from "../types/task";
import StatusBadge from "./StatusBadge";

interface Props {
  tasks: AnnotationTask[];
  showAssignee?: boolean;
  showProject?: boolean;
}

export default function TaskTable({
  tasks,
  showAssignee = true,
  showProject = false,
}: Props) {
  const { user, isManager } = useAuth();

  if (tasks.length === 0) {
    return <p className="muted">No tasks.</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            {showProject && <th>Project</th>}
            <th>Volume</th>
            <th>Frames (z)</th>
            <th>Type</th>
            <th>Status</th>
            {showAssignee && <th>Assignee</th>}
            <th>Details</th>
            <th>Open</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t) => {
            // Managers and the assigned annotator get both a View and an
            // Annotate/proofread button (matches backend can_edit_task —
            // no status restriction: proofreading is expected to happen
            // after submission too). Requesters and anyone else get View only.
            const canEdit = isManager || t.assigned_to === user?.id;
            return (
              <tr key={t.id}>
                <td>#{t.id}</td>
                {showProject && <td>{t.project_title}</td>}
                <td>{t.volume_name}</td>
                <td>
                  {t.z_start}–{t.z_end}
                </td>
                <td>{t.task_type.replace(/_/g, " ")}</td>
                <td>
                  <StatusBadge value={t.status} />
                </td>
                {showAssignee && <td>{t.assigned_to_username || "—"}</td>}
                <td>
                  <Link to={`/tasks/${t.id}`}>Details</Link>
                </td>
                <td>
                  <div className="task-actions">
                    <Link to={`/viewer/tasks/${t.id}`}>
                      <button type="button" className="secondary">
                        View
                      </button>
                    </Link>
                    {canEdit && (
                      <Link to={`/editor/tasks/${t.id}`}>
                        <button type="button">Annotate</button>
                      </Link>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
