"""Tests for volume observation extraction."""

import numpy as np
import tifffile

from mito_data_agent.tools.extract_volume_observations import extract_volume_observations


def test_extract_from_temp_tiffs(tmp_path):
    """Use ephemeral TIFFs in tmp_path — no pseudo files in the repo."""
    raw = np.random.randint(0, 255, size=(4, 5, 6), dtype=np.uint8)
    label = np.zeros((4, 5, 6), dtype=np.uint16)
    label[0, 0, 1] = 1
    label[0, 0, 2] = 2
    label[0, 0, 3] = 3

    raw_path = tmp_path / "raw.tif"
    label_path = tmp_path / "label.tif"
    tifffile.imwrite(raw_path, raw)
    tifffile.imwrite(label_path, label)

    result = extract_volume_observations(
        raw_file_path=str(raw_path),
        label_file_path=str(label_path),
        prompt_resolution_nm=(8.0, 8.0, 40.0),
    )

    assert result.shape_xyz == (6, 5, 4)
    assert result.num_mito == 3
    assert result.num_mito_source == "label_file"
    assert result.shape_source in ("raw_file", "label_file")
