// Shared enums / literal unions mirroring the Django `TextChoices`.

export type Role =
  | "manager"
  | "annotator"
  | "requester"
  | "client"
  | "reviewer"
  | null;

export type LabelType = "none" | "prediction" | "proofread" | "partial";

export type TaskType =
  | "manual_annotation"
  | "prediction_proofreading"
  | "final_review"
  | "qc_review";

export type TaskStatus =
  | "unassigned"
  | "assigned"
  | "in_progress"
  | "submitted"
  | "approved"
  | "rejected"
  | "revision_requested";

export type ProjectStatus =
  | "draft"
  | "active"
  | "in_annotation"
  | "in_review"
  | "completed"
  | "delivered"
  | "cancelled";

export type QCStatus = "not_run" | "passed" | "warning" | "failed";

export type ReviewDecision = "approved" | "rejected" | "revision_requested";

export interface CurrentUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_superuser: boolean;
  role: Role;
  institution_name: string;
}
