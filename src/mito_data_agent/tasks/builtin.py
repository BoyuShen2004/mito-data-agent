"""Built-in task definitions."""

from __future__ import annotations

from mito_data_agent.tasks.registry import TaskSpec, register_task
from mito_data_agent.tasks.result_formatters import format_list_local_data


def register_builtin_tasks() -> None:
    """Register all stock tasks. Safe to call multiple times if registry was cleared."""
    from mito_data_agent.tasks.registry import get_task

    if get_task("list_local_data"):
        return

    register_task(
        TaskSpec(
            intent="list_local_data",
            description="list/browse annotated volumes already on disk (local data dir)",
            entry_node="list_local_data",
            examples=(
                "what data do I have",
                "list my volumes",
                "show local datasets",
                "what is in mito_data_agent_data",
            ),
            terminal_edges=(("list_local_data", "write_local_data_report"),),
            format_result=format_list_local_data,
        )
    )

    register_task(
        TaskSpec(
            intent="upload_annotation",
            description="upload/prepare HF staging and/or update MitoVerse for an annotated volume",
            entry_node="inspect_uploaded_files",
            examples=(
                "upload this annotation",
                "prepare HF upload",
                "update MitoVerse",
            ),
            post_validation="upload_valid",
        )
    )

    register_task(
        TaskSpec(
            intent="metadata_only_update",
            description="update MitoVerse metadata row only, no file upload",
            entry_node="merge_prompt_and_file_metadata",
            examples=("only update metadata row", "metadata only"),
            post_validation="metadata_valid",
            skip_hf_upload=True,
        )
    )

    register_task(
        TaskSpec(
            intent="check_upload_readiness",
            description="inspect/validate files and metadata readiness only (no upload)",
            entry_node="inspect_uploaded_files",
            examples=("check if this is ready", "validate files", "upload readiness"),
            post_validation="readiness_report",
            post_validation_always=True,
        )
    )

    register_task(
        TaskSpec(
            intent="unsupported_request",
            description="placeholder for routing unsupported prompts to a report",
            entry_node="write_unsupported_report",
        )
    )
