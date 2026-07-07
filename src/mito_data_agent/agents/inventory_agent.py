"""Inventory agent — wraps the existing local-data scan tool."""

from __future__ import annotations

from mito_data_agent.agents.base import finalize
from mito_data_agent.agents.state import MultiAgentState
from mito_data_agent.tools.list_local_data import list_local_data


def inventory_agent(state: MultiAgentState) -> dict:
    """Scan the local data directory and inventory paired raw/label volumes."""
    parsed = state.get("parsed_request") or {}
    data_dir = parsed.get("data_dir")
    try:
        inventory = list_local_data(data_dir)
        payload = inventory.model_dump()
        warnings = list(inventory.warnings)
        for vol in inventory.volumes:
            warnings.extend(vol.warnings)
        summary = (
            f"Found {len(payload.get('volumes', []))} local volume(s) "
            f"in {payload.get('data_dir')}."
        )
        return finalize(
            state,
            "inventory_agent",
            "success",
            {"local_data_inventory": payload},
            summary,
            input_keys=["parsed_request"],
            warnings=warnings,
        )
    except Exception as exc:  # noqa: BLE001
        # Non-"error" sentinel so the supervisor treats the step as done and
        # moves on to the report instead of looping.
        payload = {"data_dir": data_dir, "volumes": [], "scan_error": str(exc)}
        return finalize(
            state,
            "inventory_agent",
            "failed",
            {"local_data_inventory": payload},
            f"Local data scan failed: {exc}",
            input_keys=["parsed_request"],
            errors=[f"Local data scan failed: {exc}"],
        )
