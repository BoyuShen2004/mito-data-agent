"""Tests for the web chat API."""

from fastapi.testclient import TestClient

from mito_data_agent.web.server import app

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_examples():
    res = client.get("/api/examples")
    assert res.status_code == 200
    assert len(res.json()) >= 1


def test_chat_minimal():
    prompt = (
        "Please update only the MitoVerse metadata row.\n"
        "Volume: web_test\n"
        "Dataset: test\n"
        "Modality: FIB-SEM\n"
        "Organism: Human\n"
        "Organ: Test\n"
        "Tissue / region: Test\n"
        "Resolution: 8x8x40 nm\n"
        "Shape: 100x100x50\n"
        "# Mito: 5\n"
    )
    res = client.post("/api/chat", json={"message": prompt})
    assert res.status_code == 200
    data = res.json()
    assert "message" in data
    assert data["summary"]["intent"] == "agent_react"
