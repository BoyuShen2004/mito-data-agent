import { Link } from "react-router-dom";
import { listProjects } from "../api/projects";
import { listSubmissions } from "../api/submissions";
import { listPayments } from "../api/payments";
import { useAsync } from "../hooks/useAsync";
import StatusBadge from "../components/StatusBadge";

export default function ManagerDashboard() {
  const projects = useAsync(listProjects, []);
  const submissions = useAsync(() => listSubmissions("submitted"), []);
  const payments = useAsync(listPayments, []);

  const pendingPay = (payments.data ?? []).filter(
    (p) => p.status !== "paid" && p.status !== "cancelled",
  );
  const estTotal = pendingPay.reduce((s, p) => s + Number(p.amount), 0);

  return (
    <>
      <div className="row spread">
        <h1>Manager Dashboard</h1>
        <Link to="/projects">
          <button>All projects</button>
        </Link>
      </div>

      <div className="grid">
        <div className="card">
          <div className="muted">Projects</div>
          <div className="stat">{projects.data?.length ?? "…"}</div>
        </div>
        <div className="card">
          <div className="muted">Waiting for review</div>
          <div className="stat">{submissions.data?.length ?? "…"}</div>
        </div>
        <div className="card">
          <div className="muted">Estimated payable</div>
          <div className="stat">${estTotal.toFixed(2)}</div>
        </div>
      </div>

      <div className="card">
        <h3>Active projects</h3>
        {projects.loading ? (
          <p className="muted">Loading…</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Status</th>
                  <th>Volumes</th>
                  <th>Tasks</th>
                  <th>Deadline</th>
                </tr>
              </thead>
              <tbody>
                {(projects.data ?? []).map((p) => (
                  <tr key={p.id}>
                    <td>
                      <Link to={`/projects/${p.id}`}>{p.title}</Link>
                    </td>
                    <td>
                      <StatusBadge value={p.status} />
                    </td>
                    <td>{p.volume_count}</td>
                    <td>{p.task_count}</td>
                    <td>{p.deadline ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h3>Submissions waiting for review</h3>
        {(submissions.data ?? []).length === 0 ? (
          <p className="muted">Nothing to review.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Submission</th>
                  <th>Task</th>
                  <th>Annotator</th>
                  <th>QC</th>
                  <th>Submitted</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {(submissions.data ?? []).map((s) => (
                  <tr key={s.id}>
                    <td>#{s.id}</td>
                    <td>
                      {s.task_detail.volume_name} z{s.task_detail.z_start}–
                      {s.task_detail.z_end}
                    </td>
                    <td>{s.annotator_username}</td>
                    <td>
                      <StatusBadge value={s.qc_status} />
                    </td>
                    <td>{new Date(s.submitted_at).toLocaleString()}</td>
                    <td>
                      <Link to={`/submissions/${s.id}/review`}>Review</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
