"""Generate Hugging Face staging folder (metadata artifacts; large TIFFs not copied)."""

from __future__ import annotations

from mito_data_agent.schemas import MitoVerseVolumeRow
from mito_data_agent.utils.io import write_json, write_text
from mito_data_agent.utils.paths import ensure_output_dirs, get_outputs_dir, normalize_stored_path, safe_slug, to_relative_path


def _build_volume_row(merged_metadata: dict) -> MitoVerseVolumeRow:
    """Construct a MitoVerseVolumeRow from merged metadata."""
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


def generate_hf_staging_files(merged_metadata: dict, run_id: str) -> str:
    """Create HF staging artifacts under outputs/hf_staging/<volume>/.

    Does not copy large raw/label files in the MVP.
    """
    ensure_output_dirs()
    volume = merged_metadata["volume"]
    slug = safe_slug(volume)
    staging_dir = get_outputs_dir() / "hf_staging" / slug
    staging_dir.mkdir(parents=True, exist_ok=True)

    row = _build_volume_row(merged_metadata)
    write_json(staging_dir / "metadata.json", row.model_dump())

    manifest = {
        "run_id": run_id,
        "raw_file_path": normalize_stored_path(merged_metadata.get("raw_file_path")),
        "label_file_path": normalize_stored_path(merged_metadata.get("label_file_path")),
        "metadata_file_path": normalize_stored_path(merged_metadata.get("metadata_file_path")),
        "would_upload_files": [
            normalize_stored_path(merged_metadata.get("raw_file_path")) or "",
            normalize_stored_path(merged_metadata.get("label_file_path")) or "",
        ],
        "note": (
            "Staging writes metadata.json, manifest.json, and README.md only. "
            "Large raw/label TIFFs are not copied (swap tool impl to copy/upload)."
        ),
    }
    write_json(staging_dir / "manifest.json", manifest)

    res = merged_metadata["resolution_nm"]
    shape = merged_metadata["shape_xyz"]
    readme = f"""# {volume}

**Dataset:** {merged_metadata['dataset']}
**Modality:** {merged_metadata['modality']}
**Organism:** {merged_metadata['organism']}
**Organ:** {merged_metadata['organ']}
**Tissue / region:** {merged_metadata['tissue_region']}
**Resolution (nm):** {res[0]}×{res[1]}×{res[2]}
**Shape (x,y,z):** {shape[0]}×{shape[1]}×{shape[2]}
**# Mito:** {merged_metadata['num_mito']}

> Staging folder for Hugging Face upload preparation (metadata only).
"""
    write_text(staging_dir / "README.md", readme)

    return to_relative_path(staging_dir) or str(staging_dir)
