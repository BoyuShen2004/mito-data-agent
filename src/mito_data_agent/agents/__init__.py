"""Supervisor-based multi-agent LangGraph workflow.

Public surface:
    build_multi_agent_graph  — compile the supervisor-routed graph.
    run_multi_agent          — run it end-to-end and return a summary + trace.
    ALLOWED_NEXT_AGENTS      — the supervisor's routing allow-list.
    LLMSupervisor            — default LLM-driven routing policy.
"""

from __future__ import annotations

from mito_data_agent.agents.graph import build_multi_agent_graph
from mito_data_agent.agents.registry import AGENT_CATALOG
from mito_data_agent.agents.runner import (
    build_summary,
    executed_route,
    initial_multi_agent_state,
    reset_graph,
    run_multi_agent,
)
from mito_data_agent.agents.state import (
    ALLOWED_NEXT_AGENTS,
    ROUTABLE_AGENTS,
    WORKER_AGENTS,
    MultiAgentState,
)
from mito_data_agent.agents.supervisor_agent import (
    SupervisorPolicy,
    make_supervisor_node,
)
from mito_data_agent.agents.supervisor_llm import (
    LLMSupervisor,
    get_supervisor_model,
)

__all__ = [
    "build_multi_agent_graph",
    "run_multi_agent",
    "build_summary",
    "executed_route",
    "initial_multi_agent_state",
    "reset_graph",
    "AGENT_CATALOG",
    "ALLOWED_NEXT_AGENTS",
    "ROUTABLE_AGENTS",
    "WORKER_AGENTS",
    "MultiAgentState",
    "LLMSupervisor",
    "SupervisorPolicy",
    "get_supervisor_model",
    "make_supervisor_node",
]
