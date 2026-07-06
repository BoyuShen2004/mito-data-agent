"""Tests for metadata merging."""

from mito_data_agent.schemas import ParsedUserRequest, VolumeObservation
from mito_data_agent.tools.merge_metadata import merge_prompt_and_observation_metadata


def test_num_mito_conflict_uses_label():
    parsed = ParsedUserRequest(
        intent="upload_annotation",
        volume="test",
        dataset="ds",
        modality="FIB-SEM",
        organism="Human",
        organ="Test",
        tissue_region="Test",
        resolution_nm=(8.0, 8.0, 40.0),
        shape_xyz=(6, 5, 4),
        num_mito=10,
    )
    observation = VolumeObservation(
        shape_xyz=(6, 5, 4),
        num_mito=3,
        shape_source="label_file",
        num_mito_source="label_file",
    )

    merged = merge_prompt_and_observation_metadata(parsed, None, observation)

    assert merged["num_mito"] == 3
    assert any("conflict" in w.lower() for w in merged["warnings"])
