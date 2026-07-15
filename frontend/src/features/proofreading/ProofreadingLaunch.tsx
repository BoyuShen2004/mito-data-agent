// "Open Proofreading Tool" panel for a task.
//
// Honestly distinguishes VIEWING from EDITING: a view-only provider (e.g.
// Neuroglancer) never implies edits are saved. Downloading the task descriptor
// is always offered so the existing external-annotation + upload flow works.

import { useAsync } from "../../hooks/useAsync";
import { getProofreadingInfo } from "./api";

function downloadDescriptor(info: { download: unknown }, taskId: number) {
  const blob = new Blob([JSON.stringify(info.download, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `task-${taskId}-proofreading.json`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ProofreadingLaunch({ taskId }: { taskId: number }) {
  const { data: info, loading, error } = useAsync(
    () => getProofreadingInfo(taskId),
    [taskId],
  );

  if (loading) return <p className="muted">Loading proofreading options…</p>;
  if (error) return <div className="error">{error}</div>;
  if (!info) return null;

  const canOpen = Boolean(info.url) && (info.mode === "edit" || info.mode === "view");

  return (
    <div className="card">
      <div className="row spread">
        <h3>Proofreading</h3>
        <span className="muted">provider: {info.provider}</span>
      </div>

      {info.message && <p className="muted">{info.message}</p>}

      {canOpen && (
        <p>
          <a href={info.url} target="_blank" rel="noreferrer">
            <button>
              {info.editable ? "Open editor" : "Open viewer (read-only)"}
            </button>
          </a>
          {!info.editable && (
            <span className="muted" style={{ marginLeft: 8 }}>
              View only — edit in your own tool and upload the corrected label.
            </span>
          )}
        </p>
      )}

      {info.download_available && (
        <p>
          <button
            className="secondary"
            onClick={() => downloadDescriptor(info, taskId)}
          >
            Download task descriptor
          </button>
        </p>
      )}
    </div>
  );
}
