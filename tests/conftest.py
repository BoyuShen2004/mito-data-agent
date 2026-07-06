"""Pytest configuration — mock ReAct agent LLM by default."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tests.agent_mock import ScriptedAgentLLM


@pytest.fixture(autouse=True)
def mock_agent_llm_unless_real(request, monkeypatch):
    if os.getenv("MITO_AGENT_TEST_USE_REAL_LLM") == "1":
        return
    if "no_llm_mock" in request.keywords:
        return

    scripts: dict[str, ScriptedAgentLLM] = {}

    class Factory:
        def invoke(self, messages, tools):
            from langchain_core.messages import HumanMessage

            user_text = ""
            for m in messages:
                if isinstance(m, HumanMessage):
                    user_text = m.content
                    break
            if user_text not in scripts:
                scripts[user_text] = ScriptedAgentLLM(user_text)
            return scripts[user_text].invoke(messages, tools)

    monkeypatch.setattr(
        "mito_data_agent.agent.nodes.get_agent_chat_model",
        lambda: Factory(),
    )
    # Reset cached graph so tests pick up the mock.
    import mito_data_agent.runner as runner_mod

    runner_mod._GRAPH = None
