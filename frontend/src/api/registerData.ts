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

/** An image matched to its mask by case id. The two may be in different dirs. */
export interface DetectedPair {
  image: string;
  mask: string;
  case: string;
}

/** A sibling folder offered as a quick pick (e.g. labelsTr vs labelsTr-instance). */
export interface DirSuggestion {
  name: string;
  path: string;
  count: number;
  split: string;
  current: boolean;
}

export interface ScanResult {
  image_directory: string;
  mask_directory: string;
  image_files: HpcFile[];
  mask_files: HpcFile[];
  pairs: DetectedPair[];
  unmatched_images: string[];
  unmatched_masks: string[];
  extra_channels: string[];
  /** "dataset.json" when pairs came from the manifest, else "filename". */
  pairing_source: string;
  split: string;
  suggestions: { images: DirSuggestion[]; masks: DirSuggestion[] };
  dataset_metadata: Record<string, unknown>;
  manifest_path: string;
}

export const scanDataSources = (
  image_directory: string,
  mask_directory: string,
) => api.post<ScanResult>("/hpc/scan/", { image_directory, mask_directory });

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
  image_directory: string;
  mask_directory?: string;
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
