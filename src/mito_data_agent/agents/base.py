"""Shared helpers for worker agents: step counting, trace, and error/warning logs.

Every worker agent finishes by calling :func:`finalize`, which stamps the
``agent_trace`` entry, advances the shared ``step`` counter, and folds any new
warnings/errors into the running state. Keeping this in one place guarantees the
trace shape is identical across agents.
"""

from __future__ import annotations

from typing import Any, Iterable

from mito_data_agent.agents.state import MultiAgentState


def next_step(state: MultiAgentState) -> int:
    """Return the next monotonic step number for this run."""
    return int(state.get("step", 0)) + 1


def _log_entries(
    state: MultiAgentState, key: str, agent: str, messages: Iterable[str]
) -> list[dict]:
    """Append ``{agent, message}`` records to an existing error/warning log."""
    existing = list(state.get(key, []) or [])
    for msg in messages:
        existing.append({"agent": agent, "message": str(msg)})
    return existing


def finalize(
    state: MultiAgentState,
    agent: str,
    status: str,
    outputs: dict[str, Any],
    summary: str,
    *,
    input_keys: Iterable[str] | None = None,
    details: Iterable[str] | None = None,
    warnings: Iterable[str] | None = None,
    errors: Iterable[str] | None = None,
    conflicts: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build a worker agent's state update with a trace entry attached.

    Args:
        state: current graph state (read-only).
        agent: the worker agent name.
        status: ``"success" | "failed" | "skipped"``.
        outputs: the work-product fields this agent writes (e.g. ``file_inspection``).
        summary: one-line human-readable summary for the trace.
        input_keys: state keys the agent read.
        details: component-level sub-steps (tool calls / decisions) for the trace.
        warnings/errors: new messages to fold into the shared logs.
        conflicts: prompt/data mismatches auto-resolved in favour of the file.
            These are informational (not warnings/errors) and feed the trace.
    """
    step = next_step(state)
    warnings = list(warnings or [])
    errors = list(errors or [])
    details = [str(d) for d in (details or [])]
    conflicts = [str(c) for c in (conflicts or [])]

    update: dict[str, Any] = dict(outputs)
    update["current_agent"] = agent
    update["step"] = step

    if warnings:
        update["warnings"] = _log_entries(state, "warnings", agent, warnings)
    if errors:
        update["errors"] = _log_entries(state, "errors", agent, errors)
    if conflicts:
        update["conflicts"] = _log_entries(state, "conflicts", agent, conflicts)

    entry = {
        "step": step,
        "agent": agent,
        "status": status,
        "input_keys": list(input_keys or []),
        "output_keys": list(outputs.keys()),
        "summary": summary,
        "details": details + [f"conflict resolved (file wins): {c}" for c in conflicts],
        "errors": [str(e) for e in errors],
    }
    update["agent_trace"] = list(state.get("agent_trace", []) or []) + [entry]
    return update
