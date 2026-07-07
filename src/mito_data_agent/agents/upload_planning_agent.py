"""Upload planning agent — wraps the pseudo Hugging Face upload (dry-run)."""

from __future__ import annotations

from mito_data_agent.agents.base import finalize
from mito_data_agent.agents.state import MultiAgentState
from mito_data_agent.tools.pseudo_upload_hf import pseudo_upload_to_hf


def upload_planning_agent(state: MultiAgentState) -> dict:
    """Produce a pseudo Hugging Face upload plan (no real API calls).

    ``real_write_performed`` stays ``False`` — this only validates the staging
    directory and returns a plan describing what a real upload *would* do.
    """
    staging_dir = state.get("hf_staging_dir")
    if not staging_dir:
        plan = {
            "tool_name": "pseudo_upload_hf",
            "success": False,
            "signal": "failed",
            "real_write_performed": False,
            "message": "No HF staging directory available; cannot plan upload.",
        }
        return finalize(
            state,
            "upload_planning_agent",
            "failed",
            {"hf_upload_plan": plan, "real_write_performed": False},
            "Pseudo HF upload skipped — staging directory missing.",
            input_keys=["hf_staging_dir"],
            errors=["No HF staging directory available for upload planning."],
        )

    result = pseudo_upload_to_hf(staging_dir)
    plan = result.model_dump()
    return finalize(
        state,
        "upload_planning_agent",
        "success",
        {"hf_upload_plan": plan, "real_write_performed": False},
        f"Pseudo HF upload plan generated (signal={plan.get('signal')}, no real write).",
        input_keys=["hf_staging_dir"],
    )
