"""Supervisor-based multi-agent LangGraph.

Topology::

    START → supervisor_agent
    supervisor_agent → (conditional) → agent → supervisor_agent
    supervisor_agent → END   (when next_agent == "finish")

The supervisor is the central router. *Every* agent — including the input
parser — is dispatched by the supervisor and returns to it, so all agent
functions go through a single uniform loop.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from mito_data_agent.agents.catalog_agent import catalog_agent
from mito_data_agent.agents.chat_agent import chat_agent
from mito_data_agent.agents.dataset_inspector_agent import dataset_inspector_agent
from mito_data_agent.agents.input_parser_agent import input_parser_agent
from mito_data_agent.agents.inventory_agent import inventory_agent
from mito_data_agent.agents.metadata_agent import metadata_agent
from mito_data_agent.agents.metadata_record_agent import metadata_record_agent
from mito_data_agent.agents.observation_agent import observation_agent
from mito_data_agent.agents.report_agent import report_agent
from mito_data_agent.agents.staging_agent import staging_agent
from mito_data_agent.agents.state import MultiAgentState, ROUTABLE_AGENTS
from mito_data_agent.agents.storage_info_agent import storage_info_agent
from mito_data_agent.agents.supervisor_agent import (
    SupervisorPolicy,
    make_supervisor_node,
    route_from_supervisor,
)
from mito_data_agent.agents.upload_planning_agent import upload_planning_agent
from mito_data_agent.agents.validation_agent import validation_agent
from mito_data_agent.agents.website_update_agent import website_update_agent

# Every agent the supervisor can dispatch — the parser is routed like the rest.
_AGENT_NODES = {
    "input_parser_agent": input_parser_agent,
    "dataset_inspector_agent": dataset_inspector_agent,
    "observation_agent": observation_agent,
    "metadata_agent": metadata_agent,
    "validation_agent": validation_agent,
    "metadata_record_agent": metadata_record_agent,
    "staging_agent": staging_agent,
    "upload_planning_agent": upload_planning_agent,
    "website_update_agent": website_update_agent,
    "inventory_agent": inventory_agent,
    "catalog_agent": catalog_agent,
    "storage_info_agent": storage_info_agent,
    "chat_agent": chat_agent,
    "report_agent": report_agent,
}


def build_multi_agent_graph(policy: SupervisorPolicy | None = None):
    """Compile the supervisor-routed multi-agent workflow.

    Args:
        policy: optional routing policy (defaults to the LLM-driven supervisor
            that picks the next agent via native function calling).
    """
    graph = StateGraph(MultiAgentState)

    graph.add_node("supervisor_agent", make_supervisor_node(policy))
    for name, fn in _AGENT_NODES.items():
        graph.add_node(name, fn)

    # The supervisor is the single entry point; it dispatches every agent.
    graph.add_edge(START, "supervisor_agent")

    conditional_map = {name: name for name in ROUTABLE_AGENTS}
    conditional_map["finish"] = END
    graph.add_conditional_edges(
        "supervisor_agent", route_from_supervisor, conditional_map
    )

    # Every agent returns to the supervisor.
    for name in _AGENT_NODES:
        graph.add_edge(name, "supervisor_agent")

    return graph.compile()
