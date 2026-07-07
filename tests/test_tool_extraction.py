"""Unit tests for the deterministic logic extracted out of the agents into tools.

Agents are pure flow; the mechanical work lives in tools and is testable on its
own (no graph, no state machine) — that's what these cover.
"""

from __future__ import annotations

from mito_data_agent.tools.parse_prompt import promote_primary_fields
from mito_data_agent.tools.record_datasets import collect_datasets_to_record
from mito_data_agent.tools import trace_details


def test_promote_primary_fields_mirrors_first_dataset():
    payload = {"volume": None, "datasets": [{"volume": "vol1", "organism": "Mouse"}]}
    out = promote_primary_fields(payload)
    assert out["volume"] == "vol1"
    assert out["organism"] == "Mouse"


def test_promote_primary_fields_noop_when_primary_present():
    payload = {"volume": "already", "datasets": [{"volume": "other"}]}
    assert promote_primary_fields(dict(payload))["volume"] == "already"


def test_collect_datasets_dedupes_primary_and_extras():
    state = {
        "merged_metadata": {"volume": "ME2-Stem"},
        "schema_validation": {"success": True},
        "parsed_request": {
            "datasets": [
                {"volume": "ME2-Stem"},          # duplicate of primary -> dropped
                {"dataset": "MitoHardLiver"},     # name lives in `dataset`, still kept
            ]
        },
    }
    collected = collect_datasets_to_record(state)
    keys = [md.get("volume") for md, _ in collected]
    assert "ME2-Stem" in keys
    assert "MitoHardLiver" in keys          # keyed off `dataset` when volume empty
    assert keys.count("ME2-Stem") == 1      # de-duped
    # The primary carries its validation result; extras are unvalidated (None).
    assert collected[0] == ({"volume": "ME2-Stem"}, True)


def test_trace_detail_formatters_are_pure_strings():
    assert "intent = upload" in trace_details.parser_details({"intent": "upload", "volume": "v"})
    assert any("→ failed" in d for d in trace_details.validation_details(
        {"status": "failed", "missing_fields": ["tissue_region"]}))
    assert any("missing required fields: tissue_region" in d for d in trace_details.validation_details(
        {"status": "failed", "missing_fields": ["tissue_region"]}))
