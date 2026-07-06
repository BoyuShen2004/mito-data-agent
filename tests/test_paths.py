"""Tests for project-relative path helpers."""

from pathlib import Path

from mito_data_agent.utils.paths import (
    get_project_root,
    normalize_stored_path,
    resolve_path,
    to_relative_path,
)


def test_resolve_relative_data_dir():
    resolved = resolve_path("../mito_data_agent_data")
    assert resolved is not None
    assert resolved.name == "mito_data_agent_data"


def test_to_relative_path_for_outputs():
    rel = to_relative_path(get_project_root() / "outputs" / "logs")
    assert rel == "outputs/logs"


def test_normalize_stored_path_from_absolute():
    root = get_project_root()
    abs_path = root / "outputs" / "hf_staging" / "vol1"
    assert normalize_stored_path(str(abs_path)) == "outputs/hf_staging/vol1"


def test_normalize_stored_path_keeps_relative():
    assert normalize_stored_path("../mito_data_agent_data/vol1.tiff") == (
        "../mito_data_agent_data/vol1.tiff"
    )
