import { listMyCompletedTasks, listMyTasks } from "../api/tasks";
import { useAsync } from "../hooks/useAsync";
import TaskTable from "../components/TaskTable";

export default function AnnotatorDashboard() {
  const myTasks = useAsync(listMyTasks, []);
  const completed = useAsync(listMyCompletedTasks, []);

  return (
    <>
      <h1>My Tasks</h1>

      <div className="grid">
        <div className="card">
          <div className="muted">Active tasks</div>
          <div className="stat">{myTasks.data?.length ?? "…"}</div>
        </div>
        <div className="card">
          <div className="muted">Completed</div>
          <div className="stat">{completed.data?.length ?? "…"}</div>
        </div>
      </div>

      <div className="card">
        <h3>To annotate</h3>
        <p className="muted">
          Click <b>Annotate</b> on a task to open the editor, or <b>View</b> to
          look at the data read-only.
        </p>
        {myTasks.loading ? (
          <p className="muted">Loading…</p>
        ) : (
          <TaskTable
            tasks={myTasks.data ?? []}
            showAssignee={false}
            showProject
          />
        )}
      </div>

      <div className="card">
        <h3>Submitted &amp; completed</h3>
        {completed.loading ? (
          <p className="muted">Loading…</p>
        ) : (
          <TaskTable
            tasks={completed.data ?? []}
            showAssignee={false}
            showProject
          />
        )}
      </div>
    </>
  );
}
