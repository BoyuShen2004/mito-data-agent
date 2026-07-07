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
