"""Tests for pseudo-tool success/failure signals."""

from pathlib import Path

from mito_data_agent.tools.pseudo_push_github import pseudo_push_to_github
from mito_data_agent.tools.pseudo_signal import build_pseudo_result, pseudo_tool_observation
from mito_data_agent.tools.pseudo_upload_hf import pseudo_upload_to_hf


def test_pseudo_upload_signal_ok(tmp_path):
    staging = tmp_path / "vol1"
    staging.mkdir()
    (staging / "metadata.json").write_text("{}", encoding="utf-8")
    (staging / "manifest.json").write_text("{}", encoding="utf-8")

    result = pseudo_upload_to_hf(str(staging))
    obs = pseudo_tool_observation(result)

    assert result.mode == "pseudo"
    assert result.executed is True
    assert result.signal == "ok"
    assert result.success is True
    assert result.real_write_performed is False
    assert obs["signal"] == "ok"
    assert obs["observation"] == "stub_tool_result"
    assert obs["data"]["tool_name"] == "pseudo_upload_hf"


def test_pseudo_upload_signal_failed(tmp_path):
    result = pseudo_upload_to_hf(str(tmp_path / "missing"))

    assert result.signal == "failed"
    assert result.success is False
    assert pseudo_tool_observation(result)["signal"] == "failed"


def test_pseudo_push_signal_ok(tmp_path):
    f1 = tmp_path / "row.json"
    f1.write_text("{}", encoding="utf-8")

    result = pseudo_push_to_github([str(f1)], branch_name="agent/add-test")

    assert result.signal == "ok"
    assert result.executed is True
    assert result.real_write_performed is False


def test_build_pseudo_result_signal():
    result = build_pseudo_result(
        tool_name="demo",
        success=True,
        target="demo/target",
        planned_action="demo action",
        message="demo message",
    )
    assert result.signal == "ok"


def test_local_stub_result():
    from mito_data_agent.tools.pseudo_signal import build_stub_result, stub_tool_observation

    result = build_stub_result(
        tool_name="generate_hf_staging",
        success=True,
        mode="local",
        target="/tmp/staging",
        output_paths=["/tmp/staging/metadata.json"],
        planned_action="Generate HF staging metadata",
        message="Local staging executed.",
    )
    obs = stub_tool_observation(result)
    assert result.mode == "local"
    assert obs["observation"] == "stub_tool_result"
    assert obs["signal"] == "ok"


def test_generate_hf_staging_writes_files(tmp_path, monkeypatch):
    """The HF staging tool writes the expected artifacts under outputs/."""
    from mito_data_agent.tools.generate_hf_staging import generate_hf_staging_files

    merged = {
        "volume": "test_vol",
        "dataset": "d",
        "modality": "FIB-SEM",
        "organism": "Human",
        "organ": "Liver",
        "tissue_region": "region",
        "resolution_nm": (8.0, 8.0, 40.0),
        "shape_xyz": (10, 10, 10),
        "num_mito": 2,
    }
    monkeypatch.setattr(
        "mito_data_agent.tools.generate_hf_staging.get_outputs_dir",
        lambda: tmp_path,
    )
    staging_dir = generate_hf_staging_files(merged, "run_test")
    assert staging_dir
    assert list(tmp_path.rglob("metadata.json"))
    assert list(tmp_path.rglob("manifest.json"))
