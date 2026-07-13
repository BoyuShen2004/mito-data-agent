import { Link } from "react-router-dom";
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
            <th></th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t) => (
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
                <Link to={`/tasks/${t.id}`}>View</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
