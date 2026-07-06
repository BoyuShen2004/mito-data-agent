"""Thin LangGraph node wrappers around tools."""

from __future__ import annotations

from mito_data_agent.schemas import (
    FileInspectionResult,
    ParsedUserRequest,
    VolumeObservation,
)
from mito_data_agent.state import UploadAgentState
from mito_data_agent.tools.extract_volume_observations import extract_volume_observations
from mito_data_agent.tools.generate_hf_staging import generate_hf_staging_files
from mito_data_agent.tools.generate_mitoverse_update import generate_mitoverse_update_files
from mito_data_agent.tools.inspect_files import inspect_files
from mito_data_agent.tools.list_local_data import list_local_data
from mito_data_agent.tools.merge_metadata import merge_prompt_and_observation_metadata
from mito_data_agent.tools.parse_prompt import parse_user_prompt
from mito_data_agent.tools.pseudo_push_github import pseudo_push_to_github
from mito_data_agent.tools.pseudo_upload_hf import pseudo_upload_to_hf
from mito_data_agent.tools.validate_metadata import validate_required_metadata
from mito_data_agent.tools.write_reports import (
    write_error_report,
    write_execution_report,
    write_local_data_report,
    write_missing_fields_report,
    write_readiness_report,
    write_unsupported_report,
)
from mito_data_agent.tasks import get_parse_routes, resolve_post_validation, should_skip_hf_upload
from mito_data_agent.utils.paths import ensure_output_dirs, safe_slug


def validate_input_node(state: UploadAgentState) -> dict:
    """Validate required inputs and create output dirs."""
    if not state.get("user_prompt"):
        raise ValueError("user_prompt is required.")
    ensure_output_dirs()
    return {}


def parse_user_prompt_node(state: UploadAgentState) -> dict:
    """Parse the user prompt via LLM into structured fields."""
    try:
        parsed = parse_user_prompt(state["user_prompt"])
        return {
            "parsed_request": parsed.model_dump(),
            "raw_file_path": parsed.raw_file_path,
            "label_file_path": parsed.label_file_path,
            "metadata_file_path": parsed.metadata_file_path,
        }
    except Exception as exc:
        errors = list(state.get("errors", []))
        errors.append(f"LLM prompt parsing failed: {exc}")
        return {"errors": errors}


def route_after_parse(state: UploadAgentState) -> str:
    """Route to error report if LLM parsing failed, else by intent."""
    if state.get("errors"):
        return "parse_error"
    return route_intent(state)


def route_intent(state: UploadAgentState) -> str:
    """Return the parsed intent for conditional routing."""
    parsed = state.get("parsed_request") or {}
    intent = parsed.get("intent", "unsupported_request")
    if intent not in get_parse_routes():
        return "unsupported_request"
    return intent


def list_local_data_node(state: UploadAgentState) -> dict:
    """Scan DEFAULT_DATA_DIR and inventory local TIFF volumes."""
    inventory = list_local_data()
    warnings = list(state.get("warnings", []))
    warnings.extend(inventory.warnings)
    for vol in inventory.volumes:
        warnings.extend(vol.warnings)
    return {
        "local_data_inventory": inventory.model_dump(),
        "warnings": warnings,
    }


def inspect_uploaded_files_node(state: UploadAgentState) -> dict:
    """Inspect raw and label files on disk."""
    result = inspect_files(state.get("raw_file_path"), state.get("label_file_path"))
    warnings = list(state.get("warnings", []))
    warnings.extend(result.warnings)
    return {
        "file_inspection": result.model_dump(),
        "warnings": warnings,
    }


def extract_volume_observations_node(state: UploadAgentState) -> dict:
    """Extract Resolution, Shape, and # Mito from files."""
    parsed = ParsedUserRequest(**(state.get("parsed_request") or {}))
    result = extract_volume_observations(
        raw_file_path=state.get("raw_file_path"),
        label_file_path=state.get("label_file_path"),
        metadata_file_path=state.get("metadata_file_path"),
        prompt_resolution_nm=parsed.resolution_nm,
        prompt_shape_xyz=parsed.shape_xyz,
        prompt_num_mito=parsed.num_mito,
        file_inspection=FileInspectionResult(**state["file_inspection"])
        if state.get("file_inspection")
        else None,
    )
    warnings = list(state.get("warnings", []))
    warnings.extend(result.warnings)
    return {
        "volume_observation": result.model_dump(),
        "warnings": warnings,
    }


def merge_prompt_and_file_metadata_node(state: UploadAgentState) -> dict:
    """Merge prompt metadata with file observations."""
    parsed = ParsedUserRequest(**(state.get("parsed_request") or {}))
    file_inspection = None
    if state.get("file_inspection"):
        file_inspection = FileInspectionResult(**state["file_inspection"])
    volume_observation = None
    if state.get("volume_observation"):
        volume_observation = VolumeObservation(**state["volume_observation"])

    merged = merge_prompt_and_observation_metadata(
        parsed, file_inspection, volume_observation
    )
    warnings = list(state.get("warnings", []))
    warnings.extend(merged.pop("warnings", []))
    return {
        "merged_metadata": merged,
        "warnings": warnings,
    }


def validate_required_columns_node(state: UploadAgentState) -> dict:
    """Validate merged metadata against required MitoVerse columns."""
    merged = state.get("merged_metadata") or {}
    result = validate_required_metadata(merged)
    warnings = list(state.get("warnings", []))
    warnings.extend(result.warnings)
    return {
        "schema_validation": result.model_dump(),
        "warnings": warnings,
    }


def route_after_validation(state: UploadAgentState) -> str:
    """Route to valid path or missing_fields report."""
    validation = state.get("schema_validation") or {}
    if validation.get("success"):
        return "valid"
    return "missing_fields"


def route_post_validation(state: UploadAgentState) -> str:
    """Route after validation based on registered task spec."""
    parsed = state.get("parsed_request") or {}
    intent = parsed.get("intent", "unsupported_request")
    validation = state.get("schema_validation") or {}
    return resolve_post_validation(intent, bool(validation.get("success")))


def route_after_mitoverse_update(state: UploadAgentState) -> str:
    """Skip HF pseudo-upload when the task spec says so."""
    parsed = state.get("parsed_request") or {}
    intent = parsed.get("intent", "unsupported_request")
    if should_skip_hf_upload(intent):
        return "skip_hf_upload"
    return "do_hf_upload"


def generate_hf_staging_files_node(state: UploadAgentState) -> dict:
    """Generate Hugging Face staging artifacts."""
    staging_dir = generate_hf_staging_files(
        state["merged_metadata"], state["run_id"]
    )
    return {"hf_staging_dir": staging_dir}


def generate_mitoverse_update_files_node(state: UploadAgentState) -> dict:
    """Generate MitoVerse update files."""
    files = generate_mitoverse_update_files(
        state["merged_metadata"], state["run_id"]
    )
    return {"mitoverse_update_files": files}


def pseudo_upload_to_hf_node(state: UploadAgentState) -> dict:
    """Plan Hugging Face upload from staging artifacts."""
    result = pseudo_upload_to_hf(state["hf_staging_dir"])
    return {"hf_upload_plan": result.model_dump()}


def pseudo_push_to_github_node(state: UploadAgentState) -> dict:
    """Plan GitHub push from MitoVerse update files."""
    merged = state.get("merged_metadata") or {}
    volume = merged.get("volume", "unknown")
    slug = safe_slug(volume)
    result = pseudo_push_to_github(
        state.get("mitoverse_update_files", []),
        branch_name=f"agent/add-{slug}",
        pr_title=f"Add MitoVerse volume: {volume}",
    )
    return {"github_push_plan": result.model_dump()}


def write_execution_report_node(state: UploadAgentState) -> dict:
    """Write final execution report."""
    path = write_execution_report(dict(state))
    return {"execution_report_path": path}


def write_missing_fields_report_node(state: UploadAgentState) -> dict:
    """Write report for missing required fields."""
    path = write_missing_fields_report(dict(state))
    return {"execution_report_path": path}


def write_error_report_node(state: UploadAgentState) -> dict:
    """Write report when LLM parsing or early fatal error occurs."""
    path = write_error_report(dict(state))
    return {"execution_report_path": path}


def write_unsupported_report_node(state: UploadAgentState) -> dict:
    """Write report for unsupported requests."""
    path = write_unsupported_report(dict(state))
    return {"execution_report_path": path}


def write_readiness_report_node(state: UploadAgentState) -> dict:
    """Write upload readiness report."""
    path = write_readiness_report(dict(state))
    return {"execution_report_path": path}


def write_local_data_report_node(state: UploadAgentState) -> dict:
    """Write local data inventory report."""
    path = write_local_data_report(dict(state))
    return {"execution_report_path": path}
