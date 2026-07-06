"""Tests for local data directory scanning via ReAct agent."""

from __future__ import annotations

import numpy as np
import tifffile

from mito_data_agent.runner import run_agent
from mito_data_agent.tools.list_local_data import list_local_data


def _write_pair(tmp_path, vol_id: str = "vol1"):
    raw = tmp_path / f"{vol_id}_0000.tiff"
    label = tmp_path / f"{vol_id}.tiff"
    tifffile.imwrite(raw, np.zeros((10, 20, 30), dtype=np.uint8))
    label_arr = np.zeros((10, 20, 30), dtype=np.uint16)
    label_arr[0, 0, 1] = 1
    label_arr[0, 0, 2] = 2
    tifffile.imwrite(label, label_arr)
    return raw, label


def test_list_local_data_finds_paired_volume(tmp_path, monkeypatch):
    _write_pair(tmp_path)
    monkeypatch.setattr("mito_data_agent.config.DEFAULT_DATA_DIR", str(tmp_path))

    inventory = list_local_data()
    assert len(inventory.volumes) == 1
    vol = inventory.volumes[0]
    assert vol.volume_id == "vol1"
    assert vol.raw_shape_xyz == (30, 20, 10)
    assert vol.num_mito == 2


def test_list_local_data_agent(tmp_path, monkeypatch):
    _write_pair(tmp_path)
    monkeypatch.setattr("mito_data_agent.config.DEFAULT_DATA_DIR", str(tmp_path))

    result = run_agent("check what data do i currently have", trace=False)
    inventory = result["raw"]["artifacts"].get("local_data_inventory")
    assert inventory is not None
    assert len(inventory["volumes"]) == 1
    assert "list_local_data" in result["summary"].get("tools_used", [])
