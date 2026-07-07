"""Dataset inspector agent — wraps the existing file inspection tool."""

from __future__ import annotations

from mito_data_agent.agents.base import finalize
from mito_data_agent.agents.state import MultiAgentState
from mito_data_agent.tools.inspect_files import inspect_files


def dataset_inspector_agent(state: MultiAgentState) -> dict:
    """Inspect raw and label files on disk (existence, shape, dtype).

    Missing files are reported as warnings rather than crashes so a bad path
    flows on to validation/report instead of aborting the graph.
    """
    raw = state.get("raw_file_path")
    label = state.get("label_file_path")
    try:
        result = inspect_files(raw, label)
        inspection = result.model_dump()
        warnings = list(result.warnings)
        if not inspection.get("raw_file_exists"):
            warnings.append(f"Raw file not found: {raw}")
        if not inspection.get("label_file_exists"):
            warnings.append(f"Label file not found: {label}")
        summary = (
            f"Inspected files (raw_exists={inspection.get('raw_file_exists')}, "
            f"label_exists={inspection.get('label_file_exists')})."
        )
        return finalize(
            state,
            "dataset_inspector_agent",
            "success",
            {"file_inspection": inspection},
            summary,
            input_keys=["raw_file_path", "label_file_path"],
            warnings=warnings,
        )
    except Exception as exc:  # noqa: BLE001
        inspection = {
            "raw_file_exists": False,
            "label_file_exists": False,
            "error": str(exc),
        }
        return finalize(
            state,
            "dataset_inspector_agent",
            "failed",
            {"file_inspection": inspection},
            f"File inspection failed: {exc}",
            input_keys=["raw_file_path", "label_file_path"],
            errors=[f"File inspection failed: {exc}"],
        )
