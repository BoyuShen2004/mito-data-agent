"""Mock ReAct agent LLM for tests (scripted tool-call loop)."""

from __future__ import annotations

import re

from langchain_core.messages import AIMessage

from mito_data_agent.tools.parse_prompt_fallback import parse_user_prompt_fallback


def _enrich_parsed(user_prompt: str, parsed):
    lower = user_prompt.lower()
    updates = {}
    if not parsed.volume and "vol1" in lower:
        updates["volume"] = "vol1"
    if not parsed.dataset and "mito_data_agent_data" in lower:
        updates["dataset"] = "mito_data_agent_data"
    if not parsed.modality and "fib-sem" in lower:
        updates["modality"] = "FIB-SEM"
    if not parsed.organism and "human" in lower:
        updates["organism"] = "Human"
    if not parsed.organ and ("hela" in lower or "cervix" in lower):
        updates["organ"] = "Cervix (HeLa)"
    if not parsed.tissue_region and "interphase" in lower:
        updates["tissue_region"] = "HeLa cell interphase"
    if not parsed.raw_file_path:
        m = re.search(r"(/\S+vol1_0000\.tiff)", user_prompt)
        if m:
            updates["raw_file_path"] = m.group(1)
    if not parsed.label_file_path:
        m = re.search(r"(/\S+vol1\.tiff)", user_prompt)
        if m:
            updates["label_file_path"] = m.group(1)
    if not parsed.resolution_nm and ("8x8x40" in lower or "8×8×40" in lower):
        updates["resolution_nm"] = (8.0, 8.0, 40.0)
    if updates:
        return parsed.model_copy(update=updates)
    return parsed


def _upload_script(parsed) -> list[dict]:
    raw = parsed.raw_file_path or "/tmp/raw.tiff"
    label = parsed.label_file_path or "/tmp/label.tiff"
    merge_args = {
        k: v
        for k, v in {
            "volume": parsed.volume,
            "dataset": parsed.dataset,
            "modality": parsed.modality,
            "organism": parsed.organism,
            "organ": parsed.organ,
            "tissue_region": parsed.tissue_region,
            "organism": parsed.organism,
            "organ": parsed.organ,
            "tissue_region": parsed.tissue_region,
            "resolution_nm": list(parsed.resolution_nm) if parsed.resolution_nm else None,
            "raw_file_path": raw,
            "label_file_path": label,
        }.items()
        if v is not None
    }
    return [
        {
            "tool_calls": [
                {"id": "1", "name": "inspect_files", "args": {"raw_file_path": raw, "label_file_path": label}}
            ]
        },
        {
            "tool_calls": [
                {
                    "id": "2",
                    "name": "extract_volume_observations",
                    "args": {"raw_file_path": raw, "label_file_path": label},
                }
            ]
        },
        {"tool_calls": [{"id": "3", "name": "merge_volume_metadata", "args": merge_args}]},
        {"tool_calls": [{"id": "4", "name": "validate_mitoverse_metadata", "args": {}}]},
        {"tool_calls": [{"id": "5", "name": "generate_hf_staging", "args": {}}]},
        {"tool_calls": [{"id": "6", "name": "generate_mitoverse_update", "args": {}}]},
        {"tool_calls": [{"id": "7", "name": "pseudo_upload_hf", "args": {}}]},
        {"tool_calls": [{"id": "8", "name": "pseudo_push_github", "args": {}}]},
        {"tool_calls": [{"id": "9", "name": "write_execution_report", "args": {}}]},
        {"content": "Upload preparation complete. See execution report for artifact paths."},
    ]


class ScriptedAgentLLM:
    """Deterministic llm → tool loop for pytest."""

    def __init__(self, user_prompt: str):
        parsed = _enrich_parsed(user_prompt, parse_user_prompt_fallback(user_prompt))
        lower = user_prompt.lower()
        if any(k in lower for k in ["what data", "currently have", "list my", "list local"]):
            self._script = [
                {"tool_calls": [{"id": "1", "name": "list_local_data", "args": {}}]},
                {"content": "Listed local annotated volumes from the data directory."},
            ]
        elif parsed.intent == "unsupported_request":
            self._script = [
                {
                    "content": (
                        "This request is out of scope. I cannot search external datasets "
                        "or train models. I can list local data or prepare an upload."
                    )
                }
            ]
        elif parsed.intent in ("upload_annotation", "metadata_only_update", "check_upload_readiness"):
            self._script = _upload_script(parsed)
        else:
            self._script = [{"content": "Done."}]
        self._i = 0

    def invoke(self, messages, tools):
        if self._i >= len(self._script):
            return AIMessage(content="Done.")
        step = self._script[self._i]
        self._i += 1
        if step.get("tool_calls"):
            return AIMessage(content="", tool_calls=step["tool_calls"])
        return AIMessage(content=step.get("content", "Done."))
