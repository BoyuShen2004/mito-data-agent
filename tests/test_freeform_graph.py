"""End-to-end test with mocked agent for free-form upload prompt."""

from pathlib import Path

from mito_data_agent.runner import run_agent
from mito_data_agent.utils.prompts import load_prompt_file

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_freeform_upload_dry_run_graph():
    prompt = load_prompt_file(EXAMPLES / "freeform_upload_prompt.md")
    result = run_agent(prompt)
    artifacts = result["raw"].get("artifacts") or {}
    merged = artifacts.get("merged_metadata") or {}

    assert merged.get("volume") == "vol1"
    assert merged.get("shape_xyz") == (1000, 1000, 100)
    assert merged.get("num_mito") == 2
    assert merged.get("shape_source") in ("raw_file", "label_file")

    assert artifacts.get("execution_report_path") or result["summary"].get("execution_report_path")
    assert artifacts.get("hf_staging_dir")

    hf_plan = artifacts.get("hf_upload_plan") or {}
    gh_plan = artifacts.get("github_push_plan") or {}
    assert hf_plan.get("real_write_performed") is False
    assert gh_plan.get("real_write_performed") is False
