"""The supervisor routes via native function calling (with a JSON fallback).

These exercise the production ``SupervisorModel.route`` dispatch with a fake LLM
client — no network — so both the tool-calling path and the codex_cli JSON
fallback are covered.
"""

from __future__ import annotations

import pytest

from mito_data_agent.agents.registry import AGENT_CATALOG
from mito_data_agent.agents.state import ALLOWED_NEXT_AGENTS
from mito_data_agent.agents.supervisor_llm import (
    SupervisorModel,
    _build_agent_tools,
    _build_context,
)


class _FakeClient:
    def __init__(self, *, tool_calling: bool):
        self._tool_calling = tool_calling
        self.calls: list[str] = []

    def supports_tool_calling(self) -> bool:
        return self._tool_calling

    def route_via_tools(self, system, user, tools):
        self.calls.append("tools")
        self._tools = tools
        return {"name": "metadata_agent", "arguments": {"reason": "merge next", "confidence": "high"}}

    def complete_json(self, system, user):
        self.calls.append("json")
        self._system = system
        return {"next_agent": "validation_agent", "reason": "validate", "confidence": "medium"}


@pytest.fixture
def context():
    return _build_context({"user_prompt": "prepare vol1", "parsed_request": {"intent": "upload"}})


def _use_client(monkeypatch, client):
    from mito_data_agent.llm import llm_client as mod
    monkeypatch.setattr(mod, "get_llm_client", lambda: client)


def test_build_agent_tools_exposes_every_allowed_agent():
    tools = _build_agent_tools({"allowed": ALLOWED_NEXT_AGENTS, "agents": AGENT_CATALOG})
    names = [t["function"]["name"] for t in tools]
    assert names == ALLOWED_NEXT_AGENTS  # one callable tool per agent, incl. finish
    for t in tools:
        assert t["type"] == "function"
        assert "reason" in t["function"]["parameters"]["properties"]


def test_route_uses_native_tool_calling(monkeypatch, context):
    fake = _FakeClient(tool_calling=True)
    _use_client(monkeypatch, fake)

    decision = SupervisorModel().route(context)
    assert decision == {"next_agent": "metadata_agent", "reason": "merge next", "confidence": "high"}
    assert fake.calls == ["tools"]
    # `finish` is always a callable option.
    assert "finish" in [t["function"]["name"] for t in fake._tools]


def test_route_falls_back_to_json_without_tool_calling(monkeypatch, context):
    fake = _FakeClient(tool_calling=False)
    _use_client(monkeypatch, fake)

    decision = SupervisorModel().route(context)
    assert decision["next_agent"] == "validation_agent"
    assert fake.calls == ["json"]
    # The JSON-format instruction is only appended on the fallback path.
    assert "JSON object" in fake._system
