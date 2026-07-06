"""Merge prompt metadata with file-derived observations."""

from __future__ import annotations

from typing import Optional

from mito_data_agent.schemas import (
    FileInspectionResult,
    ParsedUserRequest,
    VolumeObservation,
)
from mito_data_agent.utils.paths import normalize_stored_path


def merge_prompt_and_observation_metadata(
    parsed_request: ParsedUserRequest,
    file_inspection: Optional[FileInspectionResult] = None,
    volume_observation: Optional[VolumeObservation] = None,
) -> dict:
    """Combine prompt fields with file observations.

    File-derived shape and # Mito override prompt values when available.
    Resolution comes from metadata file first, then prompt.
    """
    merged: dict = {
        "volume": parsed_request.volume,
        "dataset": parsed_request.dataset,
        "modality": parsed_request.modality,
        "organism": parsed_request.organism,
        "organ": parsed_request.organ,
        "tissue_region": parsed_request.tissue_region,
        "resolution_nm": parsed_request.resolution_nm,
        "shape_xyz": parsed_request.shape_xyz,
        "num_mito": parsed_request.num_mito,
        "raw_file_path": normalize_stored_path(parsed_request.raw_file_path),
        "label_file_path": normalize_stored_path(parsed_request.label_file_path),
        "metadata_file_path": normalize_stored_path(parsed_request.metadata_file_path),
        "provenance": parsed_request.provenance,
        "source_url": parsed_request.source_url,
        "annotator": parsed_request.annotator,
        "notes": list(parsed_request.notes),
        "warnings": [],
    }

    if volume_observation:
        if volume_observation.resolution_nm is not None:
            if (
                parsed_request.resolution_nm is not None
                and parsed_request.resolution_nm != volume_observation.resolution_nm
            ):
                merged["warnings"].append(
                    f"Resolution conflict: prompt={parsed_request.resolution_nm}, "
                    f"observation={volume_observation.resolution_nm}; "
                    "using observation."
                )
            merged["resolution_nm"] = volume_observation.resolution_nm
            merged["resolution_source"] = volume_observation.resolution_source

        if volume_observation.shape_xyz is not None:
            if (
                parsed_request.shape_xyz is not None
                and parsed_request.shape_xyz != volume_observation.shape_xyz
            ):
                merged["warnings"].append(
                    f"Shape conflict: prompt={parsed_request.shape_xyz}, "
                    f"observation={volume_observation.shape_xyz}; "
                    "using observation."
                )
            merged["shape_xyz"] = volume_observation.shape_xyz
            merged["shape_source"] = volume_observation.shape_source

        if volume_observation.num_mito is not None:
            if (
                parsed_request.num_mito is not None
                and parsed_request.num_mito != volume_observation.num_mito
            ):
                merged["warnings"].append(
                    f"# Mito conflict: prompt={parsed_request.num_mito}, "
                    f"observation={volume_observation.num_mito}; "
                    "using observation."
                )
            merged["num_mito"] = volume_observation.num_mito
            merged["num_mito_source"] = volume_observation.num_mito_source

        merged["warnings"].extend(volume_observation.warnings)

    # file_inspection warnings are added by inspect_uploaded_files_node

    return merged
