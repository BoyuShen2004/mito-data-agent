import type { TaskStatus, TaskType } from "./index";

export interface AnnotationTask {
  id: number;
  project: number;
  project_title: string;
  volume: number;
  volume_name: string;
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
  payment_amount: string;
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
}
