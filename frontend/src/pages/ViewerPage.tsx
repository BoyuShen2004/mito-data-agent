import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getTask } from "../api/tasks";
import { submitInappTask } from "../api/submissions";
import { useAsync } from "../hooks/useAsync";
import { useAuth } from "../auth/AuthContext";
import { homePathForRole } from "../routes/roles";
import AnnotationCanvas from "../features/viewer/AnnotationCanvas";
import SliceViewer from "../features/viewer/SliceViewer";

// Same submittable-status set as TaskDetailPage's canSubmit — a task must
// actually be in annotator hands (not already submitted/approved) before
// "Submit for review" makes sense.
const SUBMITTABLE_STATUSES = ["assigned", "in_progress", "revision_requested"];

/**
 * Read-only volume viewer. Navigation lives in the global navbar only:
 * ← Back → volume page, brand / left nav → role home. No duplicate Done /
 * details buttons in the topbar.
 */
export function VolumeViewerPage() {
  const { id } = useParams();
  const volumeId = Number(id);
  return (
    <div className="editor-shell">
      <div className="editor-topbar">
        <h1>Volume viewer</h1>
      </div>
      <div className="editor-body">
        <SliceViewer volumeId={volumeId} />
      </div>
    </div>
  );
}

/**
 * Task viewer / editor.
 *
 * Topbar is for *task work* only (mode switch + submit). Leaving is owned by
 * the navbar: ← Back → task details (or history), My Tasks / Dashboard /
 * My Projects → role home. That avoids stacking Done + Task
 * details + Home + Submit as lookalike exits.
 */
export function TaskViewerPage({ editable = false }: { editable?: boolean }) {
  const { id } = useParams();
  const taskId = Number(id);
  const navigate = useNavigate();
  const { user, isManager } = useAuth();
  const { data: task, loading, error } = useAsync(() => getTask(taskId), [taskId]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  if (loading) return <div className="editor-shell"><p className="muted" style={{ padding: "1rem" }}>Loading…</p></div>;
  if (error) return <div className="editor-shell"><div className="error" style={{ margin: "1rem" }}>{error}</div></div>;
  if (!task) return null;

  const mayEdit = isManager || task.assigned_to === user?.id;
  const canSubmit = mayEdit && SUBMITTABLE_STATUSES.includes(task.status);

  const submitForReview = async () => {
    setSubmitting(true);
    setSubmitError(null);
    try {
      await submitInappTask(task.id);
      // Submit is the "I'm finished" action — land on the role home instead
      // of leaving a second Done button next to it.
      navigate(homePathForRole(user?.role));
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Submit failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="editor-shell">
      <div className="editor-topbar">
        <h1>
          {editable ? "Annotate" : "View"} · Task #{task.id}
        </h1>
        <span className="muted" style={{ fontSize: "0.78rem" }}>
          {task.project_title} · {task.source_volume || task.volume_name}
        </span>
        <span className="spacer" />
        {submitError && <span className="error">{submitError}</span>}
        {/* Far-right slot is ALWAYS the mode toggle (Annotate ↔ View only).
            Submit sits to its left in a reserved slot — never takes the
            position Annotate occupied on the View page (easy to misclick). */}
        <div className="editor-actions">
          <div className="editor-submit-slot">
            {editable && canSubmit ? (
              <button
                type="button"
                className="secondary editor-submit-btn"
                onClick={submitForReview}
                disabled={submitting}
                title="Hand this task to a manager for review, then return to your home page. Save your slice edits first — unsaved paint is not on disk."
              >
                {submitting ? "Submitting…" : "Submit for review"}
              </button>
            ) : null}
          </div>
          <div className="editor-mode-slot">
            {mayEdit &&
              (editable ? (
                <Link to={`/viewer/tasks/${task.id}`}>
                  <button type="button" className="secondary">
                    View only
                  </button>
                </Link>
              ) : (
                <Link to={`/editor/tasks/${task.id}`}>
                  <button type="button">Annotate</button>
                </Link>
              ))}
          </div>
        </div>
      </div>
      <div className="editor-body">
        <AnnotationCanvas
          taskId={task.id}
          volumeId={task.volume}
          zStart={task.z_start}
          zEnd={task.z_end}
          editable={Boolean(editable && mayEdit)}
        />
      </div>
    </div>
  );
}
