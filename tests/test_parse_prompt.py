"""Tests for rule-based prompt parsing (fallback module)."""

from pathlib import Path

from mito_data_agent.tools.parse_prompt_fallback import parse_user_prompt_fallback
from mito_data_agent.utils.prompts import load_prompt_file

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_parse_upload_prompt_fallback():
    prompt = load_prompt_file(EXAMPLES / "upload_prompt.md")
    result = parse_user_prompt_fallback(prompt)

    assert result.intent == "upload_annotation"
    assert result.resolution_nm == (8.0, 8.0, 40.0)
    assert result.volume == "vol1"
    assert result.raw_file_path == "../mito_data_agent_data/vol1_0000.tiff"
