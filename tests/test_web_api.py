"""Web API tests — drive the FastAPI app end-to-end with the offline LLM stand-ins.

The autouse fixtures in conftest.py mock the prompt parser + supervisor and
redirect the metadata store to a temp path, so these exercise the real endpoints
and the real graph deterministically (no network).
"""

from __future__ import annotations

import json

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


@pytest.fixture(autouse=True)
def isolate_chats(tmp_path, monkeypatch):
    """Redirect chat storage to a temp dir so tests never touch real chat history."""
    from mito_data_agent.tools import chat_store

    monkeypatch.setattr(chat_store, "get_outputs_dir", lambda: tmp_path)


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


def test_run_stream_rejects_empty_prompt(client):
    assert client.post("/api/run/stream", json={"prompt": "   "}).status_code == 400


def test_run_stream_emits_steps_then_final(client):
    with client.stream("POST", "/api/run/stream", json={"prompt": UPLOAD_PROMPT}) as r:
        assert r.status_code == 200
        msgs = [json.loads(ln) for ln in r.iter_lines() if ln.strip()]

    types = [m["type"] for m in msgs]
    # The trace streams incrementally (>=1 step) before the terminal "final".
    assert "step" in types
    assert types[-1] == "final"
    # At least one streamed step carried agent-trace entries as they completed.
    assert any(m.get("agent_trace") for m in msgs if m["type"] == "step")

    final = msgs[-1]
    assert final["run_id"] and final["report_text"]
    volumes = [d["volume"] for d in final["summary"].get("recorded_datasets", [])]
    assert "vol1" in volumes


def test_clear_endpoint(client, monkeypatch, tmp_path):
    """POST /api/clear wipes outputs/ and returns removal counts."""
    from mito_data_agent.utils import paths

    outputs = tmp_path / "outputs"
    monkeypatch.setattr(paths, "get_outputs_dir", lambda: outputs)
    # Seed a couple of artifacts across output subdirs.
    paths.ensure_output_dirs()
    (outputs / "execution_reports" / "run1.json").write_text("{}")
    (outputs / "hf_staging" / "vol1").mkdir(parents=True)

    r = client.post("/api/clear")
    assert r.status_code == 200
    body = r.json()
    assert body["removed_files"] >= 1 and body["removed_dirs"] >= 1
    # Structure is preserved (dirs + .gitkeep remain), artifacts are gone.
    assert (outputs / "execution_reports").is_dir()
    assert not (outputs / "execution_reports" / "run1.json").exists()
    assert not (outputs / "hf_staging" / "vol1").exists()


def test_chats_crud(client):
    assert client.get("/api/chats").json()["chats"] == []

    turns = [
        {"role": "user", "text": "Prepare vol1 for upload to MitoVerse"},
        {"role": "assistant", "result": {"run_id": "run_x", "summary": {}}},
    ]
    created = client.post("/api/chats", json={"turns": turns}).json()
    cid = created["id"]
    assert created["title"].startswith("Prepare vol1")  # title from first user turn
    assert created["created_at"] and created["updated_at"]

    listing = client.get("/api/chats").json()["chats"]
    assert [c["id"] for c in listing] == [cid]
    assert listing[0]["turn_count"] == 2

    got = client.get(f"/api/chats/{cid}")
    assert got.status_code == 200 and len(got.json()["turns"]) == 2

    turns.append({"role": "user", "text": "and again"})
    updated = client.put(f"/api/chats/{cid}", json={"turns": turns}).json()
    assert updated["id"] == cid and len(updated["turns"]) == 3
    assert updated["created_at"] == created["created_at"]  # preserved across updates

    assert client.delete(f"/api/chats/{cid}").json()["deleted"] is True
    assert client.get(f"/api/chats/{cid}").status_code == 404
    assert client.delete(f"/api/chats/{cid}").status_code == 404


def test_chat_store_rejects_path_traversal(tmp_path, monkeypatch):
    from mito_data_agent.tools import chat_store

    monkeypatch.setattr(chat_store, "get_outputs_dir", lambda: tmp_path)
    with pytest.raises(ValueError):
        chat_store.get_chat("../secret")
    with pytest.raises(ValueError):
        chat_store.delete_chat("a/b")


def test_settings_roundtrip(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert "llm_backend" in r.json()

    upd = client.post("/api/settings", json={"llm_backend": "openai", "llm_model": "gpt-4.1"})
    assert upd.status_code == 200
    assert upd.json()["llm_model"] == "gpt-4.1"
