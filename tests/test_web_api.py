"""Web API tests — drive the FastAPI app end-to-end with the offline LLM stand-ins.

The autouse fixtures in conftest.py mock the prompt parser + supervisor and
redirect the metadata store to a temp path, so these exercise the real endpoints
and the real graph deterministically (no network).
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from mito_data_agent.web.server import app

UPLOAD_PROMPT = """\
Please upload this annotated mitochondria volume to MitoVerse.

Volume: vol1
Dataset: mito_data_agent_data
Modality: FIB-SEM
Organism: Human
Organ: Cervix (HeLa)
Resolution: 8x8x40 nm
Raw file: ../mito_data_agent_data/vol1_0000.tiff
Label file: ../mito_data_agent_data/vol1.tiff

Prepare the Hugging Face upload and update MitoVerse metadata.
"""


@pytest.fixture(autouse=True)
def isolate_settings(tmp_path, monkeypatch):
    """Redirect the persisted LLM settings file to a temp path so tests never
    read or overwrite the user's real outputs/logs/llm_connection.json."""
    from mito_data_agent.llm import settings_store

    monkeypatch.setattr(settings_store, "_settings_path", lambda: tmp_path / "llm_connection.json")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "llm_backend" in body and "llm_model" in body


def test_examples(client):
    r = client.get("/api/examples")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert all("title" in x and "text" in x for x in items)


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Mito Data Agent" in r.text


def test_run_rejects_empty_prompt(client):
    r = client.post("/api/run", json={"prompt": "   "})
    assert r.status_code == 400


def test_run_and_records_roundtrip(client):
    r = client.post("/api/run", json={"prompt": UPLOAD_PROMPT})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_id"]
    assert body["report_text"]
    assert isinstance(body["trace"], list) and body["trace"]

    summary = body["summary"]
    volumes = [d["volume"] for d in summary.get("recorded_datasets", [])]
    assert "vol1" in volumes
    # Every external write stays a dry-run.
    assert summary.get("real_write_performed") is False

    # The recorded volume shows up in the ledger endpoint.
    rec = client.get("/api/records")
    assert rec.status_code == 200
    ledger_volumes = [x["volume"] for x in rec.json()["records"]]
    assert "vol1" in ledger_volumes

    one = client.get("/api/records/vol1")
    assert one.status_code == 200
    assert one.json()["volume"] == "vol1"

    assert client.get("/api/records/does-not-exist").status_code == 404


def test_settings_roundtrip(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert "llm_backend" in r.json()

    upd = client.post("/api/settings", json={"llm_backend": "openai", "llm_model": "gpt-4.1"})
    assert upd.status_code == 200
    assert upd.json()["llm_model"] == "gpt-4.1"
