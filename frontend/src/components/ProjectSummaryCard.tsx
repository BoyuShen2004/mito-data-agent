import type { ProjectProgress } from "../types/project";

export default function ProjectSummaryCard({
  progress,
}: {
  progress: ProjectProgress;
}) {
  return (
    <div className="grid">
      <div className="card">
        <div className="muted">Volumes</div>
        <div className="stat">{progress.volumes}</div>
      </div>
      <div className="card">
        <div className="muted">Total tasks</div>
        <div className="stat">{progress.total_tasks}</div>
      </div>
      <div className="card">
        <div className="muted">Approved</div>
        <div className="stat">{progress.approved_tasks}</div>
      </div>
      <div className="card">
        <div className="muted">Complete</div>
        <div className="stat">{progress.percent_complete}%</div>
      </div>
    </div>
  );
}
