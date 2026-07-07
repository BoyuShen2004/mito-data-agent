"""Deterministic (non-LLM) prompt parser — TEST SCAFFOLDING ONLY.

Production parsing is LLM-only (see ``tools/parse_prompt.py``). This module keeps
a rule-based parser purely so the test suite can run offline without a live LLM.
It is not imported by any production code path.
"""

from __future__ import annotations

from mito_data_agent.schemas import ParsedUserRequest
from mito_data_agent.utils.paths import normalize_stored_path
from mito_data_agent.utils.text import (
    normalize_key,
    parse_int_from_text,
    parse_resolution_string,
    parse_shape_string,
)

_FIELD_MAP: dict[str, str] = {
    "volume": "volume",
    "dataset": "dataset",
    "modality": "modality",
    "organism": "organism",
    "organ": "organ",
    "tissue_region": "tissue_region",
    "tissue": "tissue_region",
    "resolution": "resolution_nm",
    "shape": "shape_xyz",
    "num_mito": "num_mito",
    "mito": "num_mito",
    "raw_file": "raw_file_path",
    "label_file": "label_file_path",
    "metadata_file": "metadata_file_path",
    "metadata": "metadata_file_path",
    "metadata_path": "metadata_file_path",
    "provenance": "provenance",
    "source_url": "source_url",
    "annotator": "annotator",
}


def _infer_intent(prompt: str) -> str:
    lower = prompt.lower()
    list_local_keywords = [
        "what data do i have",
        "what data do i currently have",
        "what do i have",
        "list my data",
        "list my volumes",
        "list local",
        "show local",
        "local datasets",
        "local data",
        "what is in",
        "what's in",
        "available data",
        "currently have",
    ]
    if any(kw in lower for kw in list_local_keywords):
        return "list_local_data"
    dataset_search_keywords = [
        "existing dataset", "existing datasets", "list dataset", "search dataset",
        "browse dataset online", "check the existing", "check existing",
    ]
    if any(kw in lower for kw in dataset_search_keywords):
        return "unsupported_request"
    if any(kw in lower for kw in ["check readiness", "ready for", "check whether", "check if"]):
        return "check_upload_readiness"
    if any(kw in lower for kw in ["metadata only", "only metadata", "only the mitoverse metadata"]):
        return "metadata_only_update"
    if any(kw in lower for kw in ["upload", "hugging face", "hf", "prepare upload", "update mitoverse"]):
        return "upload_annotation"
    if any(kw in lower for kw in ["check", "validate", "inspect"]):
        return "check_upload_readiness"
    return "unsupported_request"


def _infer_requested_actions(prompt: str, parsed: dict) -> list[str]:
    lower = prompt.lower()
    actions: list[str] = []
    if any(kw in lower for kw in ["hugging face", "huggingface", " hf ", "upload", "staging"]):
        actions.append("prepare_hf_upload")
    if any(kw in lower for kw in ["mitoverse", "metadata update", "metadata row"]):
        actions.append("update_mitoverse_metadata")
    if parsed.get("raw_file_path") or parsed.get("label_file_path"):
        actions.append("check_files")
    if any(kw in lower for kw in ["github", " pr ", "pull request"]):
        actions.append("open_github_pr")
    return actions


def _parse_labeled_lines(prompt: str) -> dict:
    fields: dict = {}
    notes: list[str] = []
    for line in prompt.splitlines():
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        key_part, _, value_part = stripped.partition(":")
        key_norm = normalize_key(key_part).lstrip("#").strip("_")
        if key_norm in ("mito", "num_mito") or key_part.strip().startswith("#"):
            key_norm = "num_mito"
        value = value_part.strip()
        if not value:
            continue
        field_name = _FIELD_MAP.get(key_norm)
        if field_name is None:
            notes.append(f"Unrecognized field: {key_part.strip()}")
            continue
        if field_name == "resolution_nm":
            fields[field_name] = parse_resolution_string(value)
        elif field_name == "shape_xyz":
            fields[field_name] = parse_shape_string(value)
        elif field_name == "num_mito":
            fields[field_name] = parse_int_from_text(value)
        else:
            fields[field_name] = value
    fields["_notes"] = notes
    return fields


def parse_user_prompt_fallback(user_prompt: str) -> ParsedUserRequest:
    """Rule-based parser — fallback only, not LLM-powered."""
    fields = _parse_labeled_lines(user_prompt)
    notes = fields.pop("_notes", [])
    notes.insert(0, "WARNING: Rule-based fallback parser used (not LLM-powered).")

    parsed: dict = {
        "intent": _infer_intent(user_prompt),
        "volume": fields.get("volume"),
        "dataset": fields.get("dataset"),
        "modality": fields.get("modality"),
        "organism": fields.get("organism"),
        "organ": fields.get("organ"),
        "tissue_region": fields.get("tissue_region"),
        "resolution_nm": fields.get("resolution_nm"),
        "shape_xyz": fields.get("shape_xyz"),
        "num_mito": fields.get("num_mito"),
        "raw_file_path": normalize_stored_path(fields.get("raw_file_path")),
        "label_file_path": normalize_stored_path(fields.get("label_file_path")),
        "metadata_file_path": normalize_stored_path(fields.get("metadata_file_path")),
        "provenance": fields.get("provenance"),
        "source_url": fields.get("source_url"),
        "annotator": fields.get("annotator"),
        "notes": notes,
        "missing_fields": [],
        "requested_actions": [],
    }
    parsed["requested_actions"] = _infer_requested_actions(user_prompt, parsed)
    return ParsedUserRequest(**parsed)
