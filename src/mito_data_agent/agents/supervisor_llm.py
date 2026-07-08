"""LLM-driven supervisor: the router *reasons* about the next agent.

There are no hardcoded routes or keyword rules. On each turn the supervisor hands
the LLM the user's request, the agent catalog, and a snapshot of what has been
done so far. On the OpenAI backend the agents are exposed as **callable tools**
and the LLM picks the next step via native function calling (``tool_choice=
"required"``); on backends without tool calling (codex_cli) it makes the same
decision as a JSON object.

Testing: the LLM call is isolated behind :func:`get_supervisor_model`. Tests
monkeypatch that to a scripted model so the graph is deterministic offline, while
the production routing code (context building, tool/JSON handling, allow-list
enforcement) still runs.
"""

from __future__ import annotations

import json
from typing import Any

from mito_data_agent.agents.registry import AGENT_CATALOG, progress_snapshot
from mito_data_agent.agents.state import ALLOWED_NEXT_AGENTS, MultiAgentState

_SYSTEM_PROMPT = """\
You are the SUPERVISOR of a multi-agent workflow that prepares annotated \
mitochondria volumes for MitoVerse upload. You do not do task work yourself — \
you only decide which specialist agent runs next.

On each turn you are given:
- the user's request,
- the catalog of available agents,
- a progress snapshot (which work products already exist).

Choose exactly one `next_agent` from the allowed list, or `finish` when the \
user's request has been satisfied and the final report has been written.

Guidelines:
- If the user is just chatting — a greeting, small talk, "how are you", "what can \
you do", thanks, or ANY general/unrelated question that is not a mitochondria-data \
task — route to `chat_agent` to reply conversationally, then `finish`. You do NOT \
need to parse first for chat.
- `input_parser_agent` must run before anything else needs the parsed request.
- Only run the agents the user's request actually needs. A "what data do I have" \
request needs `inventory_agent`; a "is X already in MitoVerse" request needs \
`catalog_agent`; a "where do you keep / store the metadata" or "what have you \
recorded" request needs `storage_info_agent`; an upload request needs the file → \
metadata → validation → record → staging → upload → website chain.
- When the user provides metadata for MULTIPLE datasets in one prompt, still run \
the normal metadata → validation → record path once — `metadata_record_agent` saves \
every dataset the parser found, so you do not loop per dataset.
- Whenever metadata was produced, run `metadata_record_agent` (after validation) \
to save the record to the local store, even if validation failed.
- If validation failed, do not stage or upload — record the metadata, then go to \
`report_agent`.
- Run `report_agent` once, near the end, then `finish`.
- Never pick an agent whose work product already exists (avoid loops).
"""

# Native tool-calling (OpenAI) is the primary path: the agents are exposed as
# callable tools and the model *calls* the one to run next. The JSON suffix is
# only appended for the fallback path (codex_cli / no tool-calling), which asks
# for the same decision as a JSON object instead.
_JSON_FORMAT_SUFFIX = """

Respond with ONLY a JSON object:
{"next_agent": "<agent or finish>", "reason": "<one sentence>", "confidence": "low|medium|high"}
"""


def _build_context(state: MultiAgentState) -> dict[str, Any]:
    """Assemble the factual context the supervisor reasons over."""
    parsed = state.get("parsed_request") or {}
    validation = state.get("schema_validation") or {}
    return {
        "user_prompt": state.get("user_prompt", ""),
        "chat_history": state.get("chat_history") or [],
        "parsed_intent": parsed.get("intent"),
        "progress": progress_snapshot(state),
        "validation_status": validation.get("status"),
        "allowed": ALLOWED_NEXT_AGENTS,
        "agents": AGENT_CATALOG,
    }


# Recent conversation turns shown to the supervisor so follow-up messages ("do
# that", "and vol2?") are routed with context. Kept short to bound tokens.
_SUPERVISOR_HISTORY_TURNS = 6


def _render_history(history: list[dict[str, Any]]) -> str:
    """One-line-per-turn transcript of the most recent turns (empty if none)."""
    turns = [
        t
        for t in history
        if (t or {}).get("role") in ("user", "assistant") and ((t or {}).get("content") or "").strip()
    ][-_SUPERVISOR_HISTORY_TURNS:]
    if not turns:
        return ""
    lines = [f"{t['role']}: {str(t['content']).strip()}" for t in turns]
    return "Conversation so far (for context):\n" + "\n".join(lines) + "\n\n"


_FINISH_DESCRIPTION = (
    "End the run: the user's request has been satisfied and the final report has "
    "been written. Call this when no further agent is needed."
)


def _build_agent_tools(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose each allowed agent (and ``finish``) as a callable tool for the LLM.

    The model chooses the next step by *calling* one of these functions — genuine
    function calling rather than emitting a routing string. Each tool's
    description is the agent's catalog entry so the LLM reasons from it.
    """
    tools: list[dict[str, Any]] = []
    for name in context["allowed"]:
        description = _FINISH_DESCRIPTION if name == "finish" else context["agents"].get(name, name)
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "One sentence: why run this next.",
                            }
                        },
                        "required": ["reason"],
                        "additionalProperties": False,
                    },
                },
            }
        )
    return tools


def _build_user_prompt(context: dict[str, Any]) -> str:
    """Render the routing context into a user prompt string for the LLM."""
    catalog = "\n".join(f"- {name}: {desc}" for name, desc in context["agents"].items())
    return (
        f"{_render_history(context.get('chat_history') or [])}"
        f"User request:\n{context['user_prompt']}\n\n"
        f"Parsed intent: {context['parsed_intent']}\n"
        f"Validation status: {context['validation_status']}\n\n"
        f"Available agents:\n{catalog}\n\n"
        f"Allowed next_agent values: {context['allowed']}\n\n"
        f"Progress so far (true = already done):\n"
        f"{json.dumps(context['progress'], indent=2)}\n\n"
        "Pick the next agent."
    )


class SupervisorModel:
    """Production supervisor model.

    On the OpenAI backend the LLM decides the next step via **native function
    calling** — the agents are exposed as tools and the model *calls* one. On
    backends without tool calling (codex_cli) it falls back to the same decision
    expressed as JSON. Either way it returns
    ``{"next_agent", "reason", "confidence"}``.
    """

    def route(self, context: dict[str, Any]) -> dict[str, Any]:
        from mito_data_agent.llm.llm_client import get_llm_client

        client = get_llm_client()
        user_prompt = _build_user_prompt(context)

        if client.supports_tool_calling():
            tools = _build_agent_tools(context)
            last_exc: Exception | None = None
            for _attempt in range(2):  # one retry for transient LLM slowness/timeouts
                try:
                    result = client.route_via_tools(_SYSTEM_PROMPT, user_prompt, tools)
                    args = result.get("arguments", {})
                    return {
                        "next_agent": result.get("name", "finish"),
                        "reason": args.get("reason", ""),
                        "confidence": args.get("confidence", "high"),
                    }
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
            raise last_exc  # type: ignore[misc]

        # Fallback: JSON routing (backend without native tool calling).
        last_exc = None
        for _attempt in range(2):
            try:
                return client.complete_json(_SYSTEM_PROMPT + _JSON_FORMAT_SUFFIX, user_prompt)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        raise last_exc  # type: ignore[misc]


_default_model: SupervisorModel | None = None


def get_supervisor_model() -> SupervisorModel:
    """Return the supervisor LLM model (monkeypatched in tests)."""
    global _default_model
    if _default_model is None:
        _default_model = SupervisorModel()
    return _default_model


class LLMSupervisor:
    """Supervisor policy that delegates routing to the LLM."""

    def decide(self, state: MultiAgentState) -> dict:
        context = _build_context(state)
        # Looked up via the module global so tests can monkeypatch the model.
        decision = get_supervisor_model().route(context)
        return {
            "next_agent": decision.get("next_agent", "finish"),
            "reason": decision.get("reason", ""),
            "confidence": decision.get("confidence", "medium"),
        }
