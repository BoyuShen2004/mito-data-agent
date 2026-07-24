import { Link } from "react-router-dom";
import { listProjects } from "../api/projects";
import { listSubmissions } from "../api/submissions";
import { useAsync } from "../hooks/useAsync";
import StatusBadge from "../components/StatusBadge";

export default function ManagerDashboard() {
  const projects = useAsync(listProjects, []);
  const submissions = useAsync(() => listSubmissions("submitted"), []);

  const totalVolumes = (projects.data ?? []).reduce(
    (s, p) => s + p.volume_count,
    0,
  );
  const pendingReview = (projects.data ?? []).filter((p) => !p.manager_reviewed);

  return (
    <>
      <div className="row spread">
        <h1>Manager Dashboard</h1>
        <div className="row">
          <Link to="/projects/new">
            <button>+ New project</button>
          </Link>
          <Link to="/register-data">
            <button className="secondary">Register data</button>
          </Link>
          <Link to="/projects">
            <button className="secondary">All projects</button>
          </Link>
        </div>
      </div>

      <div className="grid">
        <div className="card">
          <div className="muted">Projects</div>
          <div className="stat">{projects.data?.length ?? "…"}</div>
        </div>
        <div className="card">
          <div className="muted">Volumes / chunks</div>
          <div className="stat">{projects.data ? totalVolumes : "…"}</div>
        </div>
        <div className="card">
          <div className="muted">Datasets to approve</div>
          <div className="stat">{projects.data ? pendingReview.length : "…"}</div>
        </div>
        <div className="card">
          <div className="muted">Submissions to review</div>
          <div className="stat">{submissions.data?.length ?? "…"}</div>
        </div>
      </div>

      {pendingReview.length > 0 && (
        <div className="card" style={{ borderColor: "var(--warn)" }}>
          <h3>Datasets awaiting your review</h3>
          <p className="muted">
            Requester-registered data must be reviewed before it can be
            assigned.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Dataset</th>
                  <th>Registered by</th>
                  <th>Volumes</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {pendingReview.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <Link to={`/projects/${p.id}`}>
                        {p.dataset || p.title}
                      </Link>
                    </td>
                    <td>{p.created_by_username || "—"}</td>
                    <td>{p.volume_count}</td>
                    <td>
                      <Link to={`/projects/${p.id}`}>Review</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

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
