"""Deterministic formatters for per-agent trace *details* (component sub-steps).

The multi-agent trace shows, under each agent, the tool-level things it did. That
text is presentation, so — like ``tools/reporting.py`` owns the run report — it
lives here rather than inside the agent modules. Each function is a pure
``result -> list[str]`` formatter the structural agent calls before ``finalize``.
"""

from __future__ import annotations


def parser_details(payload: dict) -> list[str]:
    n_datasets = len(payload.get("datasets") or []) or (1 if payload.get("volume") else 0)
    details = [
        f"intent = {payload.get('intent')}",
        f"datasets found: {n_datasets}",
    ]
    if payload.get("raw_file_path") or payload.get("label_file_path"):
        details.append(
            f"files: raw={payload.get('raw_file_path')}, label={payload.get('label_file_path')}"
        )
    return details


def inspection_details(inspection: dict, raw, label) -> list[str]:
    return [
        f"inspect_files(raw={raw}, label={label})",
        f"raw: exists={inspection.get('raw_file_exists')}, shape={inspection.get('raw_shape_xyz')}",
        f"label: exists={inspection.get('label_file_exists')}, shape={inspection.get('label_shape_xyz')}, "
        f"#mito={inspection.get('num_mito')}",
    ]


def observation_details(observation: dict) -> list[str]:
    return [
        f"resolution_nm={observation.get('resolution_nm')} (source: {observation.get('resolution_source')})",
        f"shape_xyz={observation.get('shape_xyz')} (source: {observation.get('shape_source')})",
        f"num_mito={observation.get('num_mito')} (source: {observation.get('num_mito_source')})",
    ]


def merge_details(merged: dict) -> list[str]:
    return [
        f"merged {key}={merged.get(key)} (source: {merged.get(key + '_source', 'prompt')})"
        for key in ("resolution_nm", "shape_xyz", "num_mito")
        if merged.get(key) is not None
    ]


def validation_details(validation: dict) -> list[str]:
    details = [f"validate_required_metadata → {validation.get('status')}"]
    missing = validation.get("missing_fields") or []
    if missing:
        details.append(f"missing required fields: {', '.join(missing)}")
    return details
