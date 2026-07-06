"""Scan the local annotated-volume data directory."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import tifffile

from mito_data_agent import config
from mito_data_agent.schemas import LocalDataInventory, LocalVolumeEntry
from mito_data_agent.tools.inspect_files import _array_shape_to_xyz
from mito_data_agent.utils.paths import resolve_path, to_relative_path


def _read_tiff_shape_fast(path: Path) -> tuple[int, int, int]:
    """Read TIFF shape from headers/series metadata without loading the full array."""
    with tifffile.TiffFile(path) as tif:
        if tif.series:
            shape = tif.series[0].shape
        elif len(tif.pages) > 1:
            shape = (len(tif.pages),) + tif.pages[0].shape
        else:
            shape = tif.pages[0].shape
    return _array_shape_to_xyz(shape)


def _volume_id_from_raw(stem: str) -> str:
    if stem.endswith("_0000"):
        return stem[: -len("_0000")]
    return stem


def _inspect_label_quick(path: Path) -> tuple[tuple[int, int, int] | None, int | None, list[str]]:
    warnings: list[str] = []
    try:
        arr = tifffile.imread(path)
        shape = _array_shape_to_xyz(arr.shape)
        unique_labels = np.unique(arr)
        num_mito = int(np.sum(unique_labels != 0))
        return shape, num_mito, warnings
    except Exception as exc:
        warnings.append(f"Failed to read label {path.name}: {exc}")
        return None, None, warnings


def _inspect_raw_shape_quick(path: Path) -> tuple[tuple[int, int, int] | None, list[str]]:
    warnings: list[str] = []
    try:
        return _read_tiff_shape_fast(path), warnings
    except Exception as exc:
        warnings.append(f"Failed to read raw shape for {path.name}: {exc}")
        return None, warnings


def list_local_data(data_dir: str | None = None) -> LocalDataInventory:
    """Discover TIFF volumes under the configured data directory."""
    root = resolve_path(data_dir or config.DEFAULT_DATA_DIR)
    if root is None:
        return LocalDataInventory(
            data_dir=config.DEFAULT_DATA_DIR,
            volumes=[],
            unpaired_files=[],
            warnings=["Data directory not configured."],
        )
    warnings: list[str] = []

    if not root.exists():
        return LocalDataInventory(
            data_dir=to_relative_path(root) or str(root),
            volumes=[],
            unpaired_files=[],
            warnings=[f"Data directory not found: {to_relative_path(root)}"],
        )
    if not root.is_dir():
        return LocalDataInventory(
            data_dir=to_relative_path(root) or str(root),
            volumes=[],
            unpaired_files=[],
            warnings=[f"Data path is not a directory: {to_relative_path(root)}"],
        )

    tiff_files = sorted(
        p for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in (".tif", ".tiff")
    )

    raw_by_vol: dict[str, Path] = {}
    label_by_vol: dict[str, Path] = {}
    assigned: set[Path] = set()

    for path in tiff_files:
        stem = path.stem
        if stem.endswith("_0000"):
            vol_id = _volume_id_from_raw(stem)
            raw_by_vol[vol_id] = path
            assigned.add(path)
        else:
            label_by_vol[stem] = path

    for vol_id, label_path in label_by_vol.items():
        assigned.add(label_path)

    for vol_id, raw_path in raw_by_vol.items():
        assigned.add(raw_path)

    volume_ids = sorted(set(raw_by_vol) | set(label_by_vol))
    volumes: list[LocalVolumeEntry] = []

    for vol_id in volume_ids:
        raw_path = raw_by_vol.get(vol_id)
        label_path = label_by_vol.get(vol_id)
        entry_warnings: list[str] = []

        raw_shape = None
        label_shape = None
        num_mito = None
        raw_size = raw_path.stat().st_size if raw_path else None
        label_size = label_path.stat().st_size if label_path else None

        if raw_path:
            raw_shape, raw_warnings = _inspect_raw_shape_quick(raw_path)
            entry_warnings.extend(raw_warnings)
        else:
            entry_warnings.append("No raw file found (expected *_0000.tiff).")

        if label_path:
            label_shape, num_mito, label_warnings = _inspect_label_quick(label_path)
            entry_warnings.extend(label_warnings)
        else:
            entry_warnings.append("No label/mask file found.")

        if raw_shape and label_shape and raw_shape != label_shape:
            entry_warnings.append(
                f"Shape mismatch: raw={raw_shape}, label={label_shape}"
            )

        volumes.append(
            LocalVolumeEntry(
                volume_id=vol_id,
                raw_file_path=to_relative_path(raw_path) if raw_path else None,
                label_file_path=to_relative_path(label_path) if label_path else None,
                raw_size_bytes=raw_size,
                label_size_bytes=label_size,
                raw_shape_xyz=raw_shape,
                label_shape_xyz=label_shape,
                num_mito=num_mito,
                warnings=entry_warnings,
            )
        )

    unpaired = [to_relative_path(p) or str(p) for p in tiff_files if p not in assigned]

    if not tiff_files:
        warnings.append(f"No TIFF files found in {to_relative_path(root)}")

    return LocalDataInventory(
        data_dir=to_relative_path(root) or str(root),
        volumes=volumes,
        unpaired_files=unpaired,
        warnings=warnings,
    )
