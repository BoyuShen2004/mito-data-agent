"""Persistent, queryable metadata store (local ledger).

Records the metadata parsed/derived for each volume so it can be queried later
or reused to update Hugging Face / the MitoVerse website. This is a *record* of
what the user entered + what the file tools observed — it performs no external
writes.

Store layout (``outputs/metadata_store/records.json``)::

    {
      "meta": {"updated_at": "...", "count": N},
      "records": {
        "<volume-slug>": {
          "volume": "...", "slug": "...",
          "metadata": { ...MitoVerse fields... },
          "validation_success": true|false|null,
          "source_prompt": "...", "run_id": "...",
          "recorded_at": "...", "updated_at": "...",
          "times_recorded": K,
          "history": [ {recorded_at, run_id, metadata}, ... ]
        }
      }
    }
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from mito_data_agent import config
from mito_data_agent.utils.paths import (
    ensure_output_dirs,
    get_outputs_dir,
    resolve_path,
    safe_slug,
    to_relative_path,
)

# Metadata fields worth persisting (excludes transient keys like ``warnings``).
_RECORDED_FIELDS = (
    "volume",
    "dataset",
    "modality",
    "organism",
    "organ",
    "tissue_region",
    "resolution_nm",
    "resolution_source",
    "shape_xyz",
    "shape_source",
    "num_mito",
    "num_mito_source",
    "raw_file_path",
    "label_file_path",
    "metadata_file_path",
    "provenance",
    "source_url",
    "annotator",
    "notes",
)


def get_store_path() -> Path:
    """Return the metadata store file path (under outputs/)."""
    return get_outputs_dir() / "metadata_store" / "records.json"


def get_sidecar_dir() -> Optional[Path]:
    """Directory next to the actual data volumes where metadata sidecars go.

    Defaults to the configured data directory (``config.DEFAULT_DATA_DIR``, i.e.
    the folder holding the raw/label TIFFs), so a volume's metadata lives right
    beside its data.
    """
    return resolve_path(config.DEFAULT_DATA_DIR)


def write_metadata_sidecar(metadata: dict) -> Optional[str]:
    """Write ``<data_dir>/<slug>.metadata.json`` next to the data volumes.

    Returns the (project-relative) path written, or None if no data dir.
    """
    data_dir = get_sidecar_dir()
    if data_dir is None:
        return None
    data_dir.mkdir(parents=True, exist_ok=True)
    volume = metadata.get("volume") or "unknown"
    slug = safe_slug(volume)
    path = data_dir / f"{slug}.metadata.json"
    payload = {
        "volume": volume,
        "metadata": _clean_metadata(metadata),
        "written_by": "mito_data_agent",
        "written_at": _now(),
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return to_relative_path(path) or str(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_store() -> dict[str, Any]:
    """Load the whole store (returns an empty skeleton if none exists)."""
    path = get_store_path()
    if not path.exists():
        return {"meta": {"updated_at": None, "count": 0}, "records": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"meta": {"updated_at": None, "count": 0}, "records": {}}
    data.setdefault("records", {})
    data.setdefault("meta", {"updated_at": None, "count": len(data["records"])})
    return data


def _clean_metadata(metadata: dict) -> dict:
    """Keep only the durable MitoVerse fields."""
    return {k: metadata.get(k) for k in _RECORDED_FIELDS if metadata.get(k) is not None}


def record_metadata(
    metadata: dict,
    *,
    run_id: str,
    source_prompt: Optional[str] = None,
    validation_success: Optional[bool] = None,
) -> dict[str, Any]:
    """Upsert one volume's metadata record and return the stored entry.

    Re-recording the same volume updates the entry and pushes the previous
    version onto ``history`` (so nothing is silently lost).
    """
    ensure_output_dirs()
    volume = metadata.get("volume") or "unknown"
    slug = safe_slug(volume)
    clean = _clean_metadata(metadata)
    now = _now()

    store = load_store()
    records = store["records"]
    existing = records.get(slug)

    if existing:
        history = list(existing.get("history", []))
        history.append(
            {
                "recorded_at": existing.get("updated_at") or existing.get("recorded_at"),
                "run_id": existing.get("run_id"),
                "metadata": existing.get("metadata", {}),
            }
        )
        entry = {
            **existing,
            "volume": volume,
            "slug": slug,
            "metadata": clean,
            "validation_success": validation_success,
            "source_prompt": source_prompt,
            "run_id": run_id,
            "updated_at": now,
            "times_recorded": int(existing.get("times_recorded", 1)) + 1,
            "history": history[-20:],  # cap history growth
        }
    else:
        entry = {
            "volume": volume,
            "slug": slug,
            "metadata": clean,
            "validation_success": validation_success,
            "source_prompt": source_prompt,
            "run_id": run_id,
            "recorded_at": now,
            "updated_at": now,
            "times_recorded": 1,
            "history": [],
        }

    records[slug] = entry
    store["meta"] = {"updated_at": now, "count": len(records)}

    path = get_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2, default=str), encoding="utf-8")
    return entry


def list_records() -> list[dict[str, Any]]:
    """Return all stored records, most-recently-updated first."""
    records = list(load_store()["records"].values())
    records.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    return records


def get_record(volume: str) -> Optional[dict[str, Any]]:
    """Return the record for a volume (by name or slug), or None."""
    records = load_store()["records"]
    slug = safe_slug(volume)
    if slug in records:
        return records[slug]
    for rec in records.values():
        if rec.get("volume") == volume:
            return rec
    return None


def reconcile_record_names(*, dry_run: bool = False) -> list[dict[str, Any]]:
    """Rename stored records + sidecars whose name doesn't match the on-disk data.

    For every record, if its real data files can be located (via file paths or a
    name hint like ``provenance``), the record + its ``<name>.metadata.json`` are
    re-keyed to the actual **file stem** (e.g. ``MitoHardLiver`` ->
    ``jrc_mus-liver_recon-1_test0``), backfilling the raw/label paths and removing
    the old misnamed sidecar. The ``dataset`` name and history are preserved.

    Returns a list of ``{"old", "new", "removed_sidecar"}`` changes. With
    ``dry_run=True`` nothing is written and the list is a preview.
    """
    from mito_data_agent.tools.reconcile_metadata import canonical_volume_from_files
    from mito_data_agent.utils.paths import normalize_stored_path

    store = load_store()
    records = store["records"]
    data_dir = get_sidecar_dir()
    changes: list[dict[str, Any]] = []

    for old_slug in list(records.keys()):
        rec = records[old_slug]
        md = dict(rec.get("metadata", {}))
        canonical = canonical_volume_from_files(md)
        if not canonical:
            continue
        new_slug = safe_slug(canonical)
        if new_slug == old_slug and rec.get("volume") == canonical:
            continue  # already consistent

        removed_sidecar: Optional[str] = None
        if not dry_run:
            md["volume"] = canonical
            if data_dir is not None:
                for suffix, key in (("_0000.tiff", "raw_file_path"), (".tiff", "label_file_path")):
                    f = data_dir / f"{canonical}{suffix}"
                    if f.exists() and not md.get(key):
                        md[key] = normalize_stored_path(str(f))
            records.pop(old_slug, None)
            records[new_slug] = {**rec, "volume": canonical, "slug": new_slug, "metadata": md}
            if data_dir is not None:
                write_metadata_sidecar(md)  # writes <new_slug>.metadata.json
                old_path = data_dir / f"{old_slug}.metadata.json"
                new_path = data_dir / f"{new_slug}.metadata.json"
                if old_path.exists() and old_path != new_path:
                    old_path.unlink()
                    removed_sidecar = old_path.name

        changes.append({"old": old_slug, "new": new_slug, "removed_sidecar": removed_sidecar})

    if changes and not dry_run:
        store["meta"] = {"updated_at": _now(), "count": len(records)}
        path = get_store_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(store, indent=2, default=str), encoding="utf-8")
    return changes


def query_records(**filters: Any) -> list[dict[str, Any]]:
    """Return records whose metadata matches all provided field filters.

    Example: ``query_records(organism="Human", modality="FIB-SEM")``.
    Matching is case-insensitive substring on string fields.
    """
    out: list[dict[str, Any]] = []
    for rec in list_records():
        md = rec.get("metadata", {})
        ok = True
        for key, want in filters.items():
            if want is None:
                continue
            have = md.get(key)
            if have is None:
                ok = False
                break
            if isinstance(have, str) and isinstance(want, str):
                if want.lower() not in have.lower():
                    ok = False
                    break
            elif have != want:
                ok = False
                break
        if ok:
            out.append(rec)
    return out
