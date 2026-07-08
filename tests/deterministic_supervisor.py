"""Deterministic supervisor model — TEST SCAFFOLDING ONLY.

Production routing is LLM-driven (``agents/supervisor_llm.py``). To keep the test
suite offline and deterministic, this stand-in implements the ``route(context)``
contract that ``LLMSupervisor`` calls, computing the "obvious" next agent from
the same context an LLM would see. The production ``LLMSupervisor`` code
(context building, allow-list enforcement, trace bookkeeping) still runs — only
the network call is replaced.
"""

from __future__ import annotations

from typing import Any

_CATALOG_KEYWORDS = (
    "already in",
    "exists in",
    "in the collection",
    "in the mitoverse",
    "look up",
    "lookup",
    "search mitoverse",
    "catalog",
)

# (state_field, agent) steps per mode — mirrors sensible upload/readiness/etc flow.
_PLANS: dict[str, list[tuple[str, str]]] = {
    "upload": [
        ("file_inspection", "dataset_inspector_agent"),
        ("volume_observation", "observation_agent"),
        ("merged_metadata", "metadata_agent"),
        ("schema_validation", "validation_agent"),
        ("metadata_record", "metadata_record_agent"),
        ("generated_artifacts", "staging_agent"),
        ("hf_upload_plan", "upload_planning_agent"),
        ("github_push_plan", "website_update_agent"),
        ("final_report", "report_agent"),
    ],
    "readiness": [
        ("file_inspection", "dataset_inspector_agent"),
        ("volume_observation", "observation_agent"),
        ("merged_metadata", "metadata_agent"),
        ("schema_validation", "validation_agent"),
        ("metadata_record", "metadata_record_agent"),
        ("final_report", "report_agent"),
    ],
    "metadata_only": [
        ("file_inspection", "dataset_inspector_agent"),
        ("volume_observation", "observation_agent"),
        ("merged_metadata", "metadata_agent"),
        ("schema_validation", "validation_agent"),
        ("metadata_record", "metadata_record_agent"),
        ("generated_artifacts", "staging_agent"),
        ("github_push_plan", "website_update_agent"),
        ("final_report", "report_agent"),
    ],
    "inventory": [
        ("local_data_inventory", "inventory_agent"),
        ("final_report", "report_agent"),
    ],
    "catalog": [
        ("mitoverse_lookup", "catalog_agent"),
        ("final_report", "report_agent"),
    ],
    "storage": [
        ("storage_info", "storage_info_agent"),
        ("final_report", "report_agent"),
    ],
    "unsupported": [
        ("final_report", "report_agent"),
    ],
}

_INTENT_TO_MODE = {
    "list_local_data": "inventory",
    "upload_annotation": "upload",
    "metadata_only_update": "metadata_only",
    "check_upload_readiness": "readiness",
}


_TASK_MARKERS = (
    "upload", "metadata", "record", "recorded", "volume", "dataset", "readiness",
    "mitoverse", "inventory", "data", "where", "store", "stored", "saved", ".tif",
    "catalog", "collection",
)
_CHAT_MARKERS = (
    "hello", "how are you", "what can you do", "who are you", "thank", "joke",
    "weather", "你好", "聊天",
)


def _is_chat(lower: str) -> bool:
    """Casual/general conversation (not a data task)."""
    if any(t in lower for t in _TASK_MARKERS):
        return False
    return any(c in lower for c in _CHAT_MARKERS)


def _is_storage_question(lower: str) -> bool:
    if "what have you recorded" in lower or "what did you record" in lower:
        return True
    if "where" in lower and any(
        w in lower for w in ("keep", "store", "stored", "saved", "metadata", "record")
    ):
        return True
    return False


def _mode(context: dict[str, Any]) -> str:
    lower = (context.get("user_prompt") or "").lower()
    # Storage/location questions take precedence — the parsed intent (often
    # list_local_data) is unreliable for these.
    if _is_storage_question(lower):
        return "storage"
    intent = context.get("parsed_intent")
    if intent in _INTENT_TO_MODE:
        return _INTENT_TO_MODE[intent]
    if any(kw in lower for kw in _CATALOG_KEYWORDS):
        return "catalog"
    return "unsupported"


def _decision(next_agent: str, reason: str = "") -> dict[str, Any]:
    return {"next_agent": next_agent, "reason": reason or next_agent, "confidence": "high"}


class ScriptedSupervisorModel:
    """Implements the ``route(context) -> decision`` contract deterministically."""

    def route(self, context: dict[str, Any]) -> dict[str, Any]:
        progress = context.get("progress", {})
        lower = (context.get("user_prompt") or "").lower()

        # Casual conversation: reply directly (no parsing), then finish.
        if _is_chat(lower):
            if not progress.get("chat_response"):
                return _decision("chat_agent", "casual conversation")
            return _decision("finish", "chat replied")

        if not progress.get("parsed_request"):
            return _decision("input_parser_agent", "prompt not parsed")

        plan = _PLANS[_mode(context)]
        for field, agent in plan:
            if field == "schema_validation":
                if not progress.get("schema_validation"):
                    return _decision("validation_agent")
                if context.get("validation_status") == "failed":
                    # Still record what was parsed, then report.
                    if not progress.get("metadata_record"):
                        return _decision("metadata_record_agent", "record metadata before reporting")
                    if not progress.get("final_report"):
                        return _decision("report_agent", "validation failed")
                    return _decision("finish", "validation failed and reported")
                continue
            if not progress.get(field):
                return _decision(agent)
        return _decision("finish", "all steps complete")
