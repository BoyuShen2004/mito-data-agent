"""Shared LangGraph state for the Mito Data Agent."""

from __future__ import annotations

from typing import Optional, TypedDict


class UploadAgentState(TypedDict):
    """State passed between graph nodes.

    Key objects:
    - parsed_request: structured fields extracted from the user prompt.
    - file_inspection: low-level existence/shape checks on raw and label files.
    - volume_observation: extracted Resolution, Shape, and # Mito from files.
    - merged_metadata: combined prompt + file observations before validation.
    - schema_validation: whether merged_metadata satisfies required columns.
    - hf_upload_plan / github_push_plan: stub tool results (no external API calls).
    """

    run_id: str
    user_prompt: str

    parsed_request: Optional[dict]
    raw_file_path: Optional[str]
    label_file_path: Optional[str]
    metadata_file_path: Optional[str]

    file_inspection: Optional[dict]
    volume_observation: Optional[dict]
    merged_metadata: Optional[dict]
    schema_validation: Optional[dict]

    hf_staging_dir: Optional[str]
    mitoverse_update_files: list[str]

    hf_upload_plan: Optional[dict]
    github_push_plan: Optional[dict]

    execution_report_path: Optional[str]

    local_data_inventory: Optional[dict]

    errors: list[str]
    warnings: list[str]
