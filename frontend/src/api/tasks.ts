import type { AnnotationTask, AssignResult, Annotator } from "../types/task";
import { api } from "./client";

export const listProjectTasks = (projectId: number, status?: string) =>
  api.get<AnnotationTask[]>(
    `/projects/${projectId}/tasks/${status ? `?status=${status}` : ""}`,
  );

export const getTask = (id: number) => api.get<AnnotationTask>(`/tasks/${id}/`);

export const updateTask = (id: number, data: Partial<AnnotationTask>) =>
  api.patch<AnnotationTask>(`/tasks/${id}/`, data);

export const assignTasks = (projectId: number) =>
  api.post<AssignResult>(`/projects/${projectId}/assign-tasks/`, {});

export const listAnnotators = () => api.get<Annotator[]>("/annotators/");

// Manually (re)assign a task to an annotator; null unassigns it.
export const assignTaskToAnnotator = (
  taskId: number,
  annotatorId: number | null,
) =>
  api.post<AnnotationTask>(`/tasks/${taskId}/assign/`, {
    annotator_id: annotatorId,
  });

export const listMyTasks = () => api.get<AnnotationTask[]>("/my-tasks/");

export const listMyCompletedTasks = () =>
  api.get<AnnotationTask[]>("/my-completed-tasks/");
