import { Link } from "react-router-dom";
import { listProjects } from "../api/projects";
import { useAsync } from "../hooks/useAsync";
import StatusBadge from "../components/StatusBadge";

export default function RequesterDashboard() {
  const projects = useAsync(listProjects, []);
  const rows = projects.data ?? [];

  return (
    <>
      <div className="row spread">
        <h1>My Projects</h1>
        <Link to="/register-data">
          <button>+ Register data</button>
        </Link>
      </div>

      <div className="grid">
        <div className="card">
          <div className="muted">Projects</div>
          <div className="stat">{projects.data?.length ?? "…"}</div>
        </div>
        <div className="card">
          <div className="muted">Volumes / chunks</div>
          <div className="stat">
            {rows.reduce((s, p) => s + p.volume_count, 0)}
          </div>
        </div>
        <div className="card">
          <div className="muted">Tasks</div>
          <div className="stat">{rows.reduce((s, p) => s + p.task_count, 0)}</div>
        </div>
      </div>

      <div className="card">
        <h3>Registered datasets</h3>
        {projects.loading ? (
          <p className="muted">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="muted">
            No projects yet. <Link to="/register-data">Register data</Link> to
            get started.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Dataset</th>
                  <th>Status</th>
                  <th>Manager review</th>
                  <th>Volumes</th>
                  <th>Tasks</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <Link to={`/projects/${p.id}`}>
                        {p.dataset || p.title}
                      </Link>
                    </td>
                    <td>
                      <StatusBadge value={p.status} />
                    </td>
                    <td>
                      <StatusBadge
                        value={p.manager_reviewed ? "approved" : "in_review"}
                      />
                    </td>
                    <td>{p.volume_count}</td>
                    <td>{p.task_count}</td>
                    <td>{new Date(p.created_at).toLocaleDateString()}</td>
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
