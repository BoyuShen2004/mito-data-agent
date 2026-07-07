"""Validation agent — wraps the existing required-column validator."""

from __future__ import annotations

from mito_data_agent.agents.base import finalize
from mito_data_agent.agents.state import MultiAgentState
from mito_data_agent.tools.trace_details import validation_details
from mito_data_agent.tools.validate_metadata import validate_required_metadata


def validation_agent(state: MultiAgentState) -> dict:
    """Validate merged metadata against the required MitoVerse columns.

    Adds an explicit ``status`` field (``"passed"``/``"failed"``) that the
    supervisor uses to decide whether to continue to staging or route to the
    report agent.
    """
    merged = state.get("merged_metadata") or {}
    result = validate_required_metadata(merged)
    validation = result.model_dump()
    validation["status"] = "passed" if result.success else "failed"

    if result.success:
        summary = "Validation passed — all required columns present."
    else:
        summary = f"Validation failed — missing: {', '.join(result.missing_fields)}"

    return finalize(
        state,
        "validation_agent",
        "success",
        {"schema_validation": validation},
        summary,
        input_keys=["merged_metadata"],
        details=validation_details(validation),
        warnings=list(result.warnings),
    )
