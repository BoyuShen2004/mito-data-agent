"""Tests for output directory helpers."""

from pathlib import Path

from mito_data_agent.utils.paths import clear_outputs, ensure_output_dirs


def test_clear_outputs(tmp_path, monkeypatch):
    outputs = tmp_path / "outputs"
    for sub in ("hf_staging", "mitoverse_updates", "execution_reports", "logs"):
        d = outputs / sub
        d.mkdir(parents=True)
        (d / "artifact.txt").write_text("old run")
    (outputs / "hf_staging" / "vol1").mkdir()
    (outputs / "hf_staging" / "vol1" / "metadata.json").write_text("{}")

    monkeypatch.setattr(
        "mito_data_agent.utils.paths.get_outputs_dir", lambda: outputs
    )

    stats = clear_outputs()

    assert stats["removed_files"] >= 4
    assert stats["removed_dirs"] == 1
    assert not (outputs / "hf_staging" / "vol1").exists()
    assert (outputs / "execution_reports" / ".gitkeep").exists()
    ensure_output_dirs()
