import type { QCStatus, ReviewDecision } from "./index";
import type { AnnotationTask } from "./task";

export interface ReviewRecord {
  id: number;
  submission: number;
  reviewer: number | null;
  reviewer_username: string;
  decision: ReviewDecision;
  comments: string;
  reviewed_at: string;
}

export interface Submission {
  id: number;
  task: number;
  task_detail: AnnotationTask;
  annotator: number | null;
  annotator_username: string;
  label_file: string;
  notes: string;
  qc_status: QCStatus;
  qc_report: Record<string, unknown>;
  reviews: ReviewRecord[];
  submitted_at: string;
}
