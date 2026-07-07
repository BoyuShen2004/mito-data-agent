"""Tests for multi-dataset recording, data-dir sidecars, and storage-info answers."""

from __future__ import annotations

import json

import pytest

from mito_data_agent.agents.metadata_record_agent import metadata_record_agent
from mito_data_agent.agents.runner import run_multi_agent
from mito_data_agent.tools import metadata_store


def _base_state(prompt="record two datasets"):
    return {
        "run_id": "run_test",
        "user_prompt": prompt,
        "agent_trace": [],
        "warnings": [],
        "errors": [],
        "step": 0,
    }


def test_records_multiple_datasets_from_one_request():
    """A single request describing several datasets records each one."""
    state = _base_state()
    # Primary (merged) + two additional datasets parsed from the same prompt.
    state["merged_metadata"] = {
        "volume": "ME2-Stem", "dataset": "Dataset008_ME2-Stem", "modality": "SBF-SEM",
        "organism": "Mouse", "organ": "Brainstem", "tissue_region": "neural/glial",
        "resolution_nm": [8, 8, 30], "shape_xyz": [1024, 1024, 100], "num_mito": 2058,
    }
    state["schema_validation"] = {"success": True, "status": "passed"}
    state["parsed_request"] = {
        "intent": "metadata_only_update",
        "datasets": [
            {"volume": "ME2-Stem"},  # duplicate of primary — must be de-duped
            # Regression: the LLM often leaves volume empty and puts the name in
            # `dataset`. This must NOT be dropped.
            {"volume": None, "dataset": "MitoHardLiver",
             "modality": "FIB-SEM", "organism": "Mouse", "organ": "Liver"},
        ],
    }

    out = metadata_record_agent(state)
    record = out["metadata_record"]

    assert record["recorded"] is True
    assert record["count"] == 2  # ME2-Stem + MitoHardLiver, not 1
    names = {v["volume"] for v in record["volumes"]}
    assert names == {"ME2-Stem", "MitoHardLiver"}

    # Both are now in the queryable store (MitoHardLiver keyed by its dataset name).
    assert metadata_store.get_record("ME2-Stem") is not None
    assert metadata_store.get_record("MitoHardLiver") is not None


def test_writes_metadata_sidecar_next_to_data(tmp_path, monkeypatch):
    """Each recorded volume gets a sidecar file in the data directory."""
    data_dir = tmp_path / "mydata"
    data_dir.mkdir()
    monkeypatch.setattr(metadata_store, "get_sidecar_dir", lambda: data_dir)

    state = _base_state()
    state["merged_metadata"] = {
        "volume": "vol1", "dataset": "d", "modality": "FIB-SEM", "organism": "Human",
        "organ": "o", "tissue_region": "t", "resolution_nm": [8, 8, 40],
        "shape_xyz": [100, 100, 50], "num_mito": 5,
    }
    state["schema_validation"] = {"success": True, "status": "passed"}
    state["parsed_request"] = {"intent": "metadata_only_update"}

    out = metadata_record_agent(state)
    sidecar = data_dir / "vol1.metadata.json"
    assert sidecar.exists()
    payload = json.loads(sidecar.read_text())
    assert payload["volume"] == "vol1"
    assert payload["metadata"]["organism"] == "Human"
    assert out["metadata_record"]["volumes"][0]["sidecar_path"] is not None


def test_file_info_wins_over_conflicting_prompt():
    """When the prompt disagrees with the actual data file, the file value wins."""
    from mito_data_agent.tools.reconcile_metadata import reconcile_with_files

    # vol1's real label file has shape (1000,1000,100) and 2 mito; give wrong prompt values.
    metadata = {
        "volume": "vol1",
        "raw_file_path": "../mito_data_agent_data/vol1_0000.tiff",
        "label_file_path": "../mito_data_agent_data/vol1.tiff",
        "shape_xyz": [1, 1, 1],
        "num_mito": 999,
    }
    reconciled, warnings = reconcile_with_files(metadata)

    assert tuple(reconciled["shape_xyz"]) == (1000, 1000, 100)
    assert reconciled["num_mito"] == 2
    assert reconciled["shape_source"] in ("label_file", "raw_file")
    # Conflicts were surfaced as warnings.
    assert any("shape conflict" in w for w in warnings)
    assert any("Mito conflict" in w for w in warnings)


def test_record_agent_applies_file_over_prompt_and_logs_conflict():
    """The record agent records the file-corrected values and logs the conflict as
    an informational conflict (auto-resolved, file wins) — NOT a warning/error."""
    state = _base_state()
    state["schema_validation"] = {"success": True, "status": "passed"}
    state["merged_metadata"] = {}
    state["parsed_request"] = {
        "intent": "metadata_only_update",
        "datasets": [
            {
                "volume": "vol1",
                "raw_file_path": "../mito_data_agent_data/vol1_0000.tiff",
                "label_file_path": "../mito_data_agent_data/vol1.tiff",
                "num_mito": 999,  # wrong on purpose
            }
        ],
    }
    out = metadata_record_agent(state)

    rec = metadata_store.get_record("vol1")
    assert rec["metadata"]["num_mito"] == 2  # file value, not 999
    # Conflicts go to the dedicated `conflicts` channel, not warnings/errors.
    assert any("Mito conflict" in c["message"] for c in out["conflicts"])
    assert not out.get("warnings")
    # And the conflict shows up as a component detail on the trace entry.
    trace_details = out["agent_trace"][-1]["details"]
    assert any("conflict resolved (file wins)" in d for d in trace_details)


def test_report_shows_every_recorded_dataset():
    """The final report must list ALL recorded datasets, not just the primary."""
    from mito_data_agent.tools.reporting import render_report_text

    state = {
        "run_id": "r",
        "parsed_request": {"intent": "metadata_only_update"},
        "merged_metadata": {"volume": "vol1", "dataset": "ME2-Stem"},
        "schema_validation": {"success": False, "status": "failed", "missing_fields": ["tissue_region"]},
        "metadata_record": {
            "recorded": True, "count": 2, "store_path": "outputs/metadata_store/records.json",
            "volumes": [
                {"volume": "vol1", "times_recorded": 1, "validation_success": False,
                 "sidecar_path": "../mito_data_agent_data/vol1.metadata.json",
                 "metadata": {"dataset": "ME2-Stem", "modality": "SBF-SEM"}},
                {"volume": "MitoHardLiver", "times_recorded": 1, "validation_success": None,
                 "sidecar_path": "../mito_data_agent_data/mitohardliver.metadata.json",
                 "metadata": {"dataset": "MitoHardLiver", "modality": "FIB-SEM"}},
            ],
        },
        "warnings": [], "errors": [],
    }
    report = render_report_text(state)
    assert "vol1" in report
    assert "MitoHardLiver" in report  # the second dataset must be reported too
    assert "Recorded 2 dataset(s)" in report


def test_storage_info_answers_where_things_are_kept():
    """'Where do you keep the metadata?' routes to storage_info_agent and reports paths."""
    result = run_multi_agent("where did you keep the metadata at?")
    raw = result["raw"]

    agents = [d["next_agent"] for d in raw["supervisor_decisions"]]
    assert "storage_info_agent" in agents
    assert raw["storage_info"] is not None
    assert raw["storage_info"]["metadata_store"].endswith("records.json")

    # The final report actually tells the user where things live.
    report = raw["final_report"]
    assert "metadata" in report.lower()
    assert "records.json" in report
    assert "sidecar" in report.lower()
