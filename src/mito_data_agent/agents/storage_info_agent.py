"""Storage info agent — answer "where do you keep things?" questions.

Reports the concrete locations the agent uses (metadata store, data-dir sidecars,
outputs directories) and what volumes have been recorded so far. Read-only.
"""

from __future__ import annotations

from mito_data_agent.agents.base import finalize
from mito_data_agent.agents.state import MultiAgentState
from mito_data_agent.tools import metadata_store
from mito_data_agent.utils.paths import get_outputs_dir, to_relative_path


def storage_info_agent(state: MultiAgentState) -> dict:
    """Collect where the agent stores metadata, data sidecars, and outputs."""
    records = metadata_store.list_records()
    sidecar_dir = metadata_store.get_sidecar_dir()
    outputs = get_outputs_dir()
    store_path = metadata_store.get_store_path()

    info = {
        "metadata_store": to_relative_path(store_path),
        "metadata_store_abs": str(store_path),
        "data_dir_sidecars": to_relative_path(sidecar_dir) if sidecar_dir else None,
        "data_dir_abs": str(sidecar_dir) if sidecar_dir else None,
        "outputs_dir": to_relative_path(outputs),
        "execution_reports_dir": to_relative_path(outputs / "execution_reports"),
        "hf_staging_dir": to_relative_path(outputs / "hf_staging"),
        "mitoverse_updates_dir": to_relative_path(outputs / "mitoverse_updates"),
        "recorded_count": len(records),
        "recorded_volumes": [r.get("volume") for r in records],
    }
    summary = (
        f"Storage: metadata store at {info['metadata_store']}, "
        f"sidecars in {info['data_dir_sidecars']}, "
        f"{info['recorded_count']} volume(s) recorded."
    )
    return finalize(
        state,
        "storage_info_agent",
        "success",
        {"storage_info": info},
        summary,
        input_keys=["parsed_request"],
    )
