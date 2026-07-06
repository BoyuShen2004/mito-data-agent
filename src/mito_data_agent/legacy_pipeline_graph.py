"""Legacy fixed-pipeline LangGraph (pre-ReAct). Kept for reference/tests."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from mito_data_agent.nodes import (
    extract_volume_observations_node,
    generate_hf_staging_files_node,
    generate_mitoverse_update_files_node,
    inspect_uploaded_files_node,
    list_local_data_node,
    merge_prompt_and_file_metadata_node,
    parse_user_prompt_node,
    pseudo_push_to_github_node,
    pseudo_upload_to_hf_node,
    route_after_parse,
    validate_input_node,
    validate_required_columns_node,
    write_error_report_node,
    write_execution_report_node,
    write_local_data_report_node,
    write_missing_fields_report_node,
    write_readiness_report_node,
    write_unsupported_report_node,
)
from mito_data_agent.state import UploadAgentState
from mito_data_agent.tasks import get_parse_routes, register_builtin_tasks
from mito_data_agent.tasks.graph_edges import register_graph_edges


def build_legacy_graph():
    """Build the old intent-routed pipeline graph."""
    register_builtin_tasks()

    graph = StateGraph(UploadAgentState)

    graph.add_node("validate_input", validate_input_node)
    graph.add_node("parse_user_prompt", parse_user_prompt_node)
    graph.add_node("inspect_uploaded_files", inspect_uploaded_files_node)
    graph.add_node("extract_volume_observations", extract_volume_observations_node)
    graph.add_node("merge_prompt_and_file_metadata", merge_prompt_and_file_metadata_node)
    graph.add_node("validate_required_columns", validate_required_columns_node)
    graph.add_node("generate_hf_staging_files", generate_hf_staging_files_node)
    graph.add_node("generate_mitoverse_update_files", generate_mitoverse_update_files_node)
    graph.add_node("pseudo_upload_to_hf", pseudo_upload_to_hf_node)
    graph.add_node("pseudo_push_to_github", pseudo_push_to_github_node)
    graph.add_node("write_execution_report", write_execution_report_node)
    graph.add_node("write_missing_fields_report", write_missing_fields_report_node)
    graph.add_node("write_error_report", write_error_report_node)
    graph.add_node("write_unsupported_report", write_unsupported_report_node)
    graph.add_node("write_readiness_report", write_readiness_report_node)
    graph.add_node("list_local_data", list_local_data_node)
    graph.add_node("write_local_data_report", write_local_data_report_node)

    graph.add_edge(START, "validate_input")
    graph.add_edge("validate_input", "parse_user_prompt")

    parse_routes = {"parse_error": "write_error_report", **get_parse_routes()}
    graph.add_conditional_edges("parse_user_prompt", route_after_parse, parse_routes)

    register_graph_edges(graph)

    return graph.compile()
