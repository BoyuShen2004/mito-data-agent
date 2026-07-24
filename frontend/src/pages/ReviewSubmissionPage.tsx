import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getSubmission, reviewSubmission } from "../api/submissions";
import { useAsync } from "../hooks/useAsync";
import StatusBadge from "../components/StatusBadge";
import type { ReviewDecision } from "../types";

export default function ReviewSubmissionPage() {
  const { id } = useParams();
  const submissionId = Number(id);
  const navigate = useNavigate();
  const sub = useAsync(() => getSubmission(submissionId), [submissionId]);

  const [comments, setComments] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const decide = async (decision: ReviewDecision) => {
    setBusy(true);
    setError(null);
    try {
      await reviewSubmission(submissionId, decision, comments);
      navigate("/manager");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Review failed");
    } finally {
      setBusy(false);
    }
  };

  if (sub.loading) return <p className="muted">Loading…</p>;
  if (sub.error) return <div className="error">{sub.error}</div>;
  if (!sub.data) return null;
  const s = sub.data;
  const report = s.qc_report as {
    file_size?: number;
    extension?: string;
    errors?: string[];
    warnings?: string[];
  };

  return (
    <>
      <h1>Review submission #{s.id}</h1>
      <div className="card">
        <table>
          <tbody>
            <tr>
              <th>Task</th>
              <td>
                #{s.task_detail.id} · {s.task_detail.volume_name} · z
                {s.task_detail.z_start}–{s.task_detail.z_end}
              </td>
            </tr>
            <tr>
              <th>Task status</th>
              <td>
                <StatusBadge value={s.task_detail.status} />
              </td>
            </tr>
            <tr>
              <th>Annotator</th>
              <td>{s.annotator_username}</td>
            </tr>
            <tr>
              <th>Source</th>
              <td>
                {s.source === "inapp" ? (
                  <>
                    In-app editor — no uploaded file; inspect the actual
                    painted labels before deciding:{" "}
                    <Link to={`/editor/tasks/${s.task}`}>
                      <button className="secondary">Open annotation editor</button>
                    </Link>
                  </>
                ) : (
                  "Uploaded file"
                )}
              </td>
            </tr>
            {s.source !== "inapp" && (
              <tr>
                <th>Label file</th>
                <td>{s.label_file || "—"}</td>
              </tr>
            )}
            <tr>
              <th>Notes</th>
              <td>{s.notes || "—"}</td>
            </tr>
            <tr>
              <th>QC</th>
              <td>
                <StatusBadge value={s.qc_status} /> · {report.file_size ?? 0} bytes
                · {report.extension || "?"}
              </td>
            </tr>
          </tbody>
        </table>
        {Boolean(report.errors?.length || report.warnings?.length) && (
          <ul className="muted">
            {report.errors?.map((m, i) => (
              <li key={`e${i}`}>⚠ {m}</li>
            ))}
            {report.warnings?.map((m, i) => (
              <li key={`w${i}`}>• {m}</li>
            ))}
          </ul>
        )}
      </div>

      {s.reviews.length > 0 && (
        <div className="card">
          <h3>Previous reviews</h3>
          {s.reviews.map((r) => (
            <p key={r.id}>
              <StatusBadge value={r.decision} /> by {r.reviewer_username} —{" "}
              {r.comments || "no comment"}
            </p>
          ))}
        </div>
      )}

      <div className="card">
        <h3>Decision</h3>
        {error && <div className="error">{error}</div>}
        <label className="field">
          <span>Comments</span>
          <textarea
            rows={3}
            value={comments}
            onChange={(e) => setComments(e.target.value)}
          />
        </label>
        <div className="row">
          <button onClick={() => decide("approved")} disabled={busy}>
            Approve
          </button>
          <button
            className="secondary"
            onClick={() => decide("revision_requested")}
            disabled={busy}
          >
            Request revision
          </button>
          <button
            className="danger"
            onClick={() => decide("rejected")}
            disabled={busy}
          >
            Reject
          </button>
        </div>
      </div>
    </>
  );
}
