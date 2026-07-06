"""Tests for streaming chat API."""

import json

from fastapi.testclient import TestClient

from mito_data_agent.web.server import app

client = TestClient(app)


def _parse_sse(body: str) -> list[dict]:
    events = []
    for block in body.strip().split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block[6:]))
    return events


def test_chat_stream_emits_steps_then_done():
    prompt = "check what data do i currently have"
    with client.stream("POST", "/api/chat/stream", json={"message": prompt}) as res:
        assert res.status_code == 200
        body = "".join(res.iter_text())

    events = _parse_sse(body)
    assert any(e["type"] == "step" for e in events)
    assert events[-1]["type"] == "done"
    assert "message" in events[-1]
    assert events[-1]["summary"]["intent"] == "agent_react"
