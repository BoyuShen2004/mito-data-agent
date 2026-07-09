import type { AnnotationTask, AssignResult } from "../types/task";
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

export const listMyTasks = () => api.get<AnnotationTask[]>("/my-tasks/");

export const listMyCompletedTasks = () =>
  api.get<AnnotationTask[]>("/my-completed-tasks/");
