import type { LabelType } from "./index";

export interface Volume {
  id: number;
  project: number;
  name: string;
  image_path: string;
  image_file: string | null;
  label_path: string;
  label_file: string | null;
  label_type: LabelType;
  shape_z: number | null;
  shape_y: number | null;
  shape_x: number | null;
  voxel_size_z: number | null;
  voxel_size_y: number | null;
  voxel_size_x: number | null;
  file_format: string;
  metadata: Record<string, unknown>;
  status: string;
  has_label: boolean;
  image_location: string;
  label_location: string;
  task_count: number;
  created_at: string;
}
