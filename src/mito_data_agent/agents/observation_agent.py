"""Observation agent — wraps the existing volume-observation extractor."""

from __future__ import annotations

from mito_data_agent.agents.base import finalize
from mito_data_agent.agents.state import MultiAgentState
from mito_data_agent.schemas import FileInspectionResult, ParsedUserRequest
from mito_data_agent.tools.extract_volume_observations import extract_volume_observations


def _parsed(state: MultiAgentState) -> ParsedUserRequest:
    data = state.get("parsed_request") or {"intent": "unsupported_request"}
    return ParsedUserRequest(**data)


def _file_inspection(state: MultiAgentState) -> FileInspectionResult | None:
    raw = state.get("file_inspection")
    if not raw:
        return None
    try:
        return FileInspectionResult(**raw)
    except Exception:  # noqa: BLE001 — tolerate a failed inspection payload
        return None


def observation_agent(state: MultiAgentState) -> dict:
    """Extract Resolution, Shape, and # Mito from files (label preferred)."""
    parsed = _parsed(state)
    try:
        result = extract_volume_observations(
            raw_file_path=state.get("raw_file_path"),
            label_file_path=state.get("label_file_path"),
            metadata_file_path=state.get("metadata_file_path"),
            prompt_resolution_nm=parsed.resolution_nm,
            prompt_shape_xyz=parsed.shape_xyz,
            prompt_num_mito=parsed.num_mito,
            file_inspection=_file_inspection(state),
        )
        observation = result.model_dump()
        summary = (
            f"Extracted observations (shape={observation.get('shape_xyz')}, "
            f"num_mito={observation.get('num_mito')})."
        )
        details = [
            f"resolution_nm={observation.get('resolution_nm')} (source: {observation.get('resolution_source')})",
            f"shape_xyz={observation.get('shape_xyz')} (source: {observation.get('shape_source')})",
            f"num_mito={observation.get('num_mito')} (source: {observation.get('num_mito_source')})",
        ]
        return finalize(
            state,
            "observation_agent",
            "success",
            {"volume_observation": observation},
            summary,
            input_keys=["parsed_request", "file_inspection", "raw_file_path", "label_file_path"],
            details=details,
            warnings=list(result.warnings),
        )
    except Exception as exc:  # noqa: BLE001
        return finalize(
            state,
            "observation_agent",
            "failed",
            {"volume_observation": {"error": str(exc)}},
            f"Observation extraction failed: {exc}",
            input_keys=["parsed_request", "file_inspection"],
            errors=[f"Observation extraction failed: {exc}"],
        )
