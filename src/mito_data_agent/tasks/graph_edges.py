"""Register shared and task-specific LangGraph edges."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from mito_data_agent.tasks.registry import get_all_tasks


def register_graph_edges(graph: StateGraph) -> None:
    """Wire edges that are shared across tasks or declared on TaskSpec."""
    # File observation pipeline (upload + readiness).
    graph.add_edge("inspect_uploaded_files", "extract_volume_observations")
    graph.add_edge("extract_volume_observations", "merge_prompt_and_file_metadata")
    graph.add_edge("merge_prompt_and_file_metadata", "validate_required_columns")

    # Post-validation routes (keys resolved in nodes.route_post_validation).
    graph.add_conditional_edges(
        "validate_required_columns",
        _route_post_validation,
        {
            "upload_valid": "generate_hf_staging_files",
            "metadata_valid": "generate_mitoverse_update_files",
            "readiness_report": "write_readiness_report",
            "missing_fields": "write_missing_fields_report",
        },
    )

    graph.add_edge("generate_hf_staging_files", "generate_mitoverse_update_files")
    graph.add_conditional_edges(
        "generate_mitoverse_update_files",
        _route_after_mitoverse_update,
        {
            "do_hf_upload": "pseudo_upload_to_hf",
            "skip_hf_upload": "pseudo_push_to_github",
        },
    )
    graph.add_edge("pseudo_upload_to_hf", "pseudo_push_to_github")
    graph.add_edge("pseudo_push_to_github", "write_execution_report")

    # Terminal nodes.
    for end_node in (
        "write_execution_report",
        "write_missing_fields_report",
        "write_error_report",
        "write_unsupported_report",
        "write_readiness_report",
        "write_local_data_report",
    ):
        graph.add_edge(end_node, END)

    # Per-task linear tails (e.g. list_local_data → write_local_data_report).
    for spec in get_all_tasks():
        for src, dst in spec.terminal_edges:
            if dst == "__end__":
                graph.add_edge(src, END)
            else:
                graph.add_edge(src, dst)


def _route_post_validation(state):
    from mito_data_agent.nodes import route_post_validation

    return route_post_validation(state)


def _route_after_mitoverse_update(state):
    from mito_data_agent.nodes import route_after_mitoverse_update

    return route_after_mitoverse_update(state)
