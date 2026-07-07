"""Metadata record agent — flow only.

The mechanical work (collecting every dataset in the request, keying each to its
on-disk file, reconciling file-vs-prompt conflicts, and writing the ledger entry
+ data-dir sidecar) lives in ``tools/record_datasets.py``. This agent just runs
that tool and folds the result into the trace.
"""

from __future__ import annotations

from mito_data_agent.agents.base import finalize
from mito_data_agent.agents.state import MultiAgentState
from mito_data_agent.tools.record_datasets import record_datasets


def metadata_record_agent(state: MultiAgentState) -> dict:
    """Record every volume's metadata to the store + a data-dir sidecar."""
    result = record_datasets(state)
    record = result["metadata_record"]
    conflicts = result["conflicts"]
    errors = result["errors"]

    if not record.get("recorded") and not errors:
        return finalize(
            state,
            "metadata_record_agent",
            "skipped",
            {"metadata_record": record},
            "No metadata to record.",
            input_keys=["merged_metadata", "parsed_request"],
        )

    names = ", ".join(v["volume"] for v in record.get("volumes", [])) or "none"
    summary = f"Recorded {record.get('count', 0)} volume(s) to store + data dir: {names}."
    if conflicts:
        summary += f" ({len(conflicts)} prompt/data conflict(s) auto-resolved in favor of data.)"

    status = "failed" if errors and not record.get("recorded") else "success"
    return finalize(
        state,
        "metadata_record_agent",
        status,
        {"metadata_record": record},
        summary,
        input_keys=["merged_metadata", "parsed_request", "schema_validation"],
        details=result["details"],
        conflicts=conflicts,
        errors=errors,
    )
