import type { PaymentStatus } from "./index";

export interface PaymentRecord {
  id: number;
  annotator: number;
  annotator_username: string;
  task: number;
  task_type: string;
  project_title: string;
  amount: string;
  status: PaymentStatus;
  created_at: string;
  paid_at: string | null;
}

export interface AnnotatorPaymentRow {
  annotator_id: number;
  username: string;
  count: number;
  amount: number;
}

export interface ProjectPaymentSummary {
  totals: {
    total_records: number;
    total_amount: number;
    by_status: Record<string, { count: number; amount: number }>;
  };
  by_annotator: AnnotatorPaymentRow[];
}
