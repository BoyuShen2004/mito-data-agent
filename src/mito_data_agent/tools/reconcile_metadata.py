"""Reconcile prompt metadata with file-derived observations.

Policy: **when the prompt and the actual data files disagree, the file wins.**
The primary volume already gets this via ``merge_metadata`` (which overrides
shape / # Mito / resolution from file observations). This module applies the same
rule to *any* dataset — including the extra datasets in a multi-dataset prompt —
by locating each dataset's files and overriding its shape / # Mito / resolution
with the file-derived values, recording a warning on every conflict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from mito_data_agent import config
from mito_data_agent.tools.extract_volume_observations import extract_volume_observations
from mito_data_agent.tools.inspect_files import inspect_files
from mito_data_agent.utils.paths import normalize_stored_path, resolve_path

_STRIP_SUFFIXES = ("_0000.tiff", "_0000.tif", ".tiff", ".tif")


def _existing(path: Optional[str]) -> Optional[str]:
    """Return a normalized path if it exists (also tries the bare name in the data dir)."""
    if not path:
        return None
    resolved = resolve_path(path)
    if resolved and resolved.exists():
        return normalize_stored_path(path)
    data = resolve_path(config.DEFAULT_DATA_DIR)
    if data:
        candidate = data / Path(path).name
        if candidate.exists():
            return normalize_stored_path(str(candidate))
    return None


def _guess_from_name(name: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Guess raw/label paths in the data dir from a volume/filename hint."""
    if not name:
        return None, None
    data = resolve_path(config.DEFAULT_DATA_DIR)
    if not data:
        return None, None
    stem = Path(name).name
    for suffix in _STRIP_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    raw = data / f"{stem}_0000.tiff"
    label = data / f"{stem}.tiff"
    return (
        normalize_stored_path(str(raw)) if raw.exists() else None,
        normalize_stored_path(str(label)) if label.exists() else None,
    )


def _locate_files(metadata: dict) -> tuple[Optional[str], Optional[str]]:
    """Find a dataset's raw/label files from explicit paths or name hints."""
    raw = _existing(metadata.get("raw_file_path"))
    label = _existing(metadata.get("label_file_path"))
    if raw or label:
        return raw, label
    for hint in (
        metadata.get("raw_file_path"),
        metadata.get("label_file_path"),
        metadata.get("metadata_file_path"),
        metadata.get("volume"),
        metadata.get("dataset"),
    ):
        raw, label = _guess_from_name(hint)
        if raw or label:
            return raw, label
    return None, None


def _as_tuple(value):
    return tuple(value) if isinstance(value, (list, tuple)) else value


def reconcile_with_files(metadata: dict) -> tuple[dict, list[str]]:
    """Override prompt shape / # Mito / resolution with file-derived values.

    Returns ``(reconciled_metadata, warnings)``. If no files can be located (or the
    values already come from a file), the metadata is returned unchanged.
    """
    # Already file-derived (e.g. the primary volume went through merge) — leave it.
    if metadata.get("shape_source") in ("label_file", "raw_file"):
        return metadata, []

    raw, label = _locate_files(metadata)
    if not raw and not label:
        return metadata, []

    try:
        inspection = inspect_files(raw, label)
        obs = extract_volume_observations(
            raw_file_path=raw,
            label_file_path=label,
            metadata_file_path=metadata.get("metadata_file_path"),
            prompt_resolution_nm=_as_tuple(metadata.get("resolution_nm")),
            prompt_shape_xyz=_as_tuple(metadata.get("shape_xyz")),
            prompt_num_mito=metadata.get("num_mito"),
            file_inspection=inspection,
        )
    except Exception:  # noqa: BLE001 — reconciliation is best-effort
        return metadata, []

    out = dict(metadata)
    warnings: list[str] = []
    vol = metadata.get("volume") or "unknown"

    if obs.shape_xyz is not None:
        if metadata.get("shape_xyz") and _as_tuple(metadata["shape_xyz"]) != tuple(obs.shape_xyz):
            warnings.append(
                f"[{vol}] shape conflict: prompt={_as_tuple(metadata['shape_xyz'])} vs "
                f"data={tuple(obs.shape_xyz)}; using data."
            )
        out["shape_xyz"] = list(obs.shape_xyz)
        out["shape_source"] = obs.shape_source

    if obs.num_mito is not None:
        if metadata.get("num_mito") is not None and int(metadata["num_mito"]) != int(obs.num_mito):
            warnings.append(
                f"[{vol}] # Mito conflict: prompt={metadata['num_mito']} vs "
                f"data={obs.num_mito}; using data."
            )
        out["num_mito"] = int(obs.num_mito)
        out["num_mito_source"] = obs.num_mito_source

    # Only override resolution when it actually came from a metadata file.
    if obs.resolution_nm is not None and obs.resolution_source == "metadata_file":
        if metadata.get("resolution_nm") and _as_tuple(metadata["resolution_nm"]) != tuple(obs.resolution_nm):
            warnings.append(
                f"[{vol}] resolution conflict: prompt={_as_tuple(metadata['resolution_nm'])} vs "
                f"data={tuple(obs.resolution_nm)}; using data."
            )
        out["resolution_nm"] = list(obs.resolution_nm)
        out["resolution_source"] = obs.resolution_source

    if raw:
        out["raw_file_path"] = raw
    if label:
        out["label_file_path"] = label
    return out, warnings
