"""End-to-end dry-run graph tests (ReAct agent with mocked LLM)."""

from pathlib import Path

from mito_data_agent.runner import run_agent
from mito_data_agent.utils.prompts import load_prompt_file

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_upload_prompt_dry_run():
    prompt = load_prompt_file(EXAMPLES / "upload_prompt.md")
    result = run_agent(prompt)
    artifacts = result["raw"].get("artifacts") or {}

    assert result["summary"].get("execution_report_path") or artifacts.get("execution_report_path")
    assert artifacts.get("hf_staging_dir")
    assert artifacts.get("mitoverse_update_files")

    hf_plan = artifacts.get("hf_upload_plan") or {}
    gh_plan = artifacts.get("github_push_plan") or {}
    assert hf_plan.get("real_write_performed") is False
    assert gh_plan.get("real_write_performed") is False
    assert hf_plan.get("signal") == "ok"
    assert gh_plan.get("signal") == "ok"
    assert artifacts.get("generate_hf_staging_plan", {}).get("signal") == "ok"
    assert artifacts.get("generate_mitoverse_update_plan", {}).get("signal") == "ok"
