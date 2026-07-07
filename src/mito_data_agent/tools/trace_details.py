"""Deterministic formatters for per-agent trace *details* (component sub-steps).

The multi-agent trace shows, under each agent, one concise line about what its
tools did. That text is presentation, so — like ``tools/reporting.py`` owns the
run report — it lives here rather than inside the agent modules. Each function is
a pure ``result -> list[str]`` formatter the structural agent calls before
``finalize``. Kept intentionally terse (one line) so the trace stays readable.
"""

from __future__ import annotations


def parser_details(payload: dict) -> list[str]:
    n_datasets = len(payload.get("datasets") or []) or (1 if payload.get("volume") else 0)
    return [f"intent={payload.get('intent')}, {n_datasets} dataset(s)"]


def inspection_details(inspection: dict, raw, label) -> list[str]:
    return [
        f"raw exists={inspection.get('raw_file_exists')}, "
        f"label shape={inspection.get('label_shape_xyz')}, #mito={inspection.get('num_mito')}"
    ]


def observation_details(observation: dict) -> list[str]:
    return [
        f"shape={observation.get('shape_xyz')}, res={observation.get('resolution_nm')}, "
        f"#mito={observation.get('num_mito')}"
    ]


def merge_details(merged: dict) -> list[str]:
    return [
        f"shape={merged.get('shape_xyz')}, res={merged.get('resolution_nm')}, "
        f"#mito={merged.get('num_mito')}"
    ]


def validation_details(validation: dict) -> list[str]:
    missing = validation.get("missing_fields") or []
    line = f"validated → {validation.get('status')}"
    if missing:
        line += f" (missing: {', '.join(missing)})"
    return [line]
