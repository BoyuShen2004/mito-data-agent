"""Metadata record agent — persist parsed/validated metadata for every volume.

This is the "record what the user entered" capability. It handles **multiple
datasets described in one prompt** (each becomes its own record) and writes both:

1. a persistent, queryable ledger entry (``outputs/metadata_store/records.json``), and
2. a metadata sidecar file next to the actual data volumes
   (``<data_dir>/<slug>.metadata.json``),

so the metadata lives both in the agent's store and beside the data. It performs
no external (Hugging Face / GitHub) writes.
"""

from __future__ import annotations

from pathlib import Path

from mito_data_agent.agents.base import finalize
from mito_data_agent.agents.state import MultiAgentState
from mito_data_agent.tools.metadata_store import (
    get_store_path,
    record_metadata,
    write_metadata_sidecar,
)
from mito_data_agent.tools.reconcile_metadata import reconcile_with_files
from mito_data_agent.utils.paths import safe_slug, to_relative_path


_STRIP_SUFFIXES = ("_0000.tiff", "_0000.tif", ".tiff", ".tif")


def _dataset_key(md: dict) -> str | None:
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


def _records_to_write(state: MultiAgentState) -> list[tuple[dict, bool | None]]:
    """Collect every (metadata, validation_success) pair to record.

    The primary volume (merged_metadata, with file-derived values + validation)
    plus every additional dataset the parser found in ``parsed_request.datasets``.
    A dataset is recorded even if its ``volume`` field is empty — its name may be in
    ``dataset`` or derivable from a filename.
    """
    merged = state.get("merged_metadata") or {}
    validation = state.get("schema_validation") or {}
    parsed = state.get("parsed_request") or {}
    datasets = parsed.get("datasets") or []

    out: list[tuple[dict, bool | None]] = []
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


def metadata_record_agent(state: MultiAgentState) -> dict:
    """Record every volume's metadata to the store + a data-dir sidecar."""
    to_write = _records_to_write(state)
    if not to_write:
        return finalize(
            state,
            "metadata_record_agent",
            "skipped",
            {"metadata_record": {"recorded": False, "reason": "no metadata to record"}},
            "No metadata to record.",
            input_keys=["merged_metadata", "parsed_request"],
        )

    recorded: list[dict] = []
    errors: list[str] = []
    warnings: list[str] = []
    for metadata, validated in to_write:
        # File info wins over the prompt on any conflict (shape / # Mito / resolution).
        metadata, conflicts = reconcile_with_files(metadata)
        warnings.extend(conflicts)
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
                    # Snapshot so the report can show each dataset (not just the primary).
                    "metadata": entry.get("metadata", {}),
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{metadata.get('volume')}: {exc}")

    record = {
        "recorded": bool(recorded),
        "count": len(recorded),
        "volumes": recorded,
        "store_path": to_relative_path(get_store_path()),
    }
    names = ", ".join(r["volume"] for r in recorded) or "none"
    summary = f"Recorded {len(recorded)} volume(s) to store + data dir: {names}."
    if warnings:
        summary += f" ({len(warnings)} prompt/data conflict(s) resolved in favor of data.)"
    return finalize(
        state,
        "metadata_record_agent",
        "success" if recorded and not errors else ("failed" if errors and not recorded else "success"),
        {"metadata_record": record},
        summary,
        input_keys=["merged_metadata", "parsed_request", "schema_validation"],
        warnings=warnings,
        errors=errors,
    )
