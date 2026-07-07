"""LLM prompt templates for Mito Data Agent."""

from __future__ import annotations

from pathlib import Path

from mito_data_agent.tasks import build_intent_prompt_section

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def get_system_prompt() -> str:
    """Load the system prompt for structured user-request parsing."""
    path = _PROMPTS_DIR / "system" / "parse_user_request.md"
    if path.exists():
        base = path.read_text(encoding="utf-8").strip()
    else:
        base = _DEFAULT_SYSTEM_PROMPT
    # Strip static intent section from .md if present; registry is source of truth.
    marker = "Classify intent as"
    if marker in base:
        base = base.split(marker)[0].strip()
    return f"{base}\n\n{build_intent_prompt_section()}"


_DEFAULT_SYSTEM_PROMPT = """You are the prompt-understanding module for Mito Data Agent.
Your only job is to parse an annotator's natural-language request into structured metadata.

You do NOT upload files, push to GitHub, search datasets, train models, or download external data.
You do NOT infer file-derived values such as shape (x,y,z) or # Mito from filenames alone.
If the user asks to infer shape or mitochondria count from mask files, leave shape_xyz and num_mito as null;
downstream Python tools will read the files.

Extract metadata from free-form sentences. Do not require Key: value formatting.
Use null for unknown fields. List missing required metadata in missing_fields.

Return JSON matching the ParsedUserRequest schema only. No markdown fences."""


def build_user_message(user_prompt: str) -> str:
    return f"Parse this annotator request:\n\n{user_prompt}"
