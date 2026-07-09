import type { ProjectStatus, TaskStatus } from "./index";

export interface Project {
  id: number;
  title: string;
  institution: number | null;
  institution_name: string;
  description: string;
  annotation_target: string;
  annotation_type: string;
  status: ProjectStatus;
  deadline: string | null;
  created_by: number | null;
  created_by_username: string;
  volume_count: number;
  task_count: number;
  created_at: string;
}

export interface ProjectProgress {
  total_tasks: number;
  approved_tasks: number;
  percent_complete: number;
  status_counts: Record<TaskStatus, number>;
  volumes: number;
}

export interface WorkloadRow {
  annotator_id: number;
  username: string;
  total: number;
  active: number;
  submitted: number;
  approved: number;
}

export interface PaymentTotals {
  total_records: number;
  total_amount: number;
  by_status: Record<string, { count: number; amount: number }>;
}

export interface ProjectSummary {
  project: Project;
  progress: ProjectProgress;
  workload: WorkloadRow[];
  payment: PaymentTotals;
}
