import { listMyCompletedTasks, listMyTasks } from "../api/tasks";
import { listMyPayments } from "../api/payments";
import { useAsync } from "../hooks/useAsync";
import TaskTable from "../components/TaskTable";

export default function AnnotatorDashboard() {
  const myTasks = useAsync(listMyTasks, []);
  const completed = useAsync(listMyCompletedTasks, []);
  const payments = useAsync(listMyPayments, []);

  const estEarnings = (payments.data ?? [])
    .filter((p) => p.status !== "cancelled")
    .reduce((s, p) => s + Number(p.amount), 0);

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
        <div className="card">
          <div className="muted">Estimated earnings</div>
          <div className="stat">${estEarnings.toFixed(2)}</div>
        </div>
      </div>

      <div className="card">
        <h3>Assigned to me</h3>
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
        <h3>Submitted / completed</h3>
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
