"""ReAct LangGraph: llm → tools → llm … until done (Andrew Ng pattern).

This IS LangGraph — StateGraph with nodes, edges, and shared AgentState.
ReAct (Reason + Act) is the orchestration pattern inside the graph, not a
replacement for LangGraph.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from mito_data_agent.agent.nodes import (
    call_llm_node,
    should_continue,
    take_action_node,
    validate_input_node,
)
from mito_data_agent.agent.state import AgentState


def build_graph():
    """Build the tool-calling agent graph."""
    graph = StateGraph(AgentState)

    graph.add_node("validate_input", validate_input_node)
    graph.add_node("llm", call_llm_node)
    graph.add_node("action", take_action_node)

    graph.add_edge(START, "validate_input")
    graph.add_edge("validate_input", "llm")
    graph.add_conditional_edges(
        "llm",
        should_continue,
        {"continue": "action", "end": END},
    )
    graph.add_edge("action", "llm")

    return graph.compile()
