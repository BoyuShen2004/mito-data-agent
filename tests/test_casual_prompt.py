"""Tests for casual / ambiguous prompt handling."""

from mito_data_agent.tools.parse_prompt_fallback import parse_user_prompt_fallback


def test_dataset_search_is_unsupported():
    result = parse_user_prompt_fallback("check the existing datasets to be uploaded")
    assert result.intent == "unsupported_request"
