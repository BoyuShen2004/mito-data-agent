"""LLM-first prompt parsing with optional rule-based fallback."""

from __future__ import annotations

from mito_data_agent import config
from mito_data_agent.schemas import ParsedUserRequest
from mito_data_agent.tools.parse_prompt_fallback import parse_user_prompt_fallback
from mito_data_agent.tools.parse_prompt_llm import parse_user_prompt_with_llm


def parse_user_prompt(user_prompt: str) -> ParsedUserRequest:
    """Parse user prompt — LLM required by default; fallback only if explicitly allowed."""
    if not config.REQUIRE_LLM_FOR_PROMPT_PARSING:
        return parse_user_prompt_fallback(user_prompt)

    try:
        return parse_user_prompt_with_llm(user_prompt)
    except Exception as exc:
        if config.ALLOW_RULE_BASED_FALLBACK:
            result = parse_user_prompt_fallback(user_prompt)
            notes = list(result.notes)
            notes.append(f"LLM parsing failed ({exc}); used rule-based fallback.")
            return result.model_copy(update={"notes": notes})
        raise RuntimeError(
            "No LLM backend available. This MVP requires LLM prompt parsing. "
            f"Original error: {exc}"
        ) from exc
