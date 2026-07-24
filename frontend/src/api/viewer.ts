// Slice-viewer + in-app annotation API.
//
// Slices are streamed as PNG from the backend slice-IO endpoints. Auth is a
// token header (not a cookie), so an <img src> cannot authenticate — we fetch
// each slice with the header and hand back an object URL. Volume SliceViewer
// keeps those URLs in a bounded LRU; task View/Annotate share AnnotationCanvas.

import { api } from "./client";
import { getToken } from "./client";

export interface VolumeMeta {
  shape: { z: number; y: number; x: number };
  dtype: string;
  axes: string[];
  has_label: boolean;
  volume_id: number;
  display_range: { lo: number; hi: number };
}

export type Axis = "z" | "y" | "x";

export interface SliceParams {
  axis: Axis;
  index: number;
}

export const getVolumeMeta = (volumeId: number) =>
  api.get<VolumeMeta>(`/volumes/${volumeId}/meta/`);

// No window/level in the request: the server normalises every slice against
// the volume-wide display range once, so a slice is fetched exactly once per
// (axis, index) no matter how brightness/contrast are adjusted afterwards —
// those are applied client-side (a canvas filter) with zero extra requests.
export function imageSlicePath(volumeId: number, p: SliceParams): string {
  const q = new URLSearchParams({ axis: p.axis, index: String(p.index) });
  return `/api/volumes/${volumeId}/slice/?${q.toString()}`;
}

export function labelSlicePath(volumeId: number, axis: Axis, index: number): string {
  const q = new URLSearchParams({ axis, index: String(index) });
  return `/api/volumes/${volumeId}/label-slice/?${q.toString()}`;
}

/** Fetch a PNG slice with the auth header and return an object URL.
 *
 * Takes an optional ``signal`` so a caller can cancel it — the slice viewer
 * prefetches several MB-sized neighbours per navigation step, and without
 * cancellation, rapidly changing slices (e.g. a fast scrub, or switching
 * pages before older fetches finish) piles up dozens of in-flight requests
 * that outlive their relevance and starve the ones that are actually needed.
 */
export async function fetchObjectUrl(
  path: string,
  signal?: AbortSignal,
): Promise<string> {
  const token = getToken();
  const res = await fetch(path, {
    headers: token ? { Authorization: `Token ${token}` } : {},
    signal,
  });
  if (!res.ok) throw new Error(`slice ${res.status}`);
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

// --- Fork-aware SAM2 tracking ---------------------------------------------

export interface SeedInput {
  z: number;
  rle: [number, number][]; // [start, length] over the flattened HxW mask
  shape: [number, number];
}

export interface TrackResult {
  final_id: number;
  branch_ids: number[];
  group: {
    group_id: number;
    branch_ids: number[];
    final_id: number;
    seed_z: number | null;
  } | null;
}

export const trackTaskFork = (
  taskId: number,
  seeds: SeedInput[],
  zRange?: [number, number],
) =>
  api.post<TrackResult>(`/tasks/${taskId}/track/`, {
    seeds,
    z_range: zRange,
  });

// --- In-app label editor (raw instance ids, RLE over the wire) -------------
// A colorized PNG (labelSlicePath above) is fine for read-only viewing, but
// the editor needs the *raw* ids so it can hit-test under the cursor and
// paint/erase specific instances. Run-length encoding keeps the payload small
// even though a decoded slice (int32 per pixel) would not be.

export interface LabelIdsResponse {
  shape: [number, number];
  runs: [number, number][]; // [id, run-length], row-major
}

export interface LabelState {
  max_label_id: number;
  next_label_id: number;
}

export const getLabelState = (taskId: number) =>
  api.get<LabelState>(`/tasks/${taskId}/label-state/`);

export const getLabelIds = (taskId: number, axis: Axis, index: number, signal?: AbortSignal) =>
  api.get<LabelIdsResponse>(
    `/tasks/${taskId}/label-ids/?axis=${axis}&index=${index}`,
    signal,
  );

export const putLabelIds = (
  taskId: number,
  axis: Axis,
  index: number,
  shape: [number, number],
  runs: [number, number][],
  origin: "manual" | "ai" = "manual",
) =>
  api.put<LabelState>(`/tasks/${taskId}/label-ids/`, {
    axis,
    index,
    shape,
    runs,
    origin,
  });

/** Decode row-major RLE runs into a flat Int32Array of instance ids. */
export function decodeRuns(runs: [number, number][], size: number): Int32Array {
  const out = new Int32Array(size);
  let pos = 0;
  for (const [id, count] of runs) {
    out.fill(id, pos, pos + count);
    pos += count;
  }
  return out;
}

/** Inverse of decodeRuns: flat instance ids -> row-major RLE runs. */
export function encodeRuns(ids: Int32Array | Uint32Array): [number, number][] {
  const runs: [number, number][] = [];
  if (ids.length === 0) return runs;
  let start = 0;
  for (let i = 1; i <= ids.length; i++) {
    if (i === ids.length || ids[i] !== ids[start]) {
      runs.push([ids[start], i - start]);
      start = i;
    }
  }
  return runs;
}

// --- Cellable-ported interactive AI tools (Point/Box/Boundary, Seeds) ------
// See progress/history/19-cellable-parity-annotator-brief.md +
// backend/annotation/cellable_port/. Point/Box/Boundary are read-only
// "preview a mask" calls (0/1 label-RLE, reusing decodeRuns above) — the
// caller merges the result into its already-loaded slice and commits
// through putLabelIds like a brush stroke. Watershed is the one call here
// that mutates the server-side working copy directly (like trackTaskFork),
// since it operates in 3D across the whole label volume, not one slice.

export interface MaskPrediction {
  shape: [number, number];
  runs: [number, number][];
}

// `signal` lets the caller drop a superseded predict (rapid clicks / a new
// box drag before the last one resolved) — see AnnotationCanvas.tsx's
// sequence-guarded predict handlers (progress/history/23-cellable-parity-
// ort-and-prompt-ux.md).

export const predictMaskFromPoints = (
  taskId: number,
  axis: Axis,
  index: number,
  points: [number, number][],
  pointLabels: (0 | 1)[],
  signal?: AbortSignal,
) =>
  api.post<MaskPrediction>(
    `/tasks/${taskId}/predict-mask/`,
    { axis, index, mode: "points", points, point_labels: pointLabels },
    signal,
  );

export const predictMaskFromBox = (
  taskId: number,
  axis: Axis,
  index: number,
  box: [[number, number], [number, number]],
  signal?: AbortSignal,
) =>
  api.post<MaskPrediction>(
    `/tasks/${taskId}/predict-mask/`,
    { axis, index, mode: "box", box },
    signal,
  );

export const predictBoundary = (
  taskId: number,
  axis: Axis,
  index: number,
  points: [number, number][],
  pointLabels: (0 | 1)[],
  signal?: AbortSignal,
) =>
  api.post<MaskPrediction>(
    `/tasks/${taskId}/predict-mask/`,
    { axis, index, mode: "boundary", points, point_labels: pointLabels },
    signal,
  );

/** Pre-computes the EfficientSAM embedding for one slice so a following
 * Point/Box/Boundary predict is decoder-only — fire-and-forget from the
 * frontend (slice change, entering an AI tool, neighbor prefetch). Never
 * throws for "model unavailable" (`{warmed: false}`, HTTP 200) — only a
 * genuine network/abort failure rejects. */
export const warmEmbedding = (taskId: number, axis: Axis, index: number, signal?: AbortSignal) =>
  api.post<{ warmed: boolean }>(`/tasks/${taskId}/warm-embedding/`, { axis, index }, signal);

export interface WatershedSeed {
  z: number;
  y: number;
  x: number;
}

export interface WatershedResult {
  target_label: number;
  new_label_ids: number[];
  bbox: [number, number, number, number, number, number];
}

export const runWatershed = (taskId: number, label: number, seeds: WatershedSeed[]) =>
  api.post<WatershedResult>(`/tasks/${taskId}/watershed/`, { label, seeds });

// --- Labels panel (Filters Options: state/origin/lifecycle) + 3D preview ---
// Cellable parity — see progress/history/21-cellable-parity-followups.md.
// LabelState/LabelOrigin mirror backend/annotation/cellable_port/label_state.py.

export type LabelLifecycleState = "proposed" | "edited" | "verified";
export type LabelOrigin = "ai" | "watershed" | "manual" | "tracking" | "unknown";

export interface LabelSummaryRow {
  id: number;
  voxel_count: number;
  z_start: number;
  z_end: number;
  state: LabelLifecycleState;
  origin: LabelOrigin;
  verified_at: string;
  can_revert: boolean;
}

export interface LabelStats {
  total: number;
  proposed: number;
  edited: number;
  verified: number;
}

export const getLabelsSummary = (taskId: number) =>
  api.get<{ labels: LabelSummaryRow[]; stats: LabelStats }>(`/tasks/${taskId}/labels-summary/`);

export type LabelLifecycleAction = "verify" | "unverify" | "revert" | "reject";

export const setLabelLifecycle = (taskId: number, labelId: number, action: LabelLifecycleAction) =>
  api.post<{ label_id: number; action: string; state: LabelLifecycleState | null; removed: boolean }>(
    `/tasks/${taskId}/labels/${labelId}/lifecycle/`,
    { action },
  );

export interface Labels3DPreview {
  shape: [number, number, number];
  grids: Map<number, Uint8Array>;
}

/** Fetch + decode the compact binary 3D preview grid (see
 * `TaskLabels3DView`'s docstring for the wire format): a little-endian
 * header (dz, dy, dx, num_labels) followed by (label_id, dz*dy*dx bytes)
 * per label. Auth is a token header, same reason as `fetchObjectUrl`. */
export async function fetchLabels3D(
  taskId: number,
  labelIds: number[],
  signal?: AbortSignal,
): Promise<Labels3DPreview> {
  const token = getToken();
  const q = new URLSearchParams({ labels: labelIds.join(",") });
  const res = await fetch(`/api/tasks/${taskId}/labels-3d/?${q.toString()}`, {
    headers: token ? { Authorization: `Token ${token}` } : {},
    signal,
  });
  if (!res.ok) throw new Error(`labels-3d ${res.status}`);
  const buf = await res.arrayBuffer();
  const view = new DataView(buf);
  const dz = view.getUint32(0, true);
  const dy = view.getUint32(4, true);
  const dx = view.getUint32(8, true);
  const numLabels = view.getUint32(12, true);
  const grids = new Map<number, Uint8Array>();
  let offset = 16;
  const voxels = dz * dy * dx;
  for (let i = 0; i < numLabels; i++) {
    const labelId = view.getInt32(offset, true);
    offset += 4;
    grids.set(labelId, new Uint8Array(buf, offset, voxels));
    offset += voxels;
  }
  return { shape: [dz, dy, dx], grids };
}
