"""LLM prompt parsing — the agent parses free-form prompts via the LLM only.

There is no rule-based fallback: this is an agentic system and prompt
understanding is the LLM's job. If no LLM backend is configured, parsing fails
loudly.
"""

from __future__ import annotations

from mito_data_agent.schemas import ParsedUserRequest
from mito_data_agent.tools.parse_prompt_llm import parse_user_prompt_with_llm

# Top-level fields a first dataset can fill when the LLM only populated
# ``datasets`` (multi-dataset prompts) and left the primary fields empty.
_PRIMARY_FIELDS = (
    "volume", "dataset", "modality", "organism", "organ", "tissue_region",
    "resolution_nm", "shape_xyz", "num_mito", "raw_file_path", "label_file_path",
    "metadata_file_path", "provenance", "source_url", "annotator",
)


def promote_primary_fields(payload: dict) -> dict:
    """Mirror the first dataset into the empty top-level fields.

    When the LLM fills only ``datasets`` (a multi-dataset prompt), the primary
    metadata/validation path has nothing to work on. Copying the first dataset up
    into the empty top-level fields gives it a primary volume to process. Pure and
    deterministic — the structural agent just calls it after parsing.
    """
    datasets = payload.get("datasets") or []
    if payload.get("volume") or not datasets:
        return payload
    first = datasets[0]
    for field in _PRIMARY_FIELDS:
        if payload.get(field) is None and first.get(field) is not None:
            payload[field] = first[field]
    return payload


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
