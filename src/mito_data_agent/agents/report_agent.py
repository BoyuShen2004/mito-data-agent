"""Report agent — flow only; all formatting lives in the reporting tool.

The agent's job is just to invoke the reporting tool and fold the result into the
shared state. How a run is rendered (text, JSON, which shape) is owned by
``mito_data_agent.tools.reporting``.
"""

from __future__ import annotations

from mito_data_agent.agents.base import finalize
from mito_data_agent.agents.state import MultiAgentState
from mito_data_agent.tools.reporting import render_report_text, write_execution_report


def report_agent(state: MultiAgentState) -> dict:
    """Assemble the final report + execution report via the reporting tool."""
    try:
        out = write_execution_report(state)  # {final_report, execution_report_path}
        return finalize(
            state,
            "report_agent",
            "success",
            {**out, "real_write_performed": False},
            f"Final report generated → {out['execution_report_path']}",
            input_keys=["agent_trace", "supervisor_decisions", "merged_metadata", "metadata_record"],
        )
    except Exception as exc:  # noqa: BLE001 — still surface a report in-state
        return finalize(
            state,
            "report_agent",
            "failed",
            {"final_report": render_report_text(state), "real_write_performed": False},
            f"Final report built but writing execution report failed: {exc}",
            input_keys=["agent_trace", "supervisor_decisions", "merged_metadata"],
            errors=[f"Execution report write failed: {exc}"],
        )
