"""Tests for the persistent metadata store and the record agent."""

from __future__ import annotations

import pytest

from mito_data_agent.agents.runner import run_multi_agent
from mito_data_agent.tools import metadata_store

COMPLETE_PROMPT = """\
Please upload this annotated mitochondria volume to MitoVerse.

Volume: vol1
Dataset: mito_data_agent_data
Modality: FIB-SEM
Organism: Human
Organ: Cervix (HeLa)
Tissue / region: HeLa cell interphase
Resolution: 8x8x40 nm
Raw file: ../mito_data_agent_data/vol1_0000.tiff
Label file: ../mito_data_agent_data/vol1.tiff
"""


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Point the store at a temp file so tests don't touch real outputs/."""
    store = tmp_path / "records.json"
    monkeypatch.setattr(metadata_store, "get_store_path", lambda: store)
    return store


def test_run_records_metadata_to_store():
    """A successful upload run persists a queryable record."""
    result = run_multi_agent(COMPLETE_PROMPT)
    raw = result["raw"]

    # The record agent ran and reported success.
    assert raw["metadata_record"]["recorded"] is True
    assert {v["volume"] for v in raw["metadata_record"]["volumes"]} == {"vol1"}

    # The record is now queryable from the store.
    rec = metadata_store.get_record("vol1")
    assert rec is not None
    assert rec["metadata"]["dataset"] == "mito_data_agent_data"
    assert rec["metadata"]["organism"] == "Human"
    assert rec["validation_success"] is True
    assert rec["source_prompt"]  # the original prompt is retained


def test_records_are_upserted_with_history():
    """Recording the same volume twice keeps a version history, no data loss."""
    run_multi_agent(COMPLETE_PROMPT)
    run_multi_agent(COMPLETE_PROMPT)

    rec = metadata_store.get_record("vol1")
    assert rec["times_recorded"] == 2
    assert len(rec["history"]) == 1  # the first version was retained

    assert len(metadata_store.list_records()) == 1  # still one volume, not duplicated


def test_reconcile_renames_record_and_sidecar_to_data_file(tmp_path, monkeypatch):
    """A record named from the prompt (MitoHardLiver) is re-keyed to its actual
    data file (jrc_x), the sidecar is renamed, and the dataset name is preserved."""
    from mito_data_agent import config

    data = tmp_path / "data"  # already created + wired as the sidecar dir by conftest
    data.mkdir(exist_ok=True)
    (data / "jrc_x_0000.tiff").write_bytes(b"raw")
    (data / "jrc_x.tiff").write_bytes(b"label")
    monkeypatch.setattr(config, "DEFAULT_DATA_DIR", str(data))
    monkeypatch.setattr(metadata_store, "get_sidecar_dir", lambda: data)

    # Seed a misnamed record + sidecar: name is from the prompt, but `provenance`
    # points at the real file stem (paths were never captured — the real-world bug).
    seed = {"volume": "MitoHardLiver", "dataset": "MitoHardLiver", "provenance": "jrc_x"}
    metadata_store.record_metadata(seed, run_id="r1")
    metadata_store.write_metadata_sidecar(seed)
    assert (data / "mitohardliver.metadata.json").exists()

    changes = metadata_store.reconcile_record_names()
    assert changes == [
        {"old": "mitohardliver", "new": "jrc_x", "removed_sidecar": "mitohardliver.metadata.json"}
    ]

    # Store re-keyed to the file stem; dataset preserved; file paths backfilled.
    assert "mitohardliver" not in metadata_store.load_store()["records"]
    rec = metadata_store.get_record("jrc_x")
    assert rec is not None and rec["volume"] == "jrc_x"
    assert rec["metadata"]["dataset"] == "MitoHardLiver"
    assert rec["metadata"]["raw_file_path"].endswith("jrc_x_0000.tiff")

    # Sidecar renamed on disk.
    assert (data / "jrc_x.metadata.json").exists()
    assert not (data / "mitohardliver.metadata.json").exists()

    # Idempotent: nothing left to rename.
    assert metadata_store.reconcile_record_names() == []


def test_query_records_by_field():
    """Records can be filtered by a metadata field for later reuse."""
    run_multi_agent(COMPLETE_PROMPT)

    assert metadata_store.query_records(organism="Human")
    assert metadata_store.query_records(modality="FIB-SEM")
    assert not metadata_store.query_records(organism="Mouse")


def test_records_persist_no_external_write():
    """Recording never performs a real external write."""
    raw = run_multi_agent(COMPLETE_PROMPT)["raw"]
    assert raw["real_write_performed"] is False
