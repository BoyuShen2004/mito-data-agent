"""Deterministic dataset-recording pipeline (used by ``metadata_record_agent``).

Everything mechanical about *recording* lives here so the agent stays pure flow:
collecting every dataset in a request (primary + extras), keying each to its
on-disk file name, reconciling file-vs-prompt conflicts, and writing the ledger
entry + data-dir sidecar. The agent just calls :func:`record_datasets` and folds
the result into the trace via ``finalize``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from mito_data_agent.tools.metadata_store import (
    get_store_path,
    record_metadata,
    write_metadata_sidecar,
)
from mito_data_agent.tools.reconcile_metadata import (
    canonical_volume_from_files,
    reconcile_with_files,
)
from mito_data_agent.tools.validate_metadata import validate_required_metadata
from mito_data_agent.utils.paths import safe_slug, to_relative_path

_STRIP_SUFFIXES = ("_0000.tiff", "_0000.tif", ".tiff", ".tif")


def _dataset_key(md: dict) -> Optional[str]:
    """Best available identifier for a dataset (LLMs vary on volume vs dataset name).

    Falls back through volume → dataset → a stem derived from any file path, so a
    dataset is never dropped just because its name landed in a different field.
    """
    for field in ("volume", "dataset"):
        if md.get(field):
            return str(md[field])
    for field in ("raw_file_path", "label_file_path", "metadata_file_path"):
        value = md.get(field)
        if value:
            stem = Path(str(value)).name
            for suffix in _STRIP_SUFFIXES:
                if stem.endswith(suffix):
                    stem = stem[: -len(suffix)]
                    break
            if stem:
                return stem
    return None


def collect_datasets_to_record(state: dict) -> list[tuple[dict, Optional[bool]]]:
    """Every ``(metadata, validation_success)`` pair to record for this run.

    The primary volume (``merged_metadata``, with file-derived values + validation)
    plus every additional dataset the parser found in ``parsed_request.datasets``.
    A dataset is recorded even if its ``volume`` field is empty — its name may be in
    ``dataset`` or derivable from a filename.
    """
    merged = state.get("merged_metadata") or {}
    validation = state.get("schema_validation") or {}
    parsed = state.get("parsed_request") or {}
    datasets = parsed.get("datasets") or []

    out: list[tuple[dict, Optional[bool]]] = []
    seen: set[str] = set()

    primary_key = _dataset_key(merged) if (merged and not merged.get("error")) else None
    if primary_key:
        out.append((merged, validation.get("success")))
        seen.add(safe_slug(primary_key))

    for ds in datasets:
        key = _dataset_key(ds)
        if not key:
            continue
        slug = safe_slug(key)
        if slug in seen:
            continue
        seen.add(slug)
        entry = dict(ds)
        if not entry.get("volume"):
            entry["volume"] = key  # so the store + sidecar have a name to key on
        out.append((entry, None))  # extra datasets weren't validated individually

    return out


def record_datasets(state: dict) -> dict[str, Any]:
    """Record every dataset in the request to the store + a data-dir sidecar.

    Returns ``{"metadata_record", "details", "conflicts", "errors"}``. Every
    dataset is validated (so per-dataset validity is consistent). When a dataset's
    real data files exist on disk under a different name, the record +
    ``<name>.metadata.json`` are keyed to that **data-file name** (data wins over
    the prompt name). Conflicts (shape / # Mito / resolution) are auto-resolved in
    favour of the file and are informational, not warnings.
    """
    to_write = collect_datasets_to_record(state)
    if not to_write:
        return {
            "metadata_record": {"recorded": False, "reason": "no metadata to record"},
            "details": [],
            "conflicts": [],
            "errors": [],
        }

    recorded: list[dict] = []
    errors: list[str] = []
    conflicts: list[str] = []
    details: list[str] = []
    for metadata, _ in to_write:
        metadata, ds_conflicts = reconcile_with_files(metadata)
        conflicts.extend(ds_conflicts)
        # Data-file name wins over the prompt name: when this dataset's real TIFFs
        # are on disk under a different name, key the record + sidecar to that file
        # (e.g. MitoHardLiver -> jrc_mus-liver_recon-1_test0).
        canonical = canonical_volume_from_files(metadata)
        if canonical and canonical != metadata.get("volume"):
            metadata = {**metadata, "volume": canonical}
        # Validate EVERY dataset (not just the primary) so per-dataset validity is
        # consistent.
        validated = validate_required_metadata(metadata).success
        try:
            entry = record_metadata(
                metadata,
                run_id=state.get("run_id", "unknown"),
                source_prompt=state.get("user_prompt"),
                validation_success=validated,
            )
            sidecar = write_metadata_sidecar(metadata)
            recorded.append(
                {
                    "volume": entry.get("volume"),
                    "slug": entry.get("slug"),
                    "times_recorded": entry.get("times_recorded"),
                    "validation_success": entry.get("validation_success"),
                    "sidecar_path": sidecar,
                    "metadata": entry.get("metadata", {}),
                }
            )
            details.append(
                f"recorded '{entry.get('volume')}' (v{entry.get('times_recorded')}) → store + {sidecar}"
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{metadata.get('volume')}: {exc}")

    record = {
        "recorded": bool(recorded),
        "count": len(recorded),
        "volumes": recorded,
        "store_path": to_relative_path(get_store_path()),
    }
    return {
        "metadata_record": record,
        "details": details,
        "conflicts": conflicts,
        "errors": errors,
    }
