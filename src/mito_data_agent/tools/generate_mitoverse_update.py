"""Generate MitoVerse metadata update files."""

from __future__ import annotations

import csv
from pathlib import Path

from mito_data_agent.schemas import MitoVerseVolumeRow
from mito_data_agent.utils.io import write_json, write_text
from mito_data_agent.utils.paths import ensure_output_dirs, get_outputs_dir, normalize_stored_path, safe_slug, to_relative_path


def _format_resolution(res: tuple) -> str:
    return f"{res[0]}×{res[1]}×{res[2]}"


def _format_shape(shape: tuple) -> str:
    return f"{shape[0]}×{shape[1]}×{shape[2]}"


def _build_volume_row(merged_metadata: dict) -> MitoVerseVolumeRow:
    return MitoVerseVolumeRow(
        volume=merged_metadata["volume"],
        dataset=merged_metadata["dataset"],
        modality=merged_metadata["modality"],
        organism=merged_metadata["organism"],
        organ=merged_metadata["organ"],
        tissue_region=merged_metadata["tissue_region"],
        resolution_nm=tuple(merged_metadata["resolution_nm"]),
        shape_xyz=tuple(int(v) for v in merged_metadata["shape_xyz"]),
        num_mito=int(merged_metadata["num_mito"]),
        provenance=merged_metadata.get("provenance"),
        source_url=merged_metadata.get("source_url"),
        annotator=merged_metadata.get("annotator"),
        raw_file_path=normalize_stored_path(merged_metadata.get("raw_file_path")),
        label_file_path=normalize_stored_path(merged_metadata.get("label_file_path")),
        metadata_file_path=normalize_stored_path(merged_metadata.get("metadata_file_path")),
        notes=merged_metadata.get("notes", []),
    )


def generate_mitoverse_update_files(merged_metadata: dict, run_id: str) -> list[str]:
    """Write MitoVerse row JSON, CSV, and site-update patch markdown."""
    ensure_output_dirs()
    volume = merged_metadata["volume"]
    slug = safe_slug(volume)
    out_dir = get_outputs_dir() / "mitoverse_updates"
    out_dir.mkdir(parents=True, exist_ok=True)

    row = _build_volume_row(merged_metadata)
    created: list[str] = []

    json_path = out_dir / f"{slug}_row.json"
    write_json(json_path, row.model_dump())
    created.append(to_relative_path(json_path) or str(json_path))

    csv_path = out_dir / f"{slug}_row.csv"
    csv_columns = [
        "Volume",
        "Dataset",
        "Modality",
        "Organism",
        "Organ",
        "Tissue / region",
        "Resolution (nm)",
        "Shape (x,y,z)",
        "# Mito",
    ]
    csv_row = {
        "Volume": row.volume,
        "Dataset": row.dataset,
        "Modality": row.modality,
        "Organism": row.organism,
        "Organ": row.organ,
        "Tissue / region": row.tissue_region,
        "Resolution (nm)": _format_resolution(row.resolution_nm),
        "Shape (x,y,z)": _format_shape(row.shape_xyz),
        "# Mito": row.num_mito,
    }
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_columns)
        writer.writeheader()
        writer.writerow(csv_row)
    created.append(to_relative_path(csv_path) or str(csv_path))

    patch_path = out_dir / f"{slug}_site_update_patch.md"
    patch_text = f"""# MitoVerse Site Update Patch (Dry-Run)

**Run ID:** {run_id}
**Volume:** {row.volume}

## Row that would be appended

| Volume | Dataset | Modality | Organism | Organ | Tissue / region | Resolution (nm) | Shape (x,y,z) | # Mito |
|--------|---------|----------|----------|-------|-----------------|-----------------|---------------|--------|
| {row.volume} | {row.dataset} | {row.modality} | {row.organism} | {row.organ} | {row.tissue_region} | {_format_resolution(row.resolution_nm)} | {_format_shape(row.shape_xyz)} | {row.num_mito} |

> Metadata update files for MitoVerse (local outputs only; no website API call).
"""
    write_text(patch_path, patch_text)
    created.append(to_relative_path(patch_path) or str(patch_path))

    return created
