"""Catalog agent — wraps the read-only MitoVerse catalog lookup/search tools."""

from __future__ import annotations

from mito_data_agent.agents.base import finalize
from mito_data_agent.agents.state import MultiAgentState
from mito_data_agent.tools.lookup_mitoverse_volume import lookup_mitoverse_volume_tool
from mito_data_agent.tools.search_mitoverse_collection import search_mitoverse_collection_tool


def catalog_agent(state: MultiAgentState) -> dict:
    """Look up / search whether a volume exists in the public MitoVerse catalog.

    Read-only. Network failures (offline, disabled lookup) degrade gracefully to
    a non-error sentinel so the supervisor still routes to the report.
    """
    parsed = state.get("parsed_request") or {}
    volume = parsed.get("volume")
    dataset = parsed.get("dataset")
    raw_path = state.get("raw_file_path")
    label_path = state.get("label_file_path")

    try:
        lookup = lookup_mitoverse_volume_tool(
            volume=volume,
            dataset=dataset,
            raw_file_path=raw_path,
            label_file_path=label_path,
        )
        lookup_payload = lookup.model_dump()
        outputs: dict = {"mitoverse_lookup": lookup_payload}

        # A broader search adds context when the exact volume is not found.
        try:
            search = search_mitoverse_collection_tool(
                volume=volume, dataset=dataset,
                raw_file_path=raw_path, label_file_path=label_path,
            )
            outputs["mitoverse_search"] = search.model_dump()
            match_count = search.match_count
        except Exception:  # noqa: BLE001 — search is best-effort
            match_count = 0

        summary = (
            f"MitoVerse catalog lookup: found={lookup.found} "
            f"({match_count} related match(es))."
        )
        return finalize(
            state,
            "catalog_agent",
            "success",
            outputs,
            summary,
            input_keys=["parsed_request", "raw_file_path", "label_file_path"],
        )
    except Exception as exc:  # noqa: BLE001
        # ``lookup_error`` (not ``error``) so the supervisor advances to report.
        payload = {"found": False, "lookup_error": str(exc), "query": {"volume": volume}}
        return finalize(
            state,
            "catalog_agent",
            "failed",
            {"mitoverse_lookup": payload},
            f"MitoVerse catalog lookup unavailable: {exc}",
            input_keys=["parsed_request"],
            warnings=[f"MitoVerse catalog lookup unavailable: {exc}"],
        )
