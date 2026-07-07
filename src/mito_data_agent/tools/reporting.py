"""Reporting tool — owns ALL run-result formatting.

The agents decide *flow*; this tool decides *presentation*. Everything that
renders a run (the human-readable execution report, the structured summary, the
CLI printout, and the execution-report JSON) lives here so the agent modules stay
free of hardcoded output formats.

Public API:
    write_execution_report(state) -> {"final_report", "execution_report_path"}
    build_summary(state)          -> dict   (structured; includes all datasets)
    render_report_text(state)     -> str    (human-readable report)
    render_cli_summary(summary)   -> str    (terminal printout)
"""

from __future__ import annotations

from typing import Any

from mito_data_agent.utils.io import write_json
from mito_data_agent.utils.paths import ensure_output_dirs, get_outputs_dir

_DRY_RUN_NOTE = "NOTE: All external writes are pseudo/dry-run. real_write_performed=False."


# --------------------------------------------------------------------------- #
# Recorded-dataset helpers (a single prompt may record several datasets).
# --------------------------------------------------------------------------- #
def recorded_datasets(state: dict) -> list[dict]:
    """The datasets that were recorded this run (empty if none)."""
    record = state.get("metadata_record") or {}
    return record.get("volumes", []) if record.get("recorded") else []


def _dataset_lines(vol: dict) -> list[str]:
    md = vol.get("metadata", {})
    val = vol.get("validation_success")
    val_txt = "n/a" if val is None else ("passed" if val else "failed")
    return [
        f"  ● {vol.get('volume')}   [validation: {val_txt}]  (version #{vol.get('times_recorded')})",
        f"      dataset={md.get('dataset')}, modality={md.get('modality')}, "
        f"organism={md.get('organism')}, organ={md.get('organ')}, tissue={md.get('tissue_region')}",
        f"      resolution_nm={md.get('resolution_nm')} ({md.get('resolution_source', 'prompt')}), "
        f"shape={md.get('shape_xyz')} ({md.get('shape_source', 'prompt')}), "
        f"#mito={md.get('num_mito')} ({md.get('num_mito_source', 'prompt')})",
        f"      sidecar: {vol.get('sidecar_path')}",
    ]


# --------------------------------------------------------------------------- #
# Human-readable report text.
# --------------------------------------------------------------------------- #
def render_report_text(state: dict) -> str:
    """Render the execution report, choosing a shape from the work products."""
    inventory = state.get("local_data_inventory") or {}
    lookup = state.get("mitoverse_lookup") or {}
    storage = state.get("storage_info") or {}
    merged = state.get("merged_metadata") or {}
    validation = state.get("schema_validation") or {}
    parsed = state.get("parsed_request") or {}
    intent = parsed.get("intent", "unsupported_request")
    run_id = state.get("run_id")

    if storage:
        return _render_storage(state, storage, run_id)
    if inventory:
        return _render_inventory(inventory, run_id)
    if lookup:
        return _render_lookup(lookup, run_id)

    records = recorded_datasets(state)
    if not merged and not records:
        return "\n".join(
            [
                "Mito Data Agent — Execution Report (UNSUPPORTED / NO WORK)",
                f"Run ID: {run_id}",
                f"Parsed intent: {intent}",
                "",
                "The request did not map to an upload/readiness/metadata task and "
                "produced no metadata to report.",
                "\nNOTE: No external writes. real_write_performed=False.",
            ]
        )
    return _render_metadata(state, merged, validation, intent, run_id, records)


def _render_storage(state: dict, storage: dict, run_id) -> str:
    vols = storage.get("recorded_volumes", [])
    return "\n".join(
        [
            "Mito Data Agent — Where things are stored",
            f"Run ID: {run_id}",
            "",
            f"Recorded metadata ledger:   {storage.get('metadata_store')}",
            f"  (absolute: {storage.get('metadata_store_abs')})",
            f"Per-volume sidecar files:    {storage.get('data_dir_sidecars')}/<volume>.metadata.json",
            f"  (absolute data dir: {storage.get('data_dir_abs')})",
            f"Execution reports:           {storage.get('execution_reports_dir')}/<run_id>.json",
            f"HF staging artifacts:        {storage.get('hf_staging_dir')}/",
            f"MitoVerse update files:      {storage.get('mitoverse_updates_dir')}/",
            "",
            f"Volumes recorded so far ({storage.get('recorded_count', 0)}): "
            + (", ".join(v for v in vols if v) or "none"),
            "",
            "Query them with: python -m mito_data_agent records",
        ]
    )


def _render_inventory(inventory: dict, run_id) -> str:
    volumes = inventory.get("volumes", [])
    return "\n".join(
        [
            f"Mito Data Agent — Local Data Inventory ({len(volumes)} volume(s))",
            f"Run ID: {run_id}",
            f"Local data dir: {inventory.get('data_dir')}",
            "",
            *[
                f"  - {v.get('volume_id')} (shape={v.get('label_shape_xyz')}, #mito={v.get('num_mito')})"
                for v in volumes[:20]
            ],
            "\nNOTE: Read-only scan. No external writes. real_write_performed=False.",
        ]
    )


def _render_lookup(lookup: dict, run_id) -> str:
    return "\n".join(
        [
            "Mito Data Agent — MitoVerse Catalog Lookup",
            f"Run ID: {run_id}",
            f"Query: {lookup.get('query')}",
            f"Found in MitoVerse: {lookup.get('found')}",
            f"Message: {lookup.get('message', '')}",
            *([f"Lookup error: {lookup['lookup_error']}"] if lookup.get("lookup_error") else []),
            "\nNOTE: Read-only catalog lookup. No external writes. real_write_performed=False.",
        ]
    )


def _render_metadata(state, merged, validation, intent, run_id, records) -> str:
    status = "SUCCESS" if validation.get("success") else "INCOMPLETE"
    lines = [
        f"Mito Data Agent — Execution Report ({status})",
        f"Run ID: {run_id}",
        f"Parsed intent: {intent}",
    ]

    if records:
        record = state.get("metadata_record") or {}
        lines.append("")
        lines.append(
            f"Recorded {record.get('count', len(records))} dataset(s) → store "
            f"({record.get('store_path')}) + data-dir sidecars:"
        )
        for vol in records:
            lines.append("")
            lines.extend(_dataset_lines(vol))
    else:
        lines += [
            "",
            f"Volume:        {merged.get('volume')}",
            f"Dataset:       {merged.get('dataset')}",
            f"Modality:      {merged.get('modality')}",
            f"Organism:      {merged.get('organism')}",
            f"Resolution nm: {merged.get('resolution_nm')} (source: {merged.get('resolution_source', 'prompt')})",
            f"Shape (x,y,z): {merged.get('shape_xyz')} (source: {merged.get('shape_source', 'prompt')})",
            f"# Mito:        {merged.get('num_mito')} (source: {merged.get('num_mito_source', 'prompt')})",
        ]

    lines.append("")
    lines.append(
        f"Validation (primary '{merged.get('volume')}'): "
        f"{'passed' if validation.get('success') else 'failed'}"
    )
    if not validation.get("success"):
        lines.append(f"Missing fields: {', '.join(validation.get('missing_fields', []))}")

    hf_plan = state.get("hf_upload_plan") or {}
    gh_plan = state.get("github_push_plan") or {}
    if hf_plan:
        lines.append(
            f"Pseudo HF upload:   signal={hf_plan.get('signal')}, "
            f"real_write={hf_plan.get('real_write_performed', False)}"
        )
    if gh_plan:
        lines.append(
            f"Pseudo GitHub push: signal={gh_plan.get('signal')}, "
            f"real_write={gh_plan.get('real_write_performed', False)}"
        )

    lines.append("")
    lines.append(_DRY_RUN_NOTE)

    conflicts = state.get("conflicts", []) or []
    if conflicts:
        lines.append(f"\nConflicts auto-resolved in favour of the file ({len(conflicts)}):")
        for c in conflicts:
            lines.append(f"  - [{c.get('agent', '?')}] {c.get('message')}")

    warnings = state.get("warnings", []) or []
    errors = state.get("errors", []) or []
    if warnings:
        lines.append(f"\nWarnings ({len(warnings)}):")
        for w in warnings[:10]:
            lines.append(f"  - [{w.get('agent', '?')}] {w.get('message')}")
    if errors:
        lines.append(f"\nErrors ({len(errors)}):")
        for e in errors:
            lines.append(f"  - [{e.get('agent', '?')}] {e.get('message')}")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Execution-report JSON + writing.
# --------------------------------------------------------------------------- #
def build_execution_report(state: dict, report_text: str) -> dict:
    """Assemble the full JSON run record (trace + artifacts + plans + report)."""
    validation = state.get("schema_validation") or {}
    return {
        "report_type": "multi_agent_execution_report",
        "status": "completed" if validation.get("success") else "incomplete",
        "run_id": state.get("run_id"),
        "real_write_performed": False,
        "parsed_request": state.get("parsed_request"),
        "file_inspection": state.get("file_inspection"),
        "volume_observation": state.get("volume_observation"),
        "merged_metadata": state.get("merged_metadata"),
        "schema_validation": validation,
        "metadata_record": state.get("metadata_record"),
        "generated_artifacts": state.get("generated_artifacts", {}),
        "hf_staging_dir": state.get("hf_staging_dir"),
        "mitoverse_update_files": state.get("mitoverse_update_files", []),
        "hf_upload_plan": state.get("hf_upload_plan"),
        "github_push_plan": state.get("github_push_plan"),
        "local_data_inventory": state.get("local_data_inventory"),
        "mitoverse_lookup": state.get("mitoverse_lookup"),
        "mitoverse_search": state.get("mitoverse_search"),
        "storage_info": state.get("storage_info"),
        "agent_trace": state.get("agent_trace", []),
        "supervisor_decisions": state.get("supervisor_decisions", []),
        "errors": state.get("errors", []),
        "warnings": state.get("warnings", []),
        "conflicts": state.get("conflicts", []),
        "final_report": report_text,
    }


def write_execution_report(state: dict) -> dict:
    """Render the report + JSON and write it. Returns fields for the agent state."""
    ensure_output_dirs()
    report_text = render_report_text(state)
    doc = build_execution_report(state, report_text)
    run_id = state.get("run_id", "unknown")
    path = write_json(get_outputs_dir() / "execution_reports" / f"{run_id}.json", doc)
    return {"final_report": report_text, "execution_report_path": path}


# --------------------------------------------------------------------------- #
# Structured summary + CLI printout.
# --------------------------------------------------------------------------- #
def build_summary(state: dict) -> dict[str, Any]:
    """Structured summary for CLI / callers (includes every recorded dataset)."""
    merged = state.get("merged_metadata") or {}
    validation = state.get("schema_validation") or {}
    hf_plan = state.get("hf_upload_plan") or {}
    gh_plan = state.get("github_push_plan") or {}
    parsed = state.get("parsed_request") or {}
    return {
        "run_id": state.get("run_id"),
        "intent": parsed.get("intent"),
        "execution_report_path": state.get("execution_report_path"),
        "final_report": state.get("final_report"),
        "validation_success": validation.get("success"),
        "validation_status": validation.get("status"),
        "missing_fields": validation.get("missing_fields", []),
        "volume": merged.get("volume"),
        "recorded_datasets": recorded_datasets(state),
        "hf_staging_dir": state.get("hf_staging_dir"),
        "mitoverse_update_files": state.get("mitoverse_update_files", []),
        "hf_upload_signal": hf_plan.get("signal"),
        "github_push_signal": gh_plan.get("signal"),
        "real_write_performed": state.get("real_write_performed", False),
        "metadata_record": state.get("metadata_record"),
        "storage_info": state.get("storage_info"),
        "local_data_inventory": state.get("local_data_inventory"),
        "mitoverse_lookup": state.get("mitoverse_lookup"),
        "mitoverse_search": state.get("mitoverse_search"),
        "agent_trace": state.get("agent_trace", []),
        "supervisor_decisions": state.get("supervisor_decisions", []),
        "errors": state.get("errors", []),
        "warnings": state.get("warnings", []),
        "conflicts": state.get("conflicts", []),
    }


def render_cli_summary(summary: dict) -> str:
    """Terminal printout — shows every recorded dataset, not just the primary."""
    lines = [
        "",
        "=== Mito Data Agent Summary ===",
        f"Run ID:              {summary.get('run_id')}",
        f"Intent:              {summary.get('intent')}",
        f"Execution report:    {summary.get('execution_report_path')}",
        f"Validation:          {summary.get('validation_status')} "
        f"(success={summary.get('validation_success')})",
    ]
    if summary.get("missing_fields"):
        lines.append(f"Missing fields:      {summary['missing_fields']}")

    records = summary.get("recorded_datasets", [])
    if records:
        lines.append(f"Recorded datasets:   {len(records)}")
        for v in records:
            md = v.get("metadata", {})
            lines.append(
                f"  - {v.get('volume')}: shape={md.get('shape_xyz')} "
                f"({md.get('shape_source', 'prompt')}), #mito={md.get('num_mito')} "
                f"({md.get('num_mito_source', 'prompt')}) → {v.get('sidecar_path')}"
            )

    inv = summary.get("local_data_inventory")
    if inv:
        lines.append(f"Local data dir:      {inv.get('data_dir')}")
        lines.append(f"Volumes on disk:     {len(inv.get('volumes', []))}")

    if summary.get("hf_upload_signal"):
        lines.append(f"Pseudo HF upload:    signal={summary.get('hf_upload_signal')}")
    if summary.get("github_push_signal"):
        lines.append(f"Pseudo GitHub push:  signal={summary.get('github_push_signal')}")
    lines.append(f"Real external write: {summary.get('real_write_performed')}")
    lines.append(
        f"Supervisor decisions: {len(summary.get('supervisor_decisions', []))} | "
        f"Agent steps: {len(summary.get('agent_trace', []))}"
    )
    if summary.get("conflicts"):
        lines.append(f"\nConflicts auto-resolved (file wins) ({len(summary['conflicts'])}):")
        for c in summary["conflicts"]:
            lines.append(f"  - [{c.get('agent', '?')}] {c.get('message')}")
    if summary.get("errors"):
        lines.append(f"\nErrors ({len(summary['errors'])}):")
        for e in summary["errors"]:
            lines.append(f"  - [{e.get('agent', '?')}] {e.get('message')}")
    if summary.get("warnings"):
        lines.append(f"\nWarnings ({len(summary['warnings'])}):")
        for w in summary["warnings"][:10]:
            lines.append(f"  - [{w.get('agent', '?')}] {w.get('message')}")
    return "\n".join(lines)
