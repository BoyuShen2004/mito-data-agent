"""Input parser agent — wraps the existing LLM-first prompt parser."""

from __future__ import annotations

from mito_data_agent.agents.base import finalize
from mito_data_agent.agents.state import MultiAgentState
from mito_data_agent.tools.parse_prompt import parse_user_prompt, promote_primary_fields
from mito_data_agent.tools.trace_details import parser_details


def input_parser_agent(state: MultiAgentState) -> dict:
    """Parse the free-form user prompt into structured fields via the LLM.

    Reuses :func:`parse_user_prompt` (LLM-only). On failure the workflow does not
    crash: an error is recorded and a minimal ``parsed_request`` is set so the
    supervisor can still route to the report.
    """
    prompt = state.get("user_prompt", "") or ""
    try:
        parsed = parse_user_prompt(prompt)
        payload = promote_primary_fields(parsed.model_dump())
        outputs = {
            "parsed_request": payload,
            "raw_file_path": payload.get("raw_file_path"),
            "label_file_path": payload.get("label_file_path"),
            "metadata_file_path": payload.get("metadata_file_path"),
        }
        return finalize(
            state,
            "input_parser_agent",
            "success",
            outputs,
            f"Parsed user request (intent={payload.get('intent')}).",
            input_keys=["user_prompt"],
            details=parser_details(payload),
        )
    except Exception as exc:  # noqa: BLE001 — keep the workflow alive
        payload = {"intent": "unsupported_request", "parse_error": str(exc)}
        return finalize(
            state,
            "input_parser_agent",
            "failed",
            {"parsed_request": payload},
            f"Prompt parsing failed: {exc}",
            input_keys=["user_prompt"],
            errors=[f"Prompt parsing failed: {exc}"],
        )
