"""LLM prompt parsing — the agent parses free-form prompts via the LLM only.

There is no rule-based fallback: this is an agentic system and prompt
understanding is the LLM's job. If no LLM backend is configured, parsing fails
loudly.
"""

from __future__ import annotations

from mito_data_agent.schemas import ParsedUserRequest
from mito_data_agent.tools.parse_prompt_llm import parse_user_prompt_with_llm


def parse_user_prompt(user_prompt: str) -> ParsedUserRequest:
    """Parse a free-form user prompt into structured fields using the LLM.

    Retries once on transient failures (e.g. a slow LLM/CLI timeout) before
    giving up — there is no rule-based fallback by design.
    """
    last_exc: Exception | None = None
    for _attempt in range(2):
        try:
            return parse_user_prompt_with_llm(user_prompt)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    raise RuntimeError(
        "LLM prompt parsing failed and there is no rule-based fallback. "
        "Configure an LLM backend (OpenAI API key or Codex CLI). "
        f"Original error: {last_exc}"
    ) from last_exc
