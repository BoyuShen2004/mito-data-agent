import type {
  AnnotationTask,
  Annotator,
  ApplyPlanResult,
  AssignmentPlanPreview,
  AssignmentPlanRows,
  AssignResult,
  PlanEntryInput,
} from "../types/task";
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

// List the plan editor's rows (one per volume, creating any missing
// whole-volume task) without proposing annotators — lets a manager start
// editing a plan before ever clicking "Auto-fill balanced plan".
export const listPlanRows = (projectId: number) =>
  api.post<AssignmentPlanRows>(`/projects/${projectId}/assign-plan/rows/`, {});

// Build a draft assignment plan (proposed annotators) without committing it.
export const previewAssignPlan = (projectId: number) =>
  api.post<AssignmentPlanPreview>(
    `/projects/${projectId}/assign-plan/preview/`,
    {},
  );

// Commit a manager-edited assignment plan in one request.
export const applyAssignPlan = (
  projectId: number,
  entries: PlanEntryInput[],
) =>
  api.post<ApplyPlanResult>(`/projects/${projectId}/assign-plan/apply/`, {
    entries,
  });

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
