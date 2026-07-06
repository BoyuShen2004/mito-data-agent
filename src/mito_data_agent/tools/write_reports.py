"""Write execution, readiness, and error reports."""

from __future__ import annotations

from mito_data_agent.utils.io import write_json
from mito_data_agent.utils.paths import ensure_output_dirs, get_outputs_dir, normalize_stored_path, to_relative_path


def _normalize_report_paths(value):
    """Recursively normalize known path fields in report payloads."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in {
                "raw_file_path",
                "label_file_path",
                "metadata_file_path",
                "data_dir",
                "hf_staging_dir",
                "execution_report_path",
            }:
                out[key] = normalize_stored_path(item) if item else item
            elif key in {"mitoverse_update_files", "files_checked", "output_paths", "unpaired_files"}:
                out[key] = [
                    normalize_stored_path(p) or to_relative_path(p) or p for p in (item or [])
                ]
            else:
                out[key] = _normalize_report_paths(item)
        return out
    if isinstance(value, list):
        return [_normalize_report_paths(item) for item in value]
    return value


def _base_report(state: dict) -> dict:
    """Build common report fields from agent state."""
    parsed = state.get("parsed_request") or {}
    merged = state.get("merged_metadata") or {}
    vol_obs = state.get("volume_observation") or {}

    final_values = {}
    if merged:
        final_values = {
            "resolution_nm": merged.get("resolution_nm"),
            "resolution_source": merged.get("resolution_source"),
            "shape_xyz": merged.get("shape_xyz"),
            "shape_source": merged.get("shape_source"),
            "num_mito": merged.get("num_mito"),
            "num_mito_source": merged.get("num_mito_source"),
        }
    elif vol_obs:
        final_values = {
            "resolution_nm": vol_obs.get("resolution_nm"),
            "resolution_source": vol_obs.get("resolution_source"),
            "shape_xyz": vol_obs.get("shape_xyz"),
            "shape_source": vol_obs.get("shape_source"),
            "num_mito": vol_obs.get("num_mito"),
            "num_mito_source": vol_obs.get("num_mito_source"),
        }

    hf_plan = state.get("hf_upload_plan") or {}
    gh_plan = state.get("github_push_plan") or {}

    return _normalize_report_paths({
        "run_id": state.get("run_id"),
        "intent": parsed.get("intent"),
        "parsed_request": parsed,
        "file_inspection": state.get("file_inspection"),
        "volume_observation": vol_obs,
        "merged_metadata": merged,
        "schema_validation": state.get("schema_validation"),
        "final_values": final_values,
        "hf_staging_dir": state.get("hf_staging_dir"),
        "mitoverse_update_files": state.get("mitoverse_update_files", []),
        "hf_upload_plan": hf_plan,
        "github_push_plan": gh_plan,
        "pseudo_operations": {
            "hf_upload_performed": hf_plan.get("real_write_performed", False),
            "github_push_performed": gh_plan.get("real_write_performed", False),
            "note": "Stub tools set real_write_performed=false until swapped for production.",
        },
        "warnings": state.get("warnings", []),
        "errors": state.get("errors", []),
    })


def _write_report(state: dict, report_type: str, extra: dict | None = None) -> str:
    ensure_output_dirs()
    run_id = state.get("run_id", "unknown")
    report = _base_report(state)
    report["report_type"] = report_type
    if extra:
        report.update(extra)

    path = get_outputs_dir() / "execution_reports" / f"{run_id}.json"
    return write_json(path, report)


def write_execution_report(state: dict) -> str:
    """Write a full execution report after a successful workflow."""
    return _write_report(state, "execution_report", {"status": "completed"})


def write_missing_fields_report(state: dict) -> str:
    """Write a report when required metadata fields are missing."""
    validation = state.get("schema_validation") or {}
    return _write_report(
        state,
        "missing_fields_report",
        {
            "status": "incomplete",
            "missing_fields": validation.get("missing_fields", []),
            "message": validation.get("message", ""),
        },
    )


def write_error_report(state: dict) -> str:
    """Write a report when LLM parsing or early workflow error occurs."""
    return _write_report(
        state,
        "error_report",
        {
            "status": "error",
            "message": "; ".join(state.get("errors", [])) or "Unknown error",
        },
    )


def write_unsupported_report(state: dict) -> str:
    """Write a report for unsupported user requests."""
    return _write_report(
        state,
        "unsupported_report",
        {
            "status": "unsupported",
            "message": "The user request could not be mapped to a supported intent.",
        },
    )


def write_local_data_report(state: dict) -> str:
    """Write a report listing volumes found on disk."""
    inventory = state.get("local_data_inventory") or {}
    return _write_report(
        state,
        "local_data_report",
        {
            "status": "completed",
            "local_data_inventory": inventory,
            "message": (
                f"Found {len(inventory.get('volumes', []))} volume(s) "
                f"in {inventory.get('data_dir', 'unknown')}"
            ),
        },
    )


def write_readiness_report(state: dict) -> str:
    """Write a readiness check report (no upload/push)."""
    validation = state.get("schema_validation") or {}
    return _write_report(
        state,
        "readiness_report",
        {
            "status": "readiness_check",
            "ready_for_upload": validation.get("success", False),
            "message": validation.get("message", ""),
        },
    )
