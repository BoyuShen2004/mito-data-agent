"""Tests for prompt parsing (fallback parser unit tests)."""

from pathlib import Path

from mito_data_agent.tools.parse_prompt_fallback import parse_user_prompt_fallback
from mito_data_agent.utils.prompts import load_prompt_file

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_labeled_upload_prompt_parse():
    prompt = load_prompt_file(EXAMPLES / "upload_prompt.md")
    result = parse_user_prompt_fallback(prompt)

    assert result.intent == "upload_annotation"
    assert result.volume == "vol1"
    assert result.dataset == "mito_data_agent_data"
    assert result.raw_file_path.endswith("vol1_0000.tiff")
    assert result.label_file_path.endswith("vol1.tiff")
    assert result.resolution_nm == (8.0, 8.0, 40.0)


def test_freeform_upload_prompt_intent():
    prompt = load_prompt_file(EXAMPLES / "freeform_upload_prompt.md")
    result = parse_user_prompt_fallback(prompt)
    assert result.intent == "upload_annotation"
    assert "prepare_hf_upload" in result.requested_actions


def test_fallback_parser_still_available():
    prompt = load_prompt_file(EXAMPLES / "upload_prompt.md")
    result = parse_user_prompt_fallback(prompt)
    assert result.volume == "vol1"
    assert any("fallback" in n.lower() for n in result.notes)
