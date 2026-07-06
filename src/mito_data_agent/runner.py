"""Shared agent runner for CLI and web UI."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from mito_data_agent.graph import build_graph
from mito_data_agent.utils.ids import make_run_id
from mito_data_agent.utils.trace import (
    format_trace_for_ui,
    iter_agent_trace_events,
    run_graph_with_trace,
)

_GRAPH = None


def _get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def initial_state(user_prompt: str) -> dict:
    """Build the initial ReAct agent state."""
    return {
        "run_id": make_run_id(),
        "user_prompt": user_prompt,
        "messages": [],
        "artifacts": {},
        "step_count": 0,
        "execution_report_path": None,
        "errors": [],
    }


def _final_assistant_text(result: dict) -> str:
    for msg in reversed(result.get("messages") or []):
        if isinstance(msg, AIMessage) and msg.content and not (msg.tool_calls or []):
            return msg.content
    return "Agent finished but produced no final message."


STUB_TOOL_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("generate_hf_staging_plan", "generate_hf_staging"),
    ("generate_mitoverse_update_plan", "generate_mitoverse_update"),
    ("hf_upload_plan", "pseudo_upload_hf"),
    ("github_push_plan", "pseudo_push_github"),
    ("execution_report_plan", "write_execution_report"),
)


def _collect_stub_tool_signals(artifacts: dict) -> list[dict[str, Any]]:
    """Summarize stub tools that ran and their ok/failed signal."""
    signals: list[dict[str, Any]] = []
    for artifact_key, tool_name in STUB_TOOL_ARTIFACTS:
        plan = artifacts.get(artifact_key)
        if not plan:
            continue
        signals.append(
            {
                "tool": tool_name,
                "executed": plan.get("executed", True),
                "signal": plan.get("signal", "ok" if plan.get("success") else "failed"),
                "success": plan.get("success"),
                "mode": plan.get("mode", "pseudo"),
                "real_write_performed": plan.get("real_write_performed", False),
                "target": plan.get("target"),
            }
        )
    return signals


def _collect_pseudo_tool_signals(artifacts: dict) -> list[dict[str, Any]]:
    """Backward-compatible alias — all stub tools (local + pseudo)."""
    return _collect_stub_tool_signals(artifacts)


def build_summary(result: dict) -> dict[str, Any]:
    """Turn raw graph output into a structured summary for CLI / web."""
    artifacts = result.get("artifacts") or {}
    merged = artifacts.get("merged_metadata") or {}
    validation = artifacts.get("schema_validation") or {}
    hf_plan = artifacts.get("hf_upload_plan") or {}
    gh_plan = artifacts.get("github_push_plan") or {}
    tools_used = _tool_message_names(result.get("messages"))

    return {
        "run_id": result.get("run_id"),
        "intent": "agent_react",
        "execution_report_path": result.get("execution_report_path")
        or artifacts.get("execution_report_path"),
        "hf_staging_dir": artifacts.get("hf_staging_dir"),
        "mitoverse_update_files": artifacts.get("mitoverse_update_files", []),
        "validation_success": validation.get("success"),
        "validation_message": validation.get("message"),
        "missing_fields": validation.get("missing_fields", []),
        "resolution_nm": merged.get("resolution_nm"),
        "resolution_source": merged.get("resolution_source"),
        "shape_xyz": merged.get("shape_xyz"),
        "shape_source": merged.get("shape_source"),
        "num_mito": merged.get("num_mito"),
        "num_mito_source": merged.get("num_mito_source"),
        "volume": merged.get("volume"),
        "hf_upload_success": hf_plan.get("success") if hf_plan else None,
        "hf_real_write": hf_plan.get("real_write_performed") if hf_plan else None,
        "github_push_success": gh_plan.get("success") if gh_plan else None,
        "github_real_write": gh_plan.get("real_write_performed") if gh_plan else None,
        "pseudo_tool_signals": _collect_stub_tool_signals(artifacts),
        "stub_tool_signals": _collect_stub_tool_signals(artifacts),
        "warnings": merged.get("warnings", []) if isinstance(merged.get("warnings"), list) else [],
        "errors": result.get("errors", []),
        "local_data_inventory": artifacts.get("local_data_inventory"),
        "mitoverse_lookup": artifacts.get("mitoverse_lookup"),
        "mitoverse_search": artifacts.get("mitoverse_search"),
        "mitoverse_datasets": artifacts.get("mitoverse_datasets"),
        "mitoverse_catalog_snapshot": artifacts.get("mitoverse_catalog_snapshot"),
        "agent_steps": result.get("step_count", 0),
        "tools_used": tools_used,
        "final_answer": _final_assistant_text(result),
    }


def _tool_message_names(messages) -> list[str]:
    return [getattr(m, "name", "") for m in messages or [] if getattr(m, "type", None) == "tool"]


def format_assistant_message(summary: dict, *, trace: list[dict] | None = None) -> str:
    """Format chat response — prefer the agent's final LLM answer."""
    lines = [
        f"**Run ID:** `{summary.get('run_id')}`",
        f"**Agent steps:** {summary.get('agent_steps', 0)} tool round(s)",
    ]
    if summary.get("tools_used"):
        lines.append(f"**Tools used:** {', '.join(summary['tools_used'])}")

    lines.append("")
    lines.append(summary.get("final_answer") or "_No final answer._")

    if summary.get("execution_report_path"):
        lines.append(f"\n**Report:** `{summary['execution_report_path']}`")

    pseudo_signals = summary.get("stub_tool_signals") or summary.get("pseudo_tool_signals") or []
    if pseudo_signals:
        lines.append("\n**Stub tools:**")
        for item in pseudo_signals:
            mark = "✓" if item.get("signal") == "ok" else "✗"
            mode = item.get("mode", "pseudo")
            note = "local outputs only" if mode == "local" else "pseudo, no real write"
            lines.append(
                f"- {mark} `{item['tool']}` — signal=`{item.get('signal')}` "
                f"(executed, {note})"
            )

    if trace:
        lines.append(f"\n**LangGraph trace:** {len(trace)} node(s)")
        for step in trace:
            lines.append(f"- `{step['node']}`")

    lines.append("\n_Artifacts written under outputs/ when applicable._")
    return "\n".join(lines)


def run_agent(
    user_prompt: str,
    *,
    trace: bool = False,
    print_trace: bool = True,
) -> dict[str, Any]:
    """Run the ReAct LangGraph agent."""
    graph = _get_graph()
    state = initial_state(user_prompt)

    steps: list[dict] = []
    if trace:
        result, steps = run_graph_with_trace(graph, state, print_steps=print_trace)
    else:
        result = graph.invoke(state)

    summary = build_summary(result)
    return {
        "summary": summary,
        "message": format_assistant_message(summary, trace=steps if trace else None),
        "raw": result,
        "trace": steps,
        "trace_text": format_trace_for_ui(steps) if steps else None,
    }


def run_agent_stream(user_prompt: str):
    """Yield step events, then a final done event (same payload as /api/chat)."""
    graph = _get_graph()
    state = initial_state(user_prompt)

    for event in iter_agent_trace_events(graph, state):
        if event["type"] == "step":
            yield event
        elif event["type"] == "result":
            result = event["state"]
            summary = build_summary(result)
            yield {
                "type": "done",
                "message": format_assistant_message(summary, trace=None),
                "summary": summary,
            }
