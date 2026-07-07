"""Website update agent — wraps the pseudo GitHub push (dry-run)."""

from __future__ import annotations

from mito_data_agent.agents.base import finalize
from mito_data_agent.agents.state import MultiAgentState
from mito_data_agent.tools.pseudo_push_github import pseudo_push_to_github
from mito_data_agent.utils.paths import safe_slug


def website_update_agent(state: MultiAgentState) -> dict:
    """Produce a pseudo GitHub push / PR plan for the MitoVerse website update.

    No real GitHub API call is made; ``real_write_performed`` stays ``False``.
    """
    merged = state.get("merged_metadata") or {}
    volume = merged.get("volume") or "unknown"
    slug = safe_slug(volume)
    update_files = state.get("mitoverse_update_files", []) or []

    try:
        result = pseudo_push_to_github(
            update_files,
            branch_name=f"agent/add-{slug}",
            pr_title=f"Add MitoVerse volume: {volume}",
        )
        plan = result.model_dump()
        return finalize(
            state,
            "website_update_agent",
            "success",
            {"github_push_plan": plan, "real_write_performed": False},
            f"Pseudo website update plan generated (signal={plan.get('signal')}, no real write).",
            input_keys=["merged_metadata", "mitoverse_update_files"],
        )
    except Exception as exc:  # noqa: BLE001
        plan = {
            "tool_name": "pseudo_push_github",
            "success": False,
            "signal": "failed",
            "real_write_performed": False,
            "message": str(exc),
        }
        return finalize(
            state,
            "website_update_agent",
            "failed",
            {"github_push_plan": plan, "real_write_performed": False},
            f"Pseudo website update failed: {exc}",
            input_keys=["merged_metadata", "mitoverse_update_files"],
            errors=[f"Pseudo website update failed: {exc}"],
        )
