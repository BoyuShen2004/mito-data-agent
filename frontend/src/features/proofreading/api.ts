// Proofreading feature — talks to the backend proofreading provider.
//
// This folder is the frontend home of online proofreading. To change how
// annotators open/download proofreading work, edit files here (mirrors the
// backend provider in `backend/annotation/proofreading/`).

import { api } from "../../api/client";

export type ProofreadingMode = "edit" | "view" | "download" | "unavailable";

export interface ProofreadingDownload {
  task_id: number;
  volume: string;
  image_path: string;
  label_path: string;
  region: {
    z_start: number;
    z_end: number;
    y_start: number;
    y_end: number;
    x_start: number;
    x_end: number;
  };
}

export interface ProofreadingInfo {
  mode: ProofreadingMode;
  url: string;
  editable: boolean;
  download_available: boolean;
  message: string;
  provider: string;
  extra?: Record<string, unknown>;
  download: ProofreadingDownload;
}

export function getProofreadingInfo(taskId: number): Promise<ProofreadingInfo> {
  return api.get<ProofreadingInfo>(`/tasks/${taskId}/proofreading/`);
}
