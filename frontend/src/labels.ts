// Centralised display labels (internal value -> user-facing text).
//
// Donglai's design calls the data-owning role an "Institution"; the backend
// keeps the stable internal role value `requester`. This module is the single
// place that maps internal identifiers to the words shown in the UI, so React
// components never hard-code "Institution" / "Requester" inline.
//
// Keep in sync with the backend mirror in `backend/core/labels.py`.

import type { Role } from "./types";

export type Lifecycle = "new" | "to_proofread" | "done";
export type WorkflowType = "annotation" | "proofreading" | "segmentation";

export const ROLE_LABELS: Record<string, string> = {
  manager: "Manager",
  annotator: "Annotator",
  requester: "Institution",
  client: "Institution",
  reviewer: "Reviewer",
};

export const LIFECYCLE_LABELS: Record<Lifecycle, string> = {
  new: "New",
  to_proofread: "To Proofread",
  done: "Done",
};

// Ordered for navigation / tabs.
export const LIFECYCLE_ORDER: Lifecycle[] = ["new", "to_proofread", "done"];

export const WORKFLOW_TYPE_LABELS: Record<WorkflowType, string> = {
  annotation: "Annotation",
  proofreading: "Proofreading",
  segmentation: "Segmentation",
};

// Domain nouns whose display label may diverge from the internal name.
export const TERM_LABELS: Record<string, string> = {
  requester: "Institution",
  project: "Project",
  dataset: "Dataset",
  volume: "Volume",
  chunk: "Chunk",
  task: "Task",
  submission: "Submission",
  review: "Review",
};

function titleize(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function roleLabel(role: Role | string | null | undefined): string {
  if (!role) return "";
  return ROLE_LABELS[role] ?? titleize(role);
}

export function lifecycleLabel(value: Lifecycle | string): string {
  return LIFECYCLE_LABELS[value as Lifecycle] ?? titleize(value);
}

export function workflowTypeLabel(value: WorkflowType | string): string {
  return WORKFLOW_TYPE_LABELS[value as WorkflowType] ?? titleize(value);
}

export function termLabel(term: string): string {
  return TERM_LABELS[term] ?? titleize(term);
}
