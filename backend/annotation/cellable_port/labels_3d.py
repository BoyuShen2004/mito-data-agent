"""Whole-volume label summary + a downsampled 3D preview grid.

Not a direct Cellable port (Cellable's desktop app has the whole label
volume in RAM already, via ``updateUniqueLabelListFromEntireMask`` for the
label list and ``VTKSurfaceWidget`` for a real marching-cubes iso-surface
render) — the web app must never load a whole EM label volume per request
(same reasoning as ``annotation/visualization/slice_io.py``), so both
functions here read the working label file as a memmap and cache their
(potentially expensive, O(volume)) results, invalidated by the file's mtime.

**3D rendering choice**: Cellable renders true iso-surfaces via VTK marching
cubes. Reimplementing marching cubes plus a VTK-equivalent renderer in the
browser is a large lift for a preview panel; the smallest change that still
gives real per-label 3D shape feedback is: crop to the union bounding box of
the requested (visible/pinned) labels, block-max-pool it down to a small
voxel grid (so a multi-GB volume becomes at most a few hundred KB), and let
the frontend (``Labels3DPanel.tsx``, three.js) draw each label's voxels as
instanced cubes, culled to visible-face-adjacent voxels only. This matches
the brief's "choose the smallest change that works; document it" guidance
for the 3D panel.
"""

from __future__ import annotations

from collections import OrderedDict

import numpy as np

from .watershed import label_bbox_3d

_MAX_BBOX_CACHE = 256
_bbox_cache: "OrderedDict[tuple, tuple | None]" = OrderedDict()
_summary_cache: dict[str, tuple[float, dict]] = {}


def _cached_bbox(path_str: str, mtime: float, mm: np.memmap, label_id: int):
    key = (path_str, mtime, label_id)
    if key in _bbox_cache:
        _bbox_cache.move_to_end(key)
        return _bbox_cache[key]
    bbox = label_bbox_3d(mm, label_id, padding=0)
    _bbox_cache[key] = bbox
    _bbox_cache.move_to_end(key)
    while len(_bbox_cache) > _MAX_BBOX_CACHE:
        _bbox_cache.popitem(last=False)
    return bbox


def label_summary(path) -> dict:
    """Per-instance-id voxel count + first/last z, scanned once per file
    (cached by mtime) across the whole *working* label volume. Backs the
    Labels panel's "All labels" scope (vs. "this slice"), including
    jump-to-slice (``z_start``)."""
    import tifffile

    path_str = str(path)
    if not path.exists():
        return {"labels": []}
    mtime = path.stat().st_mtime
    cached = _summary_cache.get(path_str)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    mm = tifffile.memmap(path_str, mode="r")
    counts: dict[int, int] = {}
    first_z: dict[int, int] = {}
    last_z: dict[int, int] = {}
    for z in range(mm.shape[0]):
        ids, cnts = np.unique(np.asarray(mm[z]), return_counts=True)
        for lid, c in zip(ids.tolist(), cnts.tolist()):
            if lid <= 0:
                continue
            counts[lid] = counts.get(lid, 0) + c
            first_z.setdefault(lid, z)
            last_z[lid] = z

    result = {
        "labels": [
            {
                "id": lid,
                "voxel_count": counts[lid],
                "z_start": first_z[lid],
                "z_end": last_z[lid],
            }
            for lid in sorted(counts)
        ]
    }
    _summary_cache[path_str] = (mtime, result)
    return result


def _block_max_pool(mask: np.ndarray, stride: int) -> np.ndarray:
    if stride <= 1:
        return mask.astype(np.uint8)
    pz = (-mask.shape[0]) % stride
    py = (-mask.shape[1]) % stride
    px = (-mask.shape[2]) % stride
    padded = np.pad(mask, ((0, pz), (0, py), (0, px)))
    dz, dy, dx = padded.shape
    reshaped = padded.reshape(
        dz // stride, stride, dy // stride, stride, dx // stride, stride
    )
    return reshaped.max(axis=(1, 3, 5)).astype(np.uint8)


def labels_3d_preview(path, label_ids: list[int], target_size: int = 72, padding: int = 4) -> dict:
    """Downsampled per-label binary voxel grids, cropped to the union bbox
    of ``label_ids`` (each padded, same padding the Seeds tool uses) and
    pooled down so no dimension exceeds ``target_size``.

    Returns ``{"shape": (dz, dy, dx), "grids": {label_id: np.ndarray[uint8]}}``
    — an empty result (``shape=(0,0,0)``, no grids) if the file doesn't
    exist yet or none of ``label_ids`` are present.
    """
    import tifffile

    if not label_ids or not path.exists():
        return {"shape": (0, 0, 0), "grids": {}}

    path_str = str(path)
    mtime = path.stat().st_mtime
    mm = tifffile.memmap(path_str, mode="r")

    bboxes = [
        b
        for b in (
            _cached_bbox(path_str, mtime, mm, lid) for lid in label_ids
        )
        if b is not None
    ]
    if not bboxes:
        return {"shape": (0, 0, 0), "grids": {}}

    z1 = max(0, min(b[0] for b in bboxes) - padding)
    z2 = min(mm.shape[0], max(b[1] for b in bboxes) + padding)
    y1 = max(0, min(b[2] for b in bboxes) - padding)
    y2 = min(mm.shape[1], max(b[3] for b in bboxes) + padding)
    x1 = max(0, min(b[4] for b in bboxes) - padding)
    x2 = min(mm.shape[2], max(b[5] for b in bboxes) + padding)

    region = np.asarray(mm[z1:z2, y1:y2, x1:x2])
    stride = max(1, int(np.ceil(max(region.shape) / target_size)))

    grids: dict[int, np.ndarray] = {}
    for lid in label_ids:
        binmask = region == lid
        if not binmask.any():
            continue
        grids[lid] = _block_max_pool(binmask, stride)

    shape = next(iter(grids.values())).shape if grids else (0, 0, 0)
    return {"shape": shape, "grids": grids}
