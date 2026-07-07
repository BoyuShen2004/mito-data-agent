"""Pytest configuration — run the whole suite offline with deterministic LLM stand-ins."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tests.deterministic_parser import parse_user_prompt_fallback
from tests.deterministic_supervisor import ScriptedSupervisorModel


@pytest.fixture(autouse=True)
def isolate_metadata_store(tmp_path, monkeypatch):
    """Redirect the metadata store AND the data-dir sidecars to temp paths so
    tests never write to the real outputs/ ledger or the real data directory."""
    from mito_data_agent.tools import metadata_store

    store = tmp_path / "records.json"
    sidecars = tmp_path / "data"
    sidecars.mkdir()
    monkeypatch.setattr(metadata_store, "get_store_path", lambda: store)
    monkeypatch.setattr(metadata_store, "get_sidecar_dir", lambda: sidecars)


@pytest.fixture(autouse=True)
def mock_llm_unless_real(request, monkeypatch):
    """Mock the two LLM seams (prompt parser + supervisor) with deterministic
    stand-ins so the graph runs offline. Set MITO_AGENT_TEST_USE_REAL_LLM=1 to use
    the real backend."""
    if os.getenv("MITO_AGENT_TEST_USE_REAL_LLM") == "1":
        return
    if "no_llm_mock" in request.keywords:
        return

    # LLM prompt parser (deterministic, offline).
    monkeypatch.setattr(
        "mito_data_agent.agents.input_parser_agent.parse_user_prompt",
        parse_user_prompt_fallback,
    )
    # LLM supervisor model (deterministic routing over the same context).
    monkeypatch.setattr(
        "mito_data_agent.agents.supervisor_llm.get_supervisor_model",
        lambda: ScriptedSupervisorModel(),
    )

    # Reset the cached graph so tests pick up the mocks.
    import mito_data_agent.agents.runner as agents_runner_mod

    agents_runner_mod._GRAPH = None
