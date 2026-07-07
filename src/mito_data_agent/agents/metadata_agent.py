"""Metadata agent — wraps the existing prompt/observation metadata merge."""

from __future__ import annotations

from mito_data_agent.agents.base import finalize
from mito_data_agent.agents.state import MultiAgentState
from mito_data_agent.schemas import (
    FileInspectionResult,
    ParsedUserRequest,
    VolumeObservation,
)
from mito_data_agent.tools.merge_metadata import merge_prompt_and_observation_metadata


def _parsed(state: MultiAgentState) -> ParsedUserRequest:
    return ParsedUserRequest(**(state.get("parsed_request") or {"intent": "unsupported_request"}))


def _file_inspection(state: MultiAgentState) -> FileInspectionResult | None:
    raw = state.get("file_inspection")
    if not raw:
        return None
    try:
        return FileInspectionResult(**raw)
    except Exception:  # noqa: BLE001
        return None


def _observation(state: MultiAgentState) -> VolumeObservation | None:
    raw = state.get("volume_observation")
    if not raw or "error" in raw:
        return None
    try:
        return VolumeObservation(**raw)
    except Exception:  # noqa: BLE001
        return None


def metadata_agent(state: MultiAgentState) -> dict:
    """Merge prompt metadata with file observations into a single record."""
    try:
        merged = merge_prompt_and_observation_metadata(
            _parsed(state), _file_inspection(state), _observation(state)
        )
        messages = merged.pop("warnings", [])
        # Prompt/data mismatches are auto-resolved in favour of the file — treat
        # those as informational conflicts, not warnings.
        conflicts = [m for m in messages if "conflict" in str(m).lower()]
        warnings = [m for m in messages if "conflict" not in str(m).lower()]
        details = [
            f"merged {k}={merged.get(k)} (source: {merged.get(k + '_source', 'prompt')})"
            for k in ("resolution_nm", "shape_xyz", "num_mito")
            if merged.get(k) is not None
        ]
        return finalize(
            state,
            "metadata_agent",
            "success",
            {"merged_metadata": merged},
            f"Merged metadata for volume '{merged.get('volume')}'.",
            input_keys=["parsed_request", "file_inspection", "volume_observation"],
            details=details,
            warnings=warnings,
            conflicts=conflicts,
        )
    except Exception as exc:  # noqa: BLE001
        return finalize(
            state,
            "metadata_agent",
            "failed",
            {"merged_metadata": {"error": str(exc)}},
            f"Metadata merge failed: {exc}",
            input_keys=["parsed_request", "file_inspection", "volume_observation"],
            errors=[f"Metadata merge failed: {exc}"],
        )
