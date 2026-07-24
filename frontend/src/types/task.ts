import type { TaskStatus, TaskType } from "./index";

import type { DatasetMetadata } from "./project";

export interface AnnotationTask {
  id: number;
  project: number;
  project_title: string;
  dataset: string;
  // The shared biomedical metadata (same source managers/requesters see).
  dataset_metadata: DatasetMetadata;
  voxel_size_z: number | null;
  voxel_size_y: number | null;
  voxel_size_x: number | null;
  shape_z: number | null;
  shape_y: number | null;
  shape_x: number | null;
  volume: number;
  volume_name: string;
  source_volume: string;
  image_location: string;
  label_location: string;
  assigned_to: number | null;
  assigned_to_username: string;
  z_start: number;
  z_end: number;
  y_start: number;
  y_end: number;
  x_start: number;
  x_end: number;
  task_type: TaskType;
  status: TaskStatus;
  priority: number;
  difficulty: number;
  instructions: string;
  deadline: string | null;
  frame_label: string;
  created_at: string;
  assigned_at: string | null;
  submitted_at: string | null;
  approved_at: string | null;
}

export interface AssignResult {
  assigned: number;
  per_user: Record<string, number>;
  remaining_unassigned: number;
  reviewed?: boolean;
  created_tasks?: number;
  skipped_volumes?: number;
  detail?: string;
}

export interface Annotator {
  id: number;
  username: string;
  is_active_annotator: boolean;
  max_active_tasks: number;
}

// A row of the draft assignment plan: a task plus the annotator the auto-planner
// proposes for it, which the manager can override before saving.
export interface PlanEntryTask extends AnnotationTask {
  proposed_annotator_id: number | null;
}

export interface AssignmentPlanPreview {
  created_tasks: number;
  skipped_volumes: number;
  entries: PlanEntryTask[];
}

// Response of GET-ing the plan editor's rows: one per volume (a task is
// created for any volume that doesn't have one yet), with no proposed
// annotator — that's only computed when "Auto-fill balanced plan" runs.
export interface AssignmentPlanRows {
  created_tasks: number;
  skipped_volumes: number;
  entries: AnnotationTask[];
}

// What the client sends back when saving. Only task_id is required; other keys
// are included when the manager edited them.
export interface PlanEntryInput {
  task_id: number;
  annotator_id?: number | null;
  priority?: number;
  difficulty?: number;
  instructions?: string;
  deadline?: string | null;
}

export interface ApplyPlanResult {
  updated: number;
  assigned: number;
  remaining_unassigned: number;
}
