"""Load and cache the public MitoVerse volume catalog (HF data repo)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from mito_data_agent import config
from mito_data_agent.schemas import (
    MitoVerseCatalogMatch,
    MitoVerseCatalogSnapshot,
    MitoVerseDatasetSummary,
    MitoVerseLookupResult,
    MitoVerseSearchResult,
)
from mito_data_agent.utils.paths import ensure_output_dirs, get_outputs_dir


def _cache_path() -> Path:
    ensure_output_dirs()
    cache_dir = get_outputs_dir() / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "mitoverse_catalog.json"


def _normalize_token(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _volume_id_from_path(path: str | None) -> str | None:
    if not path:
        return None
    stem = Path(path).stem
    if stem.endswith("_0000"):
        stem = stem[: -len("_0000")]
    return stem or None


def _shape_xyz_from_catalog(entry: dict) -> tuple[int, int, int] | None:
    shape_zyx = entry.get("shape_zyx")
    if not shape_zyx or len(shape_zyx) != 3:
        return None
    z, y, x = shape_zyx
    return int(x), int(y), int(z)


def _resolution_nm_from_catalog(entry: dict) -> tuple[float, float, float] | None:
    voxel = entry.get("voxel_nm")
    if not voxel or len(voxel) != 3:
        return None
    return float(voxel[0]), float(voxel[1]), float(voxel[2])


def _summarize_entry(volume_id: str, entry: dict) -> dict[str, Any]:
    return {
        "volume_id": volume_id,
        "dataset_id": entry.get("dataset_id"),
        "modality": entry.get("modality"),
        "species": entry.get("species"),
        "organ": entry.get("organ"),
        "tissue": entry.get("tissue"),
        "shape_xyz": _shape_xyz_from_catalog(entry),
        "resolution_nm": _resolution_nm_from_catalog(entry),
        "num_mito": entry.get("n_instances"),
        "zarr": entry.get("zarr"),
        "provenance": entry.get("provenance"),
    }


def _load_cache_meta(raw: dict) -> tuple[dict[str, dict], MitoVerseCatalogSnapshot]:
    if "volumes" in raw and isinstance(raw["volumes"], dict):
        volumes = raw["volumes"]
        meta = raw.get("meta") or {}
    else:
        volumes = raw
        meta = {}
    snapshot = MitoVerseCatalogSnapshot(
        source_url=meta.get("source_url", config.MITOVERSE_CATALOG_URL),
        explorer_url=config.MITOVERSE_EXPLORER_URL,
        fetched_at=meta.get("fetched_at"),
        volume_count=len(volumes),
    )
    return volumes, snapshot


def fetch_mitoverse_catalog(*, force_refresh: bool = False) -> tuple[dict[str, dict], MitoVerseCatalogSnapshot]:
    """Download or load cached catalog.json from the MitoVerse HF dataset repo."""
    if not config.ALLOW_MITOVERSE_CATALOG_LOOKUP:
        raise RuntimeError("MitoVerse catalog lookup is disabled (ALLOW_MITOVERSE_CATALOG_LOOKUP=False).")

    cache = _cache_path()
    if cache.exists() and not force_refresh:
        raw = json.loads(cache.read_text(encoding="utf-8"))
        volumes, snapshot = _load_cache_meta(raw)
        if volumes:
            return volumes, snapshot

    req = urllib.request.Request(
        config.MITOVERSE_CATALOG_URL,
        headers={"User-Agent": "mito-data-agent/0.1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to fetch MitoVerse catalog: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected MitoVerse catalog format (expected object keyed by volume_id).")

    fetched_at = datetime.now(timezone.utc).isoformat()
    wrapped = {
        "meta": {
            "source_url": config.MITOVERSE_CATALOG_URL,
            "fetched_at": fetched_at,
            "volume_count": len(payload),
        },
        "volumes": payload,
    }
    cache.write_text(json.dumps(wrapped, indent=2), encoding="utf-8")
    snapshot = MitoVerseCatalogSnapshot(
        source_url=config.MITOVERSE_CATALOG_URL,
        explorer_url=config.MITOVERSE_EXPLORER_URL,
        fetched_at=fetched_at,
        volume_count=len(payload),
    )
    return payload, snapshot


def _volume_id_variants(query: str) -> list[str]:
    q = query.strip()
    if not q:
        return []
    variants = {q, q.replace("-", "_"), q.replace("_", "-")}
    bare = q
    for prefix in ("openorganelle_", "openorganelle-"):
        if bare.startswith(prefix):
            bare = bare[len(prefix) :]
    variants.add(bare)
    variants.add(f"openorganelle_{bare}")
    return [v for v in variants if v]


def _score_volume_id(query: str, volume_id: str) -> tuple[float, str]:
    q_norm = _normalize_token(query)
    vid_norm = _normalize_token(volume_id)
    if not q_norm:
        return 0.0, "none"
    if q_norm == vid_norm:
        return 1.0, "exact_volume_id"
    if q_norm in vid_norm or vid_norm in q_norm:
        return 0.92, "partial_volume_id"
    ratio = SequenceMatcher(None, q_norm, vid_norm).ratio()
    if ratio >= 0.82:
        return ratio, "fuzzy_volume_id"
    return 0.0, "none"


def _collect_lookup_queries(
    *,
    volume: str | None = None,
    volume_id: str | None = None,
    dataset: str | None = None,
    dataset_id: str | None = None,
    raw_file_path: str | None = None,
    label_file_path: str | None = None,
) -> dict[str, Any]:
    queries: dict[str, Any] = {}
    vol = volume or volume_id
    ds = dataset_id or dataset
    if vol:
        queries["volume"] = vol
    if ds:
        queries["dataset_id"] = ds
    for key, path in (("raw_file_path", raw_file_path), ("label_file_path", label_file_path)):
        if path:
            queries[key] = path
            hint = _volume_id_from_path(path)
            if hint:
                queries.setdefault("path_volume_hint", hint)
    return queries


def lookup_mitoverse_volume(
    *,
    volume: str | None = None,
    volume_id: str | None = None,
    dataset: str | None = None,
    dataset_id: str | None = None,
    raw_file_path: str | None = None,
    label_file_path: str | None = None,
    force_refresh: bool = False,
) -> MitoVerseLookupResult:
    """Check whether a volume appears in the public MitoVerse collection."""
    catalog, snapshot = fetch_mitoverse_catalog(force_refresh=force_refresh)
    query = _collect_lookup_queries(
        volume=volume,
        volume_id=volume_id,
        dataset=dataset,
        dataset_id=dataset_id,
        raw_file_path=raw_file_path,
        label_file_path=label_file_path,
    )

    candidates: list[MitoVerseCatalogMatch] = []
    search_terms: list[tuple[str, str]] = []
    for key in ("volume", "path_volume_hint"):
        val = query.get(key)
        if isinstance(val, str):
            search_terms.append((key, val))
    for term_key, term in search_terms:
        for variant in _volume_id_variants(term):
            for vid, entry in catalog.items():
                score, matched_by = _score_volume_id(variant, vid)
                if score <= 0:
                    continue
                ds_filter = query.get("dataset_id")
                if ds_filter and entry.get("dataset_id") != ds_filter:
                    score *= 0.75
                    matched_by = f"{matched_by}+dataset_mismatch"
                candidates.append(
                    MitoVerseCatalogMatch(
                        volume_id=vid,
                        dataset_id=entry.get("dataset_id"),
                        in_collection=True,
                        match_score=round(score, 3),
                        matched_by=f"{matched_by}:{term_key}",
                        entry=_summarize_entry(vid, entry),
                    )
                )

    # Exact key attempts (fast path)
    for key in ("volume", "path_volume_hint"):
        val = query.get(key)
        if not isinstance(val, str):
            continue
        for variant in _volume_id_variants(val):
            if variant in catalog:
                entry = catalog[variant]
                candidates.append(
                    MitoVerseCatalogMatch(
                        volume_id=variant,
                        dataset_id=entry.get("dataset_id"),
                        in_collection=True,
                        match_score=1.0,
                        matched_by=f"catalog_key:{key}",
                        entry=_summarize_entry(variant, entry),
                    )
                )

    # De-duplicate by volume_id, keep best score
    best_by_id: dict[str, MitoVerseCatalogMatch] = {}
    for cand in candidates:
        prev = best_by_id.get(cand.volume_id)
        if prev is None or cand.match_score > prev.match_score:
            best_by_id[cand.volume_id] = cand
    ranked = sorted(best_by_id.values(), key=lambda c: c.match_score, reverse=True)

    ds_filter = query.get("dataset_id")
    if ds_filter:
        ranked = [c for c in ranked if c.dataset_id == ds_filter] or ranked

    best = ranked[0] if ranked else None
    found = best is not None and best.match_score >= 0.95
    if found:
        message = f"Volume found in MitoVerse catalog: {best.volume_id}"
    elif ranked:
        message = (
            f"No confident exact match. Top candidate: {ranked[0].volume_id} "
            f"(score={ranked[0].match_score})."
        )
    else:
        message = "No matching volume found in the MitoVerse catalog."

    return MitoVerseLookupResult(
        query=query,
        found=found,
        best_match=best if found else None,
        candidates=ranked[:10],
        catalog=snapshot,
        message=message,
    )


def _field_match(query_val: str | None, entry_val: str | None) -> float:
    if not query_val or not entry_val:
        return 0.0
    q = _normalize_token(query_val)
    e = _normalize_token(str(entry_val))
    if q == e:
        return 1.0
    if q in e or e in q:
        return 0.85
    return SequenceMatcher(None, q, e).ratio()


def search_mitoverse_collection(
    *,
    volume: str | None = None,
    volume_id: str | None = None,
    dataset: str | None = None,
    dataset_id: str | None = None,
    modality: str | None = None,
    organism: str | None = None,
    species: str | None = None,
    organ: str | None = None,
    tissue: str | None = None,
    tissue_region: str | None = None,
    raw_file_path: str | None = None,
    label_file_path: str | None = None,
    shape_xyz: list[int] | tuple[int, int, int] | None = None,
    num_mito: int | None = None,
    limit: int = 15,
    force_refresh: bool = False,
) -> MitoVerseSearchResult:
    """Search the MitoVerse catalog using any provided hints (partial metadata OK)."""
    catalog, snapshot = fetch_mitoverse_catalog(force_refresh=force_refresh)
    query = {
        k: v
        for k, v in {
            "volume": volume or volume_id,
            "dataset_id": dataset_id or dataset,
            "modality": modality,
            "species": species or organism,
            "organ": organ,
            "tissue": tissue or tissue_region,
            "raw_file_path": raw_file_path,
            "label_file_path": label_file_path,
            "shape_xyz": list(shape_xyz) if shape_xyz else None,
            "num_mito": num_mito,
        }.items()
        if v is not None
    }
    if raw_file_path or label_file_path:
        hint = _volume_id_from_path(raw_file_path) or _volume_id_from_path(label_file_path)
        if hint:
            query["path_volume_hint"] = hint

    matches: list[MitoVerseCatalogMatch] = []
    for vid, entry in catalog.items():
        score = 0.0
        reasons: list[str] = []
        weight_sum = 0.0

        def add(field_score: float, weight: float, reason: str) -> None:
            nonlocal score, weight_sum
            if field_score <= 0:
                return
            score += field_score * weight
            weight_sum += weight
            reasons.append(reason)

        vol_query = query.get("volume") or query.get("path_volume_hint")
        if vol_query:
            vs, _ = _score_volume_id(str(vol_query), vid)
            add(vs, 3.0, "volume_id")

        if query.get("dataset_id"):
            add(_field_match(str(query["dataset_id"]), entry.get("dataset_id")), 2.0, "dataset_id")
        if query.get("modality"):
            add(_field_match(str(query["modality"]), entry.get("modality")), 1.2, "modality")
        if query.get("species"):
            add(_field_match(str(query["species"]), entry.get("species")), 1.0, "species")
        if query.get("organ"):
            add(_field_match(str(query["organ"]), entry.get("organ")), 1.0, "organ")
        if query.get("tissue"):
            add(_field_match(str(query["tissue"]), entry.get("tissue")), 1.0, "tissue")

        if query.get("shape_xyz"):
            target = tuple(int(v) for v in query["shape_xyz"])
            entry_shape = _shape_xyz_from_catalog(entry)
            if entry_shape == target:
                add(1.0, 2.0, "shape_xyz")
            elif entry_shape:
                add(0.0, 0.0, "")

        if query.get("num_mito") is not None and entry.get("n_instances") is not None:
            if int(query["num_mito"]) == int(entry["n_instances"]):
                add(1.0, 0.8, "num_mito")

        if weight_sum == 0:
            continue
        normalized = score / weight_sum
        if normalized < 0.35:
            continue
        matches.append(
            MitoVerseCatalogMatch(
                volume_id=vid,
                dataset_id=entry.get("dataset_id"),
                in_collection=True,
                match_score=round(normalized, 3),
                matched_by=",".join(reasons) or "multi_field",
                entry=_summarize_entry(vid, entry),
            )
        )

    matches.sort(key=lambda m: m.match_score, reverse=True)
    limited = matches[: max(1, min(limit, 50))]
    return MitoVerseSearchResult(
        query=query,
        match_count=len(matches),
        matches=limited,
        catalog=snapshot,
        message=(
            f"Found {len(matches)} catalog match(es); showing top {len(limited)}."
            if matches
            else "No catalog matches for the provided hints."
        ),
    )


def list_mitoverse_datasets(*, force_refresh: bool = False) -> list[MitoVerseDatasetSummary]:
    """Summarize dataset_id groups in the MitoVerse catalog."""
    catalog, _ = fetch_mitoverse_catalog(force_refresh=force_refresh)
    grouped: dict[str, list[str]] = {}
    for vid, entry in catalog.items():
        ds = entry.get("dataset_id") or "unknown"
        grouped.setdefault(ds, []).append(vid)
    summaries = [
        MitoVerseDatasetSummary(
            dataset_id=ds,
            volume_count=len(vols),
            example_volume_ids=sorted(vols)[:5],
        )
        for ds, vols in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    ]
    return summaries
