"""Pretty-print LangGraph step-by-step trace (Andrew Ng / LangGraph tutorial style)."""

from __future__ import annotations

import json
from typing import Any, Callable, TextIO


# Human-readable notes shown under each node in trace output.
NODE_DESCRIPTIONS: dict[str, str] = {
    "validate_input": "Validate input and create output directories",
    "llm": "Call LLM with tools — decide next action",
    "action": "Execute tool calls and append observations",
    "parse_user_prompt": "Parse annotator prompt (legacy pipeline)",
    "inspect_uploaded_files": "Check raw/label TIFF existence and shapes",
    "extract_volume_observations": "Extract Resolution, Shape, and # Mito from files",
    "merge_prompt_and_file_metadata": "Merge prompt metadata with file observations",
    "validate_required_columns": "Validate required MitoVerse columns",
    "generate_hf_staging_files": "Write Hugging Face staging artifacts",
    "generate_mitoverse_update_files": "Write MitoVerse row JSON/CSV/patch",
    "pseudo_upload_to_hf": "Plan HF upload (stub tool)",
    "pseudo_push_to_github": "Plan GitHub PR (stub tool)",
    "write_execution_report": "Write final execution report",
    "write_missing_fields_report": "Write report for missing required fields",
    "write_readiness_report": "Write upload readiness report",
    "list_local_data": "Scan local data directory for TIFF volumes",
    "fetch_mitoverse_catalog": "Fetch/cache public MitoVerse catalog",
    "lookup_mitoverse_volume": "Check if volume exists in MitoVerse",
    "search_mitoverse_collection": "Search MitoVerse catalog with hints",
    "list_mitoverse_datasets": "List MitoVerse dataset groups",
    "write_local_data_report": "Write local data inventory report",
    "write_unsupported_report": "Write unsupported-request report",
}


def _routing_hint(node: str, update: dict[str, Any]) -> str | None:
    """Infer routing decisions from node outputs."""
    if node == "parse_user_prompt":
        intent = (update.get("parsed_request") or {}).get("intent")
        return f"Route intent → {intent}" if intent else None
    if node == "llm":
        last = (update.get("messages") or [])[-1] if update.get("messages") else None
        if last and getattr(last, "tool_calls", None):
            names = [tc["name"] for tc in last.tool_calls]
            return f"Tool calls → {', '.join(names)}"
        return "No tool calls — finish"
    if node == "action":
        msgs = update.get("messages") or []
        if msgs:
            return f"Observations returned ({len(msgs)} tool message(s))"
    if node == "validate_required_columns":
        validation = update.get("schema_validation") or {}
        if validation.get("success"):
            parsed_intent = None  # not in this update
            return "Route after validation → valid path"
        return "Route after validation → missing_fields"
    return None


def _compact_value(value: Any, max_len: int = 1200) -> Any:
    """Make large values readable in trace output."""
    if isinstance(value, str) and len(value) > 200:
        return value[:200] + f"... ({len(value)} chars total)"
    try:
        text = json.dumps(value, indent=2, default=str)
    except TypeError:
        text = str(value)
    if len(text) > max_len:
        return text[:max_len] + f"\n... (truncated, {len(text)} chars total)"
    if isinstance(value, (dict, list)):
        return json.loads(text) if len(text) <= max_len else text
    return value


def serialize_update(update: dict[str, Any]) -> dict[str, Any]:
    """JSON-safe view of a node update (for streaming to the Web UI)."""
    from langchain_core.messages import BaseMessage

    out: dict[str, Any] = {}
    for key, value in update.items():
        if key == "messages" and isinstance(value, list):
            serialized = []
            for msg in value:
                if isinstance(msg, BaseMessage):
                    entry: dict[str, Any] = {"type": msg.type}
                    if msg.content:
                        text = str(msg.content)
                        entry["content"] = text[:800] + "…" if len(text) > 800 else text
                    if getattr(msg, "tool_calls", None):
                        entry["tool_calls"] = msg.tool_calls
                    if getattr(msg, "name", None):
                        entry["name"] = msg.name
                    serialized.append(entry)
                else:
                    serialized.append(_compact_value(msg))
            out[key] = serialized
        else:
            out[key] = _compact_value(value)
    return out


def format_trace_step(step: int, node: str, update: dict[str, Any]) -> str:
    """Format one LangGraph node update as readable text."""
    lines = [
        "",
        "═" * 60,
        f" Step {step} │ Node: {node}",
    ]
    desc = NODE_DESCRIPTIONS.get(node)
    if desc:
        lines.append(f"         │ {desc}")
    hint = _routing_hint(node, update)
    if hint:
        lines.append(f"         │ {hint}")
    lines.append("═" * 60)

    if not update:
        lines.append(" (no state update)")
    else:
        for key, value in update.items():
            compact = _compact_value(value)
            if isinstance(compact, str) and "\n" in compact:
                lines.append(f" {key}:")
                for subline in compact.splitlines():
                    lines.append(f"   {subline}")
            else:
                lines.append(f" {key}: {json.dumps(compact, default=str) if not isinstance(compact, str) else compact}")

    return "\n".join(lines)


def print_trace_step(
    step: int,
    node: str,
    update: dict[str, Any],
    *,
    stream: TextIO | None = None,
) -> None:
    """Print one trace step to stdout (or another stream)."""
    out = stream or __import__("sys").stdout
    out.write(format_trace_step(step, node, update) + "\n")
    out.flush()


def run_graph_with_trace(
    graph,
    state: dict[str, Any],
    *,
    print_steps: bool = True,
    stream: TextIO | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Stream the graph and collect per-node updates.

    Uses LangGraph stream_mode='updates' — one chunk per completed node,
    similar to the step-by-step view in Andrew Ng's LangGraph course.
    """
    steps: list[dict[str, Any]] = []
    merged = dict(state)
    step_num = 0

    if print_steps:
        header = stream or __import__("sys").stdout
        header.write("\n🔍 LangGraph trace enabled — showing each node output\n")
        header.flush()

    for chunk in graph.stream(state, stream_mode="updates"):
        if not isinstance(chunk, dict):
            continue
        for node_name, update in chunk.items():
            step_num += 1
            update = update or {}
            record = {"step": step_num, "node": node_name, "update": update}
            steps.append(record)
            merged.update(update)
            if print_steps:
                print_trace_step(step_num, node_name, update, stream=stream)

    if print_steps and steps:
        out = stream or __import__("sys").stdout
        out.write("\n" + "─" * 60 + f"\n Trace complete — {step_num} node(s) executed\n\n")
        out.flush()

    return merged, steps


def format_trace_for_ui(trace: list[dict]) -> str:
    parts = []
    for step in trace:
        parts.append(format_trace_step(step["step"], step["node"], step["update"]))
    return "\n".join(parts)


def iter_agent_trace_events(graph, state: dict[str, Any]):
    """Yield SSE-friendly events: step updates, then final merged state."""
    merged = dict(state)
    step_num = 0

    for chunk in graph.stream(state, stream_mode="updates"):
        if not isinstance(chunk, dict):
            continue
        for node_name, update in chunk.items():
            step_num += 1
            update = update or {}
            merged.update(update)
            yield {
                "type": "step",
                "step": step_num,
                "node": node_name,
                "trace_text": format_trace_step(step_num, node_name, update),
                "update": serialize_update(update),
            }

    yield {"type": "result", "state": merged}
