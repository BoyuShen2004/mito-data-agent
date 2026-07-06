"""Extract Resolution, Shape, and # Mito from files and prompt."""

from __future__ import annotations

import json
from typing import Optional

import numpy as np
import tifffile

from mito_data_agent.schemas import FileInspectionResult, VolumeObservation
from mito_data_agent.tools.inspect_files import _array_shape_to_xyz, inspect_files
from mito_data_agent.utils.paths import resolve_path


def _read_resolution_from_metadata(
    metadata_file_path: str,
) -> Optional[tuple[float, float, float]]:
    """Read resolution from a JSON metadata file."""
    path = resolve_path(metadata_file_path)
    if path is None or not path.exists():
        return None

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    for key in ("resolution_nm", "voxel_size_nm"):
        if key in data and data[key] is not None:
            vals = data[key]
            if isinstance(vals, (list, tuple)) and len(vals) == 3:
                return (float(vals[0]), float(vals[1]), float(vals[2]))
    return None


def _count_mito_from_label(label_file_path: str) -> Optional[int]:
    """Count unique non-zero labels in a label TIFF."""
    path = resolve_path(label_file_path)
    if path is None or not path.exists():
        return None
    try:
        arr = tifffile.imread(path)
        unique_labels = np.unique(arr)
        return int(np.sum(unique_labels != 0))
    except Exception:
        return None


def extract_volume_observations(
    raw_file_path: Optional[str] = None,
    label_file_path: Optional[str] = None,
    metadata_file_path: Optional[str] = None,
    prompt_resolution_nm: Optional[tuple[float, float, float]] = None,
    prompt_shape_xyz: Optional[tuple[int, int, int]] = None,
    prompt_num_mito: Optional[int] = None,
    file_inspection: Optional[FileInspectionResult] = None,
) -> VolumeObservation:
    """Build a VolumeObservation with file-derived values where possible."""
    observations: list[str] = []
    warnings: list[str] = []

    if file_inspection is None:
        inspection = inspect_files(raw_file_path, label_file_path)
        warnings.extend(inspection.warnings)
    else:
        inspection = file_inspection

    raw_shape = inspection.raw_shape_xyz
    label_shape = inspection.label_shape_xyz
    shape_xyz: Optional[tuple[int, int, int]] = None
    shape_source: Optional[str] = None

    if raw_shape and label_shape:
        if raw_shape == label_shape:
            shape_xyz = raw_shape
            shape_source = "raw_file"
            observations.append(f"Shape from matching raw/label files: {shape_xyz}")
        else:
            shape_xyz = label_shape
            shape_source = "label_file"
            warnings.append(
                f"Raw/label shape conflict; using label shape {label_shape} "
                f"(raw was {raw_shape})"
            )
            observations.append(f"Shape from label file (conflict): {shape_xyz}")
    elif label_shape:
        shape_xyz = label_shape
        shape_source = "label_file"
        observations.append(f"Shape from label file: {shape_xyz}")
    elif raw_shape:
        shape_xyz = raw_shape
        shape_source = "raw_file"
        observations.append(f"Shape from raw file: {shape_xyz}")
    elif prompt_shape_xyz:
        shape_xyz = prompt_shape_xyz
        shape_source = "prompt"
        observations.append(f"Shape from prompt: {shape_xyz}")

    # --- # Mito ---
    num_mito: Optional[int] = None
    num_mito_source: Optional[str] = None

    if label_file_path:
        label_resolved = resolve_path(label_file_path)
        if label_resolved and label_resolved.exists():
            label_mito = _count_mito_from_label(label_file_path)
            if label_mito is not None:
                num_mito = label_mito
                num_mito_source = "label_file"
                observations.append(f"# Mito from label file: {num_mito}")
                if prompt_num_mito is not None and prompt_num_mito != label_mito:
                    warnings.append(
                        f"Prompt # Mito ({prompt_num_mito}) conflicts with "
                        f"label-derived count ({label_mito}); using label value."
                    )
    elif prompt_num_mito is not None:
        num_mito = prompt_num_mito
        num_mito_source = "prompt"
        observations.append(f"# Mito from prompt: {num_mito}")

    # --- Resolution (nm) ---
    resolution_nm: Optional[tuple[float, float, float]] = None
    resolution_source: Optional[str] = None

    if metadata_file_path:
        meta_res = _read_resolution_from_metadata(metadata_file_path)
        if meta_res:
            resolution_nm = meta_res
            resolution_source = "metadata_file"
            observations.append(f"Resolution from metadata file: {resolution_nm}")

    if resolution_nm is None and prompt_resolution_nm:
        resolution_nm = prompt_resolution_nm
        resolution_source = "prompt"
        observations.append(f"Resolution from prompt: {resolution_nm}")

    return VolumeObservation(
        raw_file_path=raw_file_path,
        label_file_path=label_file_path,
        metadata_file_path=metadata_file_path,
        resolution_nm=resolution_nm,
        shape_xyz=shape_xyz,
        num_mito=num_mito,
        raw_shape_xyz=raw_shape,
        label_shape_xyz=label_shape,
        shape_source=shape_source,  # type: ignore[arg-type]
        resolution_source=resolution_source,  # type: ignore[arg-type]
        num_mito_source=num_mito_source,  # type: ignore[arg-type]
        observations=observations,
        warnings=warnings,
    )
