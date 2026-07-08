"""The agent can converse (ChatGPT-style) for casual/general input.

The LLM chat call is mocked so the test is offline; the real graph + supervisor
routing (to chat_agent) runs.
"""

from __future__ import annotations

import pytest

from mito_data_agent.agents import executed_route
from mito_data_agent.agents.runner import run_multi_agent


@pytest.fixture(autouse=True)
def mock_chat_reply(monkeypatch):
    monkeypatch.setattr(
        "mito_data_agent.agents.chat_agent.generate_chat_reply",
        lambda prompt: "Hi! I can chat, and also help record MitoVerse metadata.",
    )


def test_casual_message_gets_a_conversational_reply():
    result = run_multi_agent("how are you, what can you do?")
    raw = result["raw"]

    # Routed to chat_agent (not the task chain), and produced a reply.
    assert "chat_agent" in executed_route(raw)
    assert raw.get("chat_response")
    assert result["summary"]["chat_response"].startswith("Hi!")

    # No metadata work happened.
    assert raw.get("metadata_record") is None
    # The report text is the conversational reply itself.
    from mito_data_agent.tools.reporting import render_report_text
    assert render_report_text(raw) == raw["chat_response"]


def test_task_message_still_runs_the_task_chain():
    """A real data task is NOT treated as chat — it still records metadata."""
    prompt = (
        "Please upload this annotated mitochondria volume to MitoVerse.\n"
        "Volume: vol1\nDataset: mito_data_agent_data\nModality: FIB-SEM\n"
        "Organism: Human\nOrgan: Cervix (HeLa)\nTissue / region: HeLa cell interphase\n"
        "Resolution: 8x8x40 nm\n"
        "Raw file: ../mito_data_agent_data/vol1_0000.tiff\n"
        "Label file: ../mito_data_agent_data/vol1.tiff"
    )
    raw = run_multi_agent(prompt)["raw"]
    assert "chat_agent" not in executed_route(raw)
    assert raw.get("chat_response") is None
    assert raw["metadata_record"]["recorded"] is True
