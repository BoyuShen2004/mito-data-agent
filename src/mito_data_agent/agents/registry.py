"""Agent catalog + shared state-inspection helpers for the supervisor.

The catalog is the menu the (LLM) supervisor picks from. There are no hardcoded
routes or keyword rules here — the supervisor reasons over the catalog and the
current progress to choose the next agent.
"""

from __future__ import annotations

from mito_data_agent.agents.state import MultiAgentState

# One-line description of each dispatchable agent, shown to the LLM supervisor.
AGENT_CATALOG: dict[str, str] = {
    "input_parser_agent": "Parse the user's free-form prompt into structured fields. Must run first.",
    "dataset_inspector_agent": "Inspect the raw/label TIFF files on disk (existence, shape, dtype).",
    "observation_agent": "Extract Resolution, Shape, and # Mito from the files (label preferred).",
    "metadata_agent": "Merge prompt metadata with file observations into one record.",
    "validation_agent": "Validate the merged metadata against required MitoVerse columns.",
    "metadata_record_agent": "Save the parsed/validated metadata to the persistent local store for later query/update. Run after validation, before the report, whenever there is metadata.",
    "staging_agent": "Generate Hugging Face staging + MitoVerse update artifacts (dry-run).",
    "upload_planning_agent": "Produce a pseudo Hugging Face upload plan (dry-run, no real write).",
    "website_update_agent": "Produce a pseudo GitHub website update plan (dry-run, no real write).",
    "inventory_agent": "Scan the local data directory and list annotated volumes on disk.",
    "catalog_agent": "Check whether a volume already exists in the public MitoVerse catalog (read-only).",
    "storage_info_agent": "Answer questions about WHERE the agent stores things (metadata store path, data-dir sidecars, outputs) and WHAT volumes have been recorded so far.",
    "report_agent": "Assemble the final report and write the execution report. Run last.",
}


def is_missing(value) -> bool:
    """A field counts as missing if it is None/empty or an error sentinel dict."""
    if value is None:
        return True
    if isinstance(value, dict) and value.get("error"):
        return True
    return False


def artifacts_incomplete(state: MultiAgentState) -> bool:
    """Whether staging artifacts still need to be generated."""
    artifacts = state.get("generated_artifacts") or {}
    if not artifacts or artifacts.get("error"):
        return True
    return not artifacts.get("complete", False)


def progress_snapshot(state: MultiAgentState) -> dict[str, bool]:
    """Boolean map of which work products are already available.

    This is the factual context the supervisor reasons over — no routing
    decisions are encoded here.
    """
    return {
        "parsed_request": not is_missing(state.get("parsed_request")),
        "file_inspection": not is_missing(state.get("file_inspection")),
        "volume_observation": not is_missing(state.get("volume_observation")),
        "merged_metadata": not is_missing(state.get("merged_metadata")),
        "schema_validation": not is_missing(state.get("schema_validation")),
        "metadata_record": not is_missing(state.get("metadata_record")),
        "generated_artifacts": not artifacts_incomplete(state),
        "hf_upload_plan": not is_missing(state.get("hf_upload_plan")),
        "github_push_plan": not is_missing(state.get("github_push_plan")),
        "local_data_inventory": not is_missing(state.get("local_data_inventory")),
        "mitoverse_lookup": not is_missing(state.get("mitoverse_lookup")),
        "storage_info": not is_missing(state.get("storage_info")),
        "final_report": not is_missing(state.get("final_report")),
    }
