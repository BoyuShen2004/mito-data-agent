import type { AnnotationTask } from "../types/task";
import type { Volume } from "../types/volume";
import { api } from "./client";

export const listProjectVolumes = (projectId: number) =>
  api.get<Volume[]>(`/projects/${projectId}/volumes/`);

export const getVolume = (id: number) => api.get<Volume>(`/volumes/${id}/`);

export const registerVolume = (projectId: number, form: FormData) =>
  api.postForm<Volume>(`/projects/${projectId}/volumes/`, form);

export const updateVolume = (id: number, form: FormData) =>
  api.patchForm<Volume>(`/volumes/${id}/`, form);

export interface SplitInput {
  z_step?: number;
  payment_amount?: string;
  task_type?: string;
  priority?: number;
  instructions?: string;
}

export const splitVolume = (id: number, data: SplitInput) =>
  api.post<{ created: number; tasks: AnnotationTask[] }>(
    `/volumes/${id}/split/`,
    data,
  );
