import type { Project, DatasetMetadata } from "../types/project";
import type { LabelType } from "../types";
import type { Volume } from "../types/volume";
import { api } from "./client";

export interface HpcFile {
  name: string;
  path: string;
  extension: string;
  size: number;
}

export interface DetectedPair {
  image: string;
  mask: string;
  base: string;
}

export interface HpcScanResult {
  directory: string;
  files: HpcFile[];
  pairs: DetectedPair[];
  unpaired: string[];
}

export const scanHpcDirectory = (hpc_directory: string) =>
  api.post<HpcScanResult>("/hpc/scan/", { hpc_directory });

export interface RegisterDataFile {
  name: string;
  chunk_id?: string;
}

export interface RegisterDataPair {
  image: string;
  mask?: string;
  chunk_id?: string;
}

export interface RegisterDataInput {
  dataset: string;
  volume: string;
  hpc_directory: string;
  project?: number | null;
  annotation_type?: string;
  pairs?: RegisterDataPair[];
  files?: RegisterDataFile[];
  label_type?: LabelType;
  metadata?: DatasetMetadata;
}

export interface RegisterDataResult {
  project: Project;
  volumes: Volume[];
}

export const registerData = (data: RegisterDataInput) =>
  api.post<RegisterDataResult>("/register-data/", data);
