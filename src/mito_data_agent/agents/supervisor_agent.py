"""Supervisor node — central LLM-driven router for the multi-agent workflow.

The supervisor performs no task work; it only decides which worker agent runs
next (or ``finish``). Routing is delegated to a :class:`SupervisorPolicy`; the
default is the LLM-driven :class:`~mito_data_agent.agents.supervisor_llm.LLMSupervisor`.
The interface makes the policy swappable, but there is no rule-based routing in
the production path.
"""

from __future__ import annotations

from typing import Protocol

from mito_data_agent.agents.base import next_step
from mito_data_agent.agents.registry import is_missing
from mito_data_agent.agents.state import ALLOWED_NEXT_AGENTS, MultiAgentState
from mito_data_agent.agents.supervisor_llm import LLMSupervisor

# Safety cap: the agentic loop must terminate even if the LLM misbehaves. This is
# a guardrail, not routing logic.
MAX_SUPERVISOR_STEPS = 24


class SupervisorPolicy(Protocol):
    """Interface for supervisor routing policies (LLM-driven by default)."""

    def decide(self, state: MultiAgentState) -> dict:  # pragma: no cover - protocol
        """Return ``{"next_agent": ..., "reason": ..., "confidence": ...}``."""
        ...


def _safe_forward_decision(state: MultiAgentState, error: Exception) -> dict:
    """Error-recovery routing used ONLY when the LLM supervisor call fails.

    This is not the router — it is a safety net that keeps a run from crashing on a
    transient LLM outage/timeout. It advances by data dependency so the durable
    work (recording the parsed metadata) still happens before the report.
    """
    note = f"LLM routing unavailable ({type(error).__name__}); "
    parsed = state.get("parsed_request") or {}
    has_metadata = bool(parsed.get("volume") or parsed.get("datasets"))
    merged_ready = not is_missing(state.get("merged_metadata"))

    if is_missing(state.get("parsed_request")):
        nxt, why = "input_parser_agent", "parsing first"
    elif has_metadata and is_missing(state.get("merged_metadata")):
        nxt, why = "metadata_agent", "merging metadata"
    elif merged_ready and is_missing(state.get("schema_validation")):
        nxt, why = "validation_agent", "validating metadata"
    elif merged_ready and is_missing(state.get("metadata_record")):
        nxt, why = "metadata_record_agent", "recording metadata"
    elif is_missing(state.get("final_report")):
        nxt, why = "report_agent", "producing a report with work done so far"
    else:
        nxt, why = "finish", "finishing"
    return {"next_agent": nxt, "reason": note + why + " (fallback).", "confidence": "low"}


# Default production policy: fully LLM-driven.
_DEFAULT_POLICY: SupervisorPolicy = LLMSupervisor()


def make_supervisor_node(policy: SupervisorPolicy | None = None):
    """Return a LangGraph node function bound to a routing policy."""
    policy = policy or _DEFAULT_POLICY

    def supervisor_agent(state: MultiAgentState) -> dict:
        decisions = state.get("supervisor_decisions", []) or []

        # Guardrail: force termination if the loop runs away.
        if len(decisions) >= MAX_SUPERVISOR_STEPS:
            next_agent = "report_agent" if is_missing(state.get("final_report")) else "finish"
            decision = {
                "next_agent": next_agent,
                "reason": f"step cap ({MAX_SUPERVISOR_STEPS}) reached; forcing termination.",
                "confidence": "low",
            }
        else:
            try:
                decision = policy.decide(state)
            except Exception as exc:  # noqa: BLE001 — LLM timeout/outage must not crash the run
                decision = _safe_forward_decision(state, exc)
            next_agent = decision.get("next_agent", "finish")
            if next_agent not in ALLOWED_NEXT_AGENTS:
                # Never route outside the allow-list.
                next_agent = "report_agent" if is_missing(state.get("final_report")) else "finish"
                decision = {
                    "next_agent": next_agent,
                    "reason": f"policy returned an invalid target; coerced to '{next_agent}'.",
                    "confidence": "low",
                }

        step = next_step(state)
        record = {
            "step": step,
            "previous_agent": state.get("current_agent"),
            "next_agent": next_agent,
            "reason": decision.get("reason", ""),
            "confidence": decision.get("confidence", "medium"),
        }
        return {
            "current_agent": "supervisor_agent",
            "next_agent": next_agent,
            "supervisor_reason": decision.get("reason", ""),
            "step": step,
            "supervisor_decisions": decisions + [record],
        }

    return supervisor_agent


def route_from_supervisor(state: MultiAgentState) -> str:
    """Conditional-edge selector: return the supervisor's chosen next node."""
    return state.get("next_agent") or "finish"
