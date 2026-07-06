"""ReAct agent nodes: llm ↔ tools loop."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from mito_data_agent.agent.llm import get_agent_chat_model
from mito_data_agent.agent.prompts import get_agent_system_prompt
from mito_data_agent.agent.state import AgentState
from mito_data_agent.agent.tools import OPENAI_TOOL_SCHEMAS, execute_tool
from mito_data_agent.utils.paths import ensure_output_dirs

MAX_AGENT_STEPS = 20


def validate_input_node(state: AgentState) -> dict:
    if not state.get("user_prompt"):
        raise ValueError("user_prompt is required.")
    ensure_output_dirs()
    return {
        "messages": [
            SystemMessage(content=get_agent_system_prompt()),
            HumanMessage(content=state["user_prompt"]),
        ],
        "artifacts": state.get("artifacts") or {},
        "step_count": 0,
    }


def call_llm_node(state: AgentState) -> dict:
    model = get_agent_chat_model()
    response = model.invoke(state["messages"], OPENAI_TOOL_SCHEMAS)
    return {"messages": [response]}


def take_action_node(state: AgentState) -> dict:
    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    artifacts = dict(state.get("artifacts") or {})
    tool_messages: list[ToolMessage] = []

    for tc in tool_calls:
        name = tc["name"]
        args = tc.get("args") or {}
        observation, updates = execute_tool(
            name,
            args,
            run_id=state["run_id"],
            artifacts=artifacts,
        )
        artifacts.update(updates)
        tool_messages.append(
            ToolMessage(tool_call_id=tc["id"], name=name, content=observation)
        )

    out: dict = {
        "messages": tool_messages,
        "artifacts": artifacts,
        "step_count": state.get("step_count", 0) + 1,
    }
    if artifacts.get("execution_report_path"):
        out["execution_report_path"] = artifacts["execution_report_path"]
    return out


def should_continue(state: AgentState) -> str:
    if state.get("step_count", 0) >= MAX_AGENT_STEPS:
        return "end"
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "continue"
    return "end"
