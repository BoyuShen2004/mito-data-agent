"""Shared state for the supervisor-based multi-agent workflow.

This state is a superset of the legacy ``UploadAgentState`` fields plus the
multi-agent trace channels (``agent_trace``, ``supervisor_decisions``) and the
supervisor routing fields (``current_agent``, ``next_agent``,
``supervisor_reason``). Worker agents read the fields they need and return
partial updates; the supervisor reads the whole state to decide the next hop.
"""

from __future__ import annotations

from typing import Optional, TypedDict

# The task worker agents (everything after parsing).
WORKER_AGENTS: list[str] = [
    "dataset_inspector_agent",
    "observation_agent",
    "metadata_agent",
    "validation_agent",
    "metadata_record_agent",
    "staging_agent",
    "upload_planning_agent",
    "website_update_agent",
    "inventory_agent",
    "catalog_agent",
    "storage_info_agent",
    "report_agent",
]

# Every agent the supervisor dispatches — the parser is routed like any other,
# so *all* agent functions go through the supervisor for a uniform loop.
ROUTABLE_AGENTS: list[str] = ["input_parser_agent", *WORKER_AGENTS]

# The full allow-list the supervisor may emit as ``next_agent``.
ALLOWED_NEXT_AGENTS: list[str] = [*ROUTABLE_AGENTS, "finish"]


class MultiAgentState(TypedDict, total=False):
    """State passed between the supervisor and worker agents.

    ``total=False`` keeps every field optional so agents can return small
    partial updates that LangGraph merges into the running state.
    """

    run_id: str
    user_prompt: str

    # Supervisor routing bookkeeping.
    current_agent: Optional[str]
    next_agent: Optional[str]
    supervisor_reason: Optional[str]

    # Monotonic step counter shared by agents and supervisor.
    step: int
    agent_trace: list[dict]
    supervisor_decisions: list[dict]

    # Work products (mirror of the legacy pipeline fields for tool reuse).
    parsed_request: Optional[dict]
    raw_file_path: Optional[str]
    label_file_path: Optional[str]
    metadata_file_path: Optional[str]

    file_inspection: Optional[dict]
    volume_observation: Optional[dict]
    merged_metadata: Optional[dict]
    schema_validation: Optional[dict]
    metadata_record: Optional[dict]

    generated_artifacts: dict
    hf_staging_dir: Optional[str]
    mitoverse_update_files: list[str]

    hf_upload_plan: Optional[dict]
    github_push_plan: Optional[dict]

    # Read-only capabilities (local inventory + MitoVerse catalog).
    local_data_inventory: Optional[dict]
    mitoverse_lookup: Optional[dict]
    mitoverse_search: Optional[dict]
    storage_info: Optional[dict]

    final_report: Optional[str]
    execution_report_path: Optional[str]

    # Safety flag — this workflow never performs real external writes.
    real_write_performed: bool

    errors: list[dict]
    warnings: list[dict]
