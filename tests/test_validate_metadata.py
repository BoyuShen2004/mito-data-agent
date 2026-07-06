"""Tests for metadata validation."""

from mito_data_agent.tools.validate_metadata import validate_required_metadata


def _valid_metadata() -> dict:
    return {
        "volume": "test_vol",
        "dataset": "test_ds",
        "modality": "FIB-SEM",
        "organism": "Human",
        "organ": "Test",
        "tissue_region": "Test region",
        "resolution_nm": (8.0, 8.0, 40.0),
        "shape_xyz": (250, 250, 164),
        "num_mito": 42,
    }


def test_valid_metadata_passes():
    result = validate_required_metadata(_valid_metadata())
    assert result.success is True
    assert result.missing_fields == []


def test_missing_resolution_fails():
    meta = _valid_metadata()
    meta["resolution_nm"] = None
    result = validate_required_metadata(meta)
    assert result.success is False
    assert "resolution_nm" in result.missing_fields


def test_negative_num_mito_fails():
    meta = _valid_metadata()
    meta["num_mito"] = -1
    result = validate_required_metadata(meta)
    assert result.success is False
    assert "num_mito" in result.missing_fields


def test_invalid_shape_fails():
    meta = _valid_metadata()
    meta["shape_xyz"] = (0, 250, 164)
    result = validate_required_metadata(meta)
    assert result.success is False
    assert "shape_xyz" in result.missing_fields
