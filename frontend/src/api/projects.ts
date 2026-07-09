import type { Project, ProjectSummary } from "../types/project";
import type { ProjectPaymentSummary } from "../types/payment";
import { api } from "./client";

export interface ProjectInput {
  title: string;
  description?: string;
  annotation_type?: string;
  annotation_target?: string;
  status?: string;
  deadline?: string | null;
}

export const listProjects = () => api.get<Project[]>("/projects/");

export const getProject = (id: number) => api.get<Project>(`/projects/${id}/`);

export const createProject = (data: ProjectInput) =>
  api.post<Project>("/projects/", data);

export const updateProject = (id: number, data: Partial<ProjectInput>) =>
  api.patch<Project>(`/projects/${id}/`, data);

export const deleteProject = (id: number) => api.del<void>(`/projects/${id}/`);

export const getProjectSummary = (id: number) =>
  api.get<ProjectSummary>(`/projects/${id}/summary/`);

export const getProjectPaymentSummary = (id: number) =>
  api.get<ProjectPaymentSummary>(`/projects/${id}/payment-summary/`);
