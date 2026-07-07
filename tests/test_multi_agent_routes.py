"""Route/behaviour tests for the supervisor-based multi-agent workflow.

These tests force the rule-based prompt parser (no live LLM) so routing is
deterministic, then assert the supervisor's hop sequence and safety invariants.
"""

from __future__ import annotations

import pytest

from mito_data_agent.agents import ALLOWED_NEXT_AGENTS, executed_route
from mito_data_agent.agents.runner import run_multi_agent

# The prompt parser (LLM) and supervisor (LLM) are mocked offline by the autouse
# fixture in conftest.py, so these tests exercise the real graph deterministically.


def _route(raw: dict) -> list[str]:
    """Reconstruct the executed node route (every hop goes through the supervisor)."""
    return executed_route(raw)


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

Please prepare the Hugging Face upload and update MitoVerse metadata.
"""

INCOMPLETE_PROMPT = """\
Please upload volume vol_missing to Hugging Face.

Volume: vol_missing
Modality: FIB-SEM
"""

INVALID_PATH_PROMPT = """\
Please upload this volume to Hugging Face.

Volume: vol_ghost
Dataset: mito_data_agent_data
Modality: FIB-SEM
Organism: Human
Organ: Cervix (HeLa)
Tissue / region: HeLa cell interphase
Resolution: 8x8x40 nm
Raw file: ../mito_data_agent_data/does_not_exist_0000.tiff
Label file: ../mito_data_agent_data/does_not_exist.tiff
"""


def test_success_path_full_route():
    """A complete prompt drives the full staging → upload → website → report route."""
    result = run_multi_agent(COMPLETE_PROMPT)
    raw = result["raw"]

    assert raw["schema_validation"]["success"] is True
    assert _route(raw) == [
        "supervisor_agent",
        "input_parser_agent",
        "supervisor_agent",
        "dataset_inspector_agent",
        "supervisor_agent",
        "observation_agent",
        "supervisor_agent",
        "metadata_agent",
        "supervisor_agent",
        "validation_agent",
        "supervisor_agent",
        "metadata_record_agent",
        "supervisor_agent",
        "staging_agent",
        "supervisor_agent",
        "upload_planning_agent",
        "supervisor_agent",
        "website_update_agent",
        "supervisor_agent",
        "report_agent",
        "supervisor_agent",
        "finish",
    ]
    # The parser is dispatched by the supervisor like every other agent.
    assert raw["supervisor_decisions"][0]["next_agent"] == "input_parser_agent"
    # Dry-run guarantees.
    assert raw["real_write_performed"] is False
    assert raw["hf_upload_plan"]["real_write_performed"] is False
    assert raw["github_push_plan"]["real_write_performed"] is False
    assert raw["final_report"]
    assert result["summary"]["execution_report_path"]


def test_validation_failed_path():
    """Missing metadata routes validation → report → finish and skips staging."""
    result = run_multi_agent(INCOMPLETE_PROMPT)
    raw = result["raw"]

    assert raw["schema_validation"]["success"] is False
    assert raw["schema_validation"]["status"] == "failed"

    route = _route(raw)
    # Metadata is still recorded before reporting, even on failed validation.
    assert route[-7:] == [
        "validation_agent",
        "supervisor_agent",
        "metadata_record_agent",
        "supervisor_agent",
        "report_agent",
        "supervisor_agent",
        "finish",
    ]
    # Never reaches upload/staging on a failed validation.
    assert "staging_agent" not in route
    assert "upload_planning_agent" not in route
    assert "website_update_agent" not in route
    assert raw["final_report"]


def test_invalid_file_path_does_not_crash():
    """An invalid file path must not crash — it flows to the report with an explanation."""
    result = run_multi_agent(INVALID_PATH_PROMPT)
    raw = result["raw"]

    # The run completed and produced a report rather than raising.
    assert raw["final_report"]
    assert "report_agent" in _route(raw)

    # The missing file is surfaced in warnings or errors.
    messages = [w["message"] for w in raw["warnings"]] + [e["message"] for e in raw["errors"]]
    assert any("not found" in m.lower() or "does_not_exist" in m.lower() for m in messages)


INVENTORY_PROMPT = "What data do I currently have in mito_data_agent_data?"
CATALOG_PROMPT = "Is jrc_mus-liver_recon-1_test0 already in the MitoVerse collection?"
READINESS_PROMPT = (
    "Is vol1 ready for upload?\n"
    "Raw file: ../mito_data_agent_data/vol1_0000.tiff\n"
    "Label file: ../mito_data_agent_data/vol1.tiff\n"
)
UNSUPPORTED_PROMPT = "Please train a segmentation model for me."


def test_inventory_route_goes_through_supervisor():
    """A 'what data do I have' prompt routes inventory → report via the supervisor."""
    raw = run_multi_agent(INVENTORY_PROMPT)["raw"]
    assert raw["parsed_request"]["intent"] == "list_local_data"
    agents = [d["next_agent"] for d in raw["supervisor_decisions"]]
    assert agents == ["input_parser_agent", "inventory_agent", "report_agent", "finish"]
    assert raw["local_data_inventory"] is not None
    assert raw["final_report"]


def test_catalog_route_goes_through_supervisor():
    """A MitoVerse lookup prompt routes catalog → report via the supervisor."""
    raw = run_multi_agent(CATALOG_PROMPT)["raw"]
    agents = [d["next_agent"] for d in raw["supervisor_decisions"]]
    assert agents == ["input_parser_agent", "catalog_agent", "report_agent", "finish"]
    # Catalog lookup is best-effort (may be offline); it must still finish cleanly.
    assert raw["mitoverse_lookup"] is not None
    assert raw["final_report"]


def test_readiness_route_skips_staging():
    """A readiness check validates then reports — no staging/upload/website."""
    raw = run_multi_agent(READINESS_PROMPT)["raw"]
    assert raw["parsed_request"]["intent"] == "check_upload_readiness"
    agents = [d["next_agent"] for d in raw["supervisor_decisions"]]
    assert agents == [
        "input_parser_agent",
        "dataset_inspector_agent",
        "observation_agent",
        "metadata_agent",
        "validation_agent",
        "metadata_record_agent",
        "report_agent",
        "finish",
    ]
    assert "staging_agent" not in agents


def test_unsupported_route_reports():
    """An out-of-scope request routes straight to the report."""
    raw = run_multi_agent(UNSUPPORTED_PROMPT)["raw"]
    assert raw["parsed_request"]["intent"] == "unsupported_request"
    agents = [d["next_agent"] for d in raw["supervisor_decisions"]]
    assert agents == ["input_parser_agent", "report_agent", "finish"]


@pytest.mark.parametrize(
    "prompt",
    [
        COMPLETE_PROMPT,
        INCOMPLETE_PROMPT,
        INVALID_PATH_PROMPT,
        INVENTORY_PROMPT,
        CATALOG_PROMPT,
        READINESS_PROMPT,
        UNSUPPORTED_PROMPT,
    ],
)
def test_supervisor_only_routes_to_allowed_agents(prompt):
    """Every supervisor decision must target an allow-listed agent — for all intents."""
    raw = run_multi_agent(prompt)["raw"]
    assert raw["supervisor_decisions"], "supervisor made no decisions"
    for decision in raw["supervisor_decisions"]:
        assert decision["next_agent"] in ALLOWED_NEXT_AGENTS
        assert decision["confidence"] in {"low", "medium", "high"}


def test_every_capability_dispatched_by_supervisor():
    """No agent ever runs without a preceding supervisor decision that selected it.

    This is the 'everything goes through the supervisor' invariant: the set of
    executed worker agents equals the set the supervisor dispatched.
    """
    for prompt in (COMPLETE_PROMPT, INVENTORY_PROMPT, CATALOG_PROMPT, UNSUPPORTED_PROMPT):
        raw = run_multi_agent(prompt)["raw"]
        executed = {e["agent"] for e in raw["agent_trace"]}
        dispatched = {d["next_agent"] for d in raw["supervisor_decisions"]}
        assert executed <= dispatched, f"agent ran without supervisor dispatch for: {prompt!r}"


def test_supervisor_llm_failure_does_not_crash(monkeypatch):
    """A failing/timing-out supervisor LLM must not crash — the run still reports."""
    import mito_data_agent.agents.supervisor_llm as sup

    class BoomModel:
        def route(self, context):
            raise TimeoutError("codex timed out")

    # Override the deterministic stand-in from conftest with a always-failing model.
    monkeypatch.setattr(sup, "get_supervisor_model", lambda: BoomModel())

    result = run_multi_agent(INVENTORY_PROMPT)
    raw = result["raw"]
    # The safety fallback drove it to a report instead of raising.
    assert raw["final_report"]
    assert any(d["next_agent"] == "report_agent" for d in raw["supervisor_decisions"])
    assert raw["supervisor_decisions"][-1]["next_agent"] == "finish"
