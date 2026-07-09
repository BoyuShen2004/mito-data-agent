import { useState } from "react";
import { Link } from "react-router-dom";
import { createProject, listProjects } from "../api/projects";
import { useAsync } from "../hooks/useAsync";
import StatusBadge from "../components/StatusBadge";

const ANNOTATION_TYPES = [
  "instance_segmentation",
  "semantic_segmentation",
  "proofreading",
];

export default function ProjectListPage() {
  const { data, loading, error, reload } = useAsync(listProjects, []);
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [annotationType, setAnnotationType] = useState(ANNOTATION_TYPES[0]);
  const [deadline, setDeadline] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      await createProject({
        title,
        description,
        annotation_type: annotationType,
        deadline: deadline || null,
      });
      setTitle("");
      setDescription("");
      setDeadline("");
      setShowForm(false);
      reload();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="row spread">
        <h1>Projects</h1>
        <button onClick={() => setShowForm((s) => !s)}>
          {showForm ? "Cancel" : "+ New project"}
        </button>
      </div>

      {showForm && (
        <div className="card">
          <h3>Create project</h3>
          {formError && <div className="error">{formError}</div>}
          <form onSubmit={submit}>
            <label className="field">
              <span>Title</span>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
            </label>
            <label className="field">
              <span>Description</span>
              <textarea
                value={description}
                rows={2}
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>
            <div className="row">
              <label className="field" style={{ flex: 1 }}>
                <span>Annotation type</span>
                <select
                  value={annotationType}
                  onChange={(e) => setAnnotationType(e.target.value)}
                >
                  {ANNOTATION_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field" style={{ flex: 1 }}>
                <span>Deadline</span>
                <input
                  type="date"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                />
              </label>
            </div>
            <button type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create"}
            </button>
          </form>
        </div>
      )}

      {error && <div className="error">{error}</div>}
      <div className="card">
        {loading ? (
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
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {(data ?? []).map((p) => (
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
