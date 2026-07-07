"""Staging agent — wraps HF staging and MitoVerse update artifact generation."""

from __future__ import annotations

from mito_data_agent.agents.base import finalize
from mito_data_agent.agents.state import MultiAgentState
from mito_data_agent.tools.generate_hf_staging import generate_hf_staging_files
from mito_data_agent.tools.generate_mitoverse_update import generate_mitoverse_update_files


def staging_agent(state: MultiAgentState) -> dict:
    """Generate Hugging Face staging files and MitoVerse update files (dry-run).

    Both artifact groups are produced here so the supervisor can treat
    ``generated_artifacts`` as a single completeness gate before upload planning.
    """
    merged = state.get("merged_metadata") or {}
    run_id = state.get("run_id", "unknown")
    try:
        staging_dir = generate_hf_staging_files(merged, run_id)
        update_files = generate_mitoverse_update_files(merged, run_id)
        generated_artifacts = {
            "hf_staging_dir": staging_dir,
            "mitoverse_update_files": update_files,
            "complete": bool(staging_dir) and bool(update_files),
        }
        outputs = {
            "hf_staging_dir": staging_dir,
            "mitoverse_update_files": update_files,
            "generated_artifacts": generated_artifacts,
        }
        summary = (
            f"Generated HF staging ({staging_dir}) and "
            f"{len(update_files)} MitoVerse update file(s)."
        )
        return finalize(
            state,
            "staging_agent",
            "success",
            outputs,
            summary,
            input_keys=["merged_metadata", "run_id"],
        )
    except Exception as exc:  # noqa: BLE001
        outputs = {"generated_artifacts": {"complete": False, "error": str(exc)}}
        return finalize(
            state,
            "staging_agent",
            "failed",
            outputs,
            f"Artifact generation failed: {exc}",
            input_keys=["merged_metadata", "run_id"],
            errors=[f"Artifact generation failed: {exc}"],
        )
