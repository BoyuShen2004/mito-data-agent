"""LLM-first prompt parser."""

from __future__ import annotations

from mito_data_agent.llm.llm_client import get_llm_client
from mito_data_agent.schemas import ParsedUserRequest


def parse_user_prompt_with_llm(user_prompt: str) -> ParsedUserRequest:
    """Parse a free-form user prompt using the configured LLM backend."""
    client = get_llm_client()
    return client.structured_parse_user_request(user_prompt)
