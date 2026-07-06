"""Inspect raw and label volume files."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import tifffile

from mito_data_agent.schemas import FileInspectionResult
from mito_data_agent.utils.paths import resolve_path, to_relative_path


def _array_shape_to_xyz(shape: tuple) -> tuple[int, int, int]:
    """Convert array shape to (x, y, z) convention.

  Shape convention:
  - (z, y, x) -> (x, y, z)
  - (y, x) -> (x, y, 1)
  - More dimensions: use last three as (z, y, x)
    """
    if len(shape) == 2:
        y, x = shape
        return (int(x), int(y), 1)
    if len(shape) == 3:
        z, y, x = shape
        return (int(x), int(y), int(z))
    if len(shape) > 3:
        z, y, x = shape[-3], shape[-2], shape[-1]
        return (int(x), int(y), int(z))
    raise ValueError(f"Unsupported array shape: {shape}")


def _read_tiff_shape(path: Path) -> tuple[int, int, int]:
    """Read TIFF shape and convert to (x, y, z)."""
    with tifffile.TiffFile(path) as tif:
        arr = tif.asarray()
    return _array_shape_to_xyz(arr.shape)


def inspect_files(
    raw_file_path: Optional[str],
    label_file_path: Optional[str],
) -> FileInspectionResult:
    """Check existence and basic properties of raw and label files.

    # Future versions should use lazy/chunked reading for large volumes.
    """
    warnings: list[str] = []
    raw_exists = False
    label_exists = False
    raw_shape: Optional[tuple[int, int, int]] = None
    label_shape: Optional[tuple[int, int, int]] = None
    label_dtype: Optional[str] = None
    num_mito: Optional[int] = None
    unique_count: Optional[int] = None
    file_format: Optional[str] = None

    if raw_file_path:
        raw_path = resolve_path(raw_file_path)
        if raw_path and raw_path.exists() and raw_path.suffix.lower() in (".tif", ".tiff"):
            raw_exists = True
            file_format = "tiff"
            try:
                raw_shape = _read_tiff_shape(raw_path)
            except Exception as exc:
                warnings.append(f"Failed to read raw file shape: {exc}")
        elif raw_path and raw_path.exists():
            warnings.append(f"Unsupported raw file format: {raw_path.suffix}")
        else:
            warnings.append(f"Raw file not found: {to_relative_path(raw_file_path) or raw_file_path}")
    else:
        warnings.append("No raw file path provided.")

    if label_file_path:
        label_path = resolve_path(label_file_path)
        if label_path and label_path.exists() and label_path.suffix.lower() in (".tif", ".tiff"):
            label_exists = True
            file_format = file_format or "tiff"
            try:
                # MVP: read full label array. Future: lazy/chunked reading.
                arr = tifffile.imread(label_path)
                if len(arr.shape) > 3:
                    warnings.append(
                        f"Label array has {len(arr.shape)} dims; using last 3."
                    )
                label_shape = _array_shape_to_xyz(arr.shape)
                label_dtype = str(arr.dtype)
                unique_labels = np.unique(arr)
                unique_count = len(unique_labels)
                num_mito = int(np.sum(unique_labels != 0))
            except Exception as exc:
                warnings.append(f"Failed to read label file: {exc}")
        elif label_path and label_path.exists():
            warnings.append(f"Unsupported label file format: {label_path.suffix}")
        else:
            warnings.append(f"Label file not found: {to_relative_path(label_file_path) or label_file_path}")
    else:
        warnings.append("No label file path provided.")

    shape_match: Optional[bool] = None
    if raw_shape is not None and label_shape is not None:
        shape_match = raw_shape == label_shape
        if not shape_match:
            warnings.append(
                f"Shape mismatch: raw={raw_shape}, label={label_shape}"
            )

    return FileInspectionResult(
        raw_file_exists=raw_exists,
        label_file_exists=label_exists,
        raw_shape_xyz=raw_shape,
        label_shape_xyz=label_shape,
        shape_match=shape_match,
        label_dtype=label_dtype,
        file_format=file_format,
        num_mito=num_mito,
        unique_label_count=unique_count,
        warnings=warnings,
    )
