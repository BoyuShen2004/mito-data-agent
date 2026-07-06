"""LLM backends for the LangGraph agent loop (OpenAI tools + Codex CLI)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from mito_data_agent import config
from mito_data_agent.llm.settings_store import apply_settings_to_config, load_settings


def _openai_messages(messages: list[AnyMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            out.append({"role": "system", "content": msg.content})
        elif isinstance(msg, HumanMessage):
            out.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            entry: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or "",
            }
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"]),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            out.append(entry)
        elif isinstance(msg, ToolMessage):
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                }
            )
    return out


def _to_ai_message(response) -> AIMessage:
    choice = response.choices[0].message
    tool_calls = []
    if choice.tool_calls:
        for tc in choice.tool_calls:
            args = tc.function.arguments
            if isinstance(args, str):
                args = json.loads(args) if args.strip() else {}
            tool_calls.append({"id": tc.id, "name": tc.function.name, "args": args})
    return AIMessage(content=choice.content or "", tool_calls=tool_calls)


def _get_codex_path() -> str | None:
    settings = load_settings()
    return (
        settings.codex_path
        or getattr(config, "_RUNTIME_CODEX_PATH", None)
        or shutil.which("codex")
    )


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise RuntimeError(f"LLM did not return JSON. Output:\n{text[:500]}")
        return json.loads(match.group())


def _messages_to_transcript(messages: list[AnyMessage]) -> str:
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            parts.append(f"[system]\n{msg.content}")
        elif isinstance(msg, HumanMessage):
            parts.append(f"[user]\n{msg.content}")
        elif isinstance(msg, AIMessage):
            if msg.tool_calls:
                parts.append(f"[assistant planned tools]\n{json.dumps(msg.tool_calls, indent=2)}")
            if msg.content:
                parts.append(f"[assistant]\n{msg.content}")
        elif isinstance(msg, ToolMessage):
            parts.append(f"[tool:{msg.name} observation]\n{msg.content}")
    return "\n\n".join(parts)


def _tools_summary(tools: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for spec in tools:
        fn = spec["function"]
        lines.append(f"- {fn['name']}: {fn.get('description', '')}")
    return "\n".join(lines)


def _invoke_codex_cli(messages: list[AnyMessage], tools: list[dict]) -> AIMessage:
    codex = _get_codex_path()
    if not codex:
        raise RuntimeError(
            "Codex CLI not found. Install Codex and run `codex login`, "
            "or switch to OpenAI in the Web UI."
        )

    prompt = (
        "You are the LLM node in a LangGraph ReAct loop for Mito Data Agent.\n"
        "After each tool observation you may call more tools or finish.\n\n"
        f"Available tools:\n{_tools_summary(tools)}\n\n"
        f"Conversation:\n{_messages_to_transcript(messages)}\n\n"
        "Reply with ONLY JSON (no markdown):\n"
        '- To call tools: {"tool_calls":[{"id":"call_1","name":"tool_name","args":{...}}]}\n'
        '- When done: {"content":"final answer for the user"}\n'
    )

    result = subprocess.run(
        [codex, "exec", "--full-auto", prompt],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Codex CLI call failed. Run `codex login` or switch to OpenAI backend.\n"
            f"stderr: {result.stderr.strip()}\nstdout: {result.stdout.strip()}"
        )

    data = _extract_json(result.stdout.strip())
    if data.get("tool_calls"):
        calls = []
        for i, tc in enumerate(data["tool_calls"]):
            calls.append(
                {
                    "id": tc.get("id") or f"codex_{uuid.uuid4().hex[:8]}_{i}",
                    "name": tc["name"],
                    "args": tc.get("args") or {},
                }
            )
        return AIMessage(content="", tool_calls=calls)
    return AIMessage(content=data.get("content") or result.stdout.strip(), tool_calls=[])


class AgentChatModel:
    """Invoke LLM inside the LangGraph agent loop."""

    def invoke(self, messages: list[AnyMessage], tools: list[dict]) -> AIMessage:
        apply_settings_to_config(load_settings())
        settings = load_settings()

        if settings.llm_backend == "codex_cli" or config.USE_CODEX_CLI:
            return _invoke_codex_cli(messages, tools)

        api_key = (
            settings.openai_api_key
            or getattr(config, "_RUNTIME_OPENAI_API_KEY", None)
        )
        if not api_key:
            raise RuntimeError(
                "OpenAI API key not configured. Set it in the Web UI Connection panel."
            )

        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=settings.llm_model or config.LLM_MODEL,
            messages=_openai_messages(messages),
            tools=tools,
            tool_choice="auto",
        )
        return _to_ai_message(response)


_default_model: AgentChatModel | None = None


def get_agent_chat_model() -> AgentChatModel:
    global _default_model
    if _default_model is None:
        _default_model = AgentChatModel()
    return _default_model
