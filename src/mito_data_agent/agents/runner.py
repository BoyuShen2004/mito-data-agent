"""Runner + trace formatting for the supervisor-based multi-agent workflow."""

from __future__ import annotations

from typing import Any

from mito_data_agent.agents.graph import build_multi_agent_graph
from mito_data_agent.agents.state import MultiAgentState
from mito_data_agent.agents.supervisor_agent import SupervisorPolicy
from mito_data_agent.tools.reporting import build_summary
from mito_data_agent.utils.ids import make_run_id
from mito_data_agent.utils.paths import ensure_output_dirs

# A supervisor loop over ~9 workers needs headroom above LangGraph's default (25).
_RECURSION_LIMIT = 60

_GRAPH = None


def _get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_multi_agent_graph()
    return _GRAPH


def reset_graph() -> None:
    """Drop the cached compiled graph (used by tests)."""
    global _GRAPH
    _GRAPH = None


def initial_multi_agent_state(user_prompt: str) -> MultiAgentState:
    """Build the initial multi-agent state."""
    return {
        "run_id": make_run_id(),
        "user_prompt": user_prompt,
        "current_agent": None,
        "next_agent": None,
        "supervisor_reason": None,
        "step": 0,
        "agent_trace": [],
        "supervisor_decisions": [],
        "parsed_request": None,
        "raw_file_path": None,
        "label_file_path": None,
        "metadata_file_path": None,
        "file_inspection": None,
        "volume_observation": None,
        "merged_metadata": None,
        "schema_validation": None,
        "metadata_record": None,
        "generated_artifacts": {},
        "hf_staging_dir": None,
        "mitoverse_update_files": [],
        "hf_upload_plan": None,
        "github_push_plan": None,
        "local_data_inventory": None,
        "mitoverse_lookup": None,
        "mitoverse_search": None,
        "storage_info": None,
        "final_report": None,
        "execution_report_path": None,
        "real_write_performed": False,
        "errors": [],
        "warnings": [],
    }


def executed_route(state: MultiAgentState) -> list[str]:
    """Reconstruct the node route: START → supervisor → agent → supervisor → …

    Every hop goes through the supervisor, so the route is just each supervisor
    decision (``supervisor_agent`` then its chosen ``next_agent``) in order.
    """
    route: list[str] = []
    for decision in state.get("supervisor_decisions", []) or []:
        route.append("supervisor_agent")
        route.append(decision["next_agent"])
    return route


def format_trace_lines(state: MultiAgentState) -> list[str]:
    """Interleave agent_trace and supervisor_decisions into ordered trace lines."""
    events: list[tuple[int, str]] = []
    for entry in state.get("agent_trace", []) or []:
        label = _agent_label(entry["agent"])
        events.append((entry["step"], f"[{label}] {entry.get('summary', entry['status'])}"))
    for dec in state.get("supervisor_decisions", []) or []:
        events.append(
            (dec["step"], f"[Supervisor] next_agent={dec['next_agent']}  ({dec.get('reason', '')})")
        )
    events.sort(key=lambda e: e[0])
    return [line for _, line in events]


def _agent_label(agent: str) -> str:
    return agent.replace("_agent", "").replace("_", " ").title() + " Agent"


def print_trace(state: MultiAgentState) -> None:
    """Print the human-readable supervisor/agent trace to stdout."""
    print("\n=== Multi-Agent Trace ===")
    for line in format_trace_lines(state):
        print(line)
    decisions = state.get("supervisor_decisions", []) or []
    agent_steps = state.get("agent_trace", []) or []
    print(f"\nSupervisor decisions: {len(decisions)} | Agent steps: {len(agent_steps)}")


def run_multi_agent(
    user_prompt: str,
    *,
    trace: bool = False,
    print_trace_output: bool = True,
    policy: SupervisorPolicy | None = None,
) -> dict[str, Any]:
    """Run the supervisor-based multi-agent workflow end-to-end.

    Args:
        user_prompt: the free-form user request.
        trace: when True, collect and (optionally) print the trace.
        print_trace_output: print the trace to stdout when ``trace`` is set.
        policy: optional supervisor policy override (compiles a fresh graph).
    """
    ensure_output_dirs()
    graph = build_multi_agent_graph(policy) if policy is not None else _get_graph()
    state = initial_multi_agent_state(user_prompt)

    result = graph.invoke(state, config={"recursion_limit": _RECURSION_LIMIT})

    if trace and print_trace_output:
        print_trace(result)

    return {
        "summary": build_summary(result),
        "raw": result,
        "trace": format_trace_lines(result),
    }
