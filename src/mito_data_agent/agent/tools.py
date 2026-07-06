"""Agent tools — each returns a JSON observation string for the LLM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mito_data_agent.schemas import FileInspectionResult, ParsedUserRequest, VolumeObservation
from mito_data_agent.tools.extract_volume_observations import extract_volume_observations
from mito_data_agent.tools.generate_hf_staging import generate_hf_staging_files
from mito_data_agent.tools.generate_mitoverse_update import generate_mitoverse_update_files
from mito_data_agent.tools.fetch_mitoverse_catalog import fetch_mitoverse_catalog_tool
from mito_data_agent.tools.inspect_files import inspect_files
from mito_data_agent.tools.list_local_data import list_local_data
from mito_data_agent.tools.list_mitoverse_datasets import list_mitoverse_datasets_tool
from mito_data_agent.tools.lookup_mitoverse_volume import lookup_mitoverse_volume_tool
from mito_data_agent.tools.merge_metadata import merge_prompt_and_observation_metadata
from mito_data_agent.tools.pseudo_push_github import pseudo_push_to_github
from mito_data_agent.tools.pseudo_signal import (
    _paths_exist,
    build_stub_result,
    pseudo_tool_observation,
    stub_tool_observation,
)
from mito_data_agent.tools.pseudo_upload_hf import pseudo_upload_to_hf
from mito_data_agent.tools.search_mitoverse_collection import search_mitoverse_collection_tool
from mito_data_agent.tools.validate_metadata import validate_required_metadata
from mito_data_agent.tools.write_reports import write_execution_report
from mito_data_agent.utils.paths import normalize_stored_path, safe_slug, to_relative_path


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _normalize_inspect_args(args: dict[str, Any]) -> tuple[str | None, str | None]:
    return (
        normalize_stored_path(_first(args.get("raw_file_path"), args.get("raw_file"))),
        normalize_stored_path(_first(args.get("label_file_path"), args.get("label_file"))),
    )


def _normalize_resolution(args: dict[str, Any]) -> tuple[float, float, float] | None:
    res = args.get("resolution_nm")
    if isinstance(res, list) and len(res) == 3:
        return float(res[0]), float(res[1]), float(res[2])
    text = _first(args.get("resolution"), args.get("resolution_nm"))
    if isinstance(text, str) and text.strip():
        from mito_data_agent.utils.text import parse_resolution_string

        parsed = parse_resolution_string(text)
        if parsed:
            return parsed
    return None


_CATALOG_QUERY_FIELDS = {
    "volume": {"type": "string"},
    "volume_id": {"type": "string"},
    "dataset": {"type": "string"},
    "dataset_id": {"type": "string"},
    "modality": {"type": "string"},
    "organism": {"type": "string"},
    "species": {"type": "string"},
    "organ": {"type": "string"},
    "tissue": {"type": "string"},
    "tissue_region": {"type": "string"},
    "raw_file_path": {"type": "string"},
    "label_file_path": {"type": "string"},
    "shape_xyz": {"type": "array", "items": {"type": "integer"}},
    "num_mito": {"type": "integer"},
    "limit": {"type": "integer"},
    "force_refresh": {"type": "boolean"},
}


def _catalog_query_schema(*, include_search_fields: bool = False) -> dict[str, Any]:
    props = {
        k: v
        for k, v in _CATALOG_QUERY_FIELDS.items()
        if include_search_fields or k in {
            "volume",
            "volume_id",
            "dataset",
            "dataset_id",
            "raw_file_path",
            "label_file_path",
            "force_refresh",
        }
    }
    return {"type": "object", "properties": props, "additionalProperties": False}


# OpenAI function-calling schemas (Andrew Ng: model picks tools dynamically)
OPENAI_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_local_data",
            "description": "Scan the local data directory and list paired raw/label TIFF volumes with shapes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_dir": {
                        "type": "string",
                        "description": "Optional override path; defaults to configured data directory.",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_files",
            "description": "Check raw and label TIFF existence, shapes, and basic label stats.",
            "parameters": {
                "type": "object",
                "properties": {
                    "raw_file_path": {"type": "string"},
                    "label_file_path": {"type": "string"},
                },
                "required": ["raw_file_path", "label_file_path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_volume_observations",
            "description": "Extract resolution, shape, and # Mito from files (preferred over LLM guesses).",
            "parameters": {
                "type": "object",
                "properties": {
                    "raw_file_path": {"type": "string"},
                    "label_file_path": {"type": "string"},
                    "metadata_file_path": {"type": "string"},
                    "resolution_nm": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Optional [x, y, z] nm from user prompt.",
                    },
                },
                "required": ["raw_file_path", "label_file_path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "merge_volume_metadata",
            "description": "Merge user-provided MitoVerse fields with file inspection/observation artifacts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "volume": {"type": "string"},
                    "dataset": {"type": "string"},
                    "modality": {"type": "string"},
                    "organism": {"type": "string"},
                    "organ": {"type": "string"},
                    "tissue_region": {"type": "string"},
                    "resolution_nm": {"type": "array", "items": {"type": "number"}},
                    "shape_xyz": {"type": "array", "items": {"type": "integer"}},
                    "num_mito": {"type": "integer"},
                    "raw_file_path": {"type": "string"},
                    "label_file_path": {"type": "string"},
                    "metadata_file_path": {"type": "string"},
                    "provenance": {"type": "string"},
                    "source_url": {"type": "string"},
                    "annotator": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_mitoverse_metadata",
            "description": "Validate merged metadata against required MitoVerse columns.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_hf_staging",
            "description": "Generate Hugging Face staging artifacts under outputs/ (metadata only; large TIFFs not copied).",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_mitoverse_update",
            "description": "Generate MitoVerse row JSON/CSV/patch files under outputs/.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pseudo_upload_hf",
            "description": "Plan HF upload from staging (stub — validates files, no HF API call).",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pseudo_push_github",
            "description": "Plan GitHub PR from update files (stub — no GitHub API call).",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_mitoverse_catalog",
            "description": "Download/cache the public MitoVerse catalog from Hugging Face (read-only).",
            "parameters": {
                "type": "object",
                "properties": {"force_refresh": {"type": "boolean"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_mitoverse_volume",
            "description": (
                "Check whether a volume exists in the public MitoVerse collection "
                "(https://pytorchconnectomics.github.io/mitoverse/). "
                "Accepts partial hints: volume name, dataset, or raw/label file paths."
            ),
            "parameters": _catalog_query_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_mitoverse_collection",
            "description": (
                "Search the MitoVerse catalog with any available metadata hints "
                "(volume, dataset, modality, organism, tissue, shape, file paths)."
            ),
            "parameters": _catalog_query_schema(include_search_fields=True),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_mitoverse_datasets",
            "description": "List dataset_id groups and volume counts in the MitoVerse catalog.",
            "parameters": {
                "type": "object",
                "properties": {"force_refresh": {"type": "boolean"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_execution_report",
            "description": "Write a JSON execution report summarizing this run's artifacts.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
]

TOOL_NAMES = {s["function"]["name"] for s in OPENAI_TOOL_SCHEMAS}


def execute_tool(
    name: str,
    args: dict[str, Any],
    *,
    run_id: str,
    artifacts: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Run one tool; return (observation_json, artifact_updates)."""
    updates: dict[str, Any] = {}

    if name not in TOOL_NAMES:
        return (
            _json({"error": f"Unknown tool {name!r}. Retry with a valid tool name."}),
            updates,
        )

    try:
        if name == "list_local_data":
            inv = list_local_data(args.get("data_dir"))
            payload = inv.model_dump()
            updates["local_data_inventory"] = payload
            return _json({"observation": "local_data_inventory", "data": payload}), updates

        if name == "inspect_files":
            raw_path, label_path = _normalize_inspect_args(args)
            result = inspect_files(raw_path, label_path)
            payload = result.model_dump()
            updates["file_inspection"] = payload
            return _json({"observation": "file_inspection", "data": payload}), updates

        if name == "extract_volume_observations":
            raw_path, label_path = _normalize_inspect_args(args)
            inspection = None
            if artifacts.get("file_inspection"):
                inspection = FileInspectionResult(**artifacts["file_inspection"])
            res_nm = _normalize_resolution(args)
            result = extract_volume_observations(
                raw_file_path=raw_path,
                label_file_path=label_path,
                metadata_file_path=args.get("metadata_file_path"),
                prompt_resolution_nm=res_nm,
                file_inspection=inspection,
            )
            payload = result.model_dump()
            updates["volume_observation"] = payload
            return _json({"observation": "volume_observation", "data": payload}), updates

        if name == "merge_volume_metadata":
            raw_path, label_path = _normalize_inspect_args(args)
            parsed = ParsedUserRequest(
                intent="upload_annotation",
                volume=_first(args.get("volume"), args.get("volume_id")),
                dataset=_first(args.get("dataset"), args.get("dataset_id")),
                modality=args.get("modality"),
                organism=_first(args.get("organism"), args.get("species")),
                organ=args.get("organ"),
                tissue_region=_first(args.get("tissue_region"), args.get("tissue")),
                resolution_nm=_normalize_resolution(args),
                shape_xyz=tuple(args["shape_xyz"]) if args.get("shape_xyz") else None,
                num_mito=args.get("num_mito"),
                raw_file_path=raw_path,
                label_file_path=label_path,
                metadata_file_path=args.get("metadata_file_path"),
                provenance=args.get("provenance"),
                source_url=args.get("source_url"),
                annotator=args.get("annotator"),
            )
            fi = FileInspectionResult(**artifacts["file_inspection"]) if artifacts.get("file_inspection") else None
            vo = VolumeObservation(**artifacts["volume_observation"]) if artifacts.get("volume_observation") else None
            merged = merge_prompt_and_observation_metadata(parsed, fi, vo)
            updates["merged_metadata"] = merged
            return _json({"observation": "merged_metadata", "data": merged}), updates

        if name == "validate_mitoverse_metadata":
            merged = artifacts.get("merged_metadata") or {}
            result = validate_required_metadata(merged)
            payload = result.model_dump()
            updates["schema_validation"] = payload
            return _json({"observation": "schema_validation", "data": payload}), updates

        if name == "generate_hf_staging":
            merged = artifacts.get("merged_metadata") or {}
            if not merged:
                result = build_stub_result(
                    tool_name="generate_hf_staging",
                    success=False,
                    mode="local",
                    target="outputs/hf_staging/",
                    planned_action="Generate HF staging metadata under outputs/",
                    message="Local staging failed: merged_metadata missing.",
                )
                updates["generate_hf_staging_plan"] = result.model_dump()
                return _json(stub_tool_observation(result)), updates
            staging_dir = generate_hf_staging_files(merged, run_id)
            expected = [
                f"{staging_dir}/metadata.json",
                f"{staging_dir}/manifest.json",
                f"{staging_dir}/README.md",
            ]
            ok, checked = _paths_exist(expected)
            result = build_stub_result(
                tool_name="generate_hf_staging",
                success=ok,
                mode="local",
                target=staging_dir,
                files_checked=checked,
                output_paths=checked if ok else [staging_dir],
                planned_action="Generate HF staging metadata (TIFFs not copied)",
                message=(
                    "Local staging executed (metadata only, no HF upload)."
                    if ok
                    else "Local staging failed: expected files missing."
                ),
            )
            updates["hf_staging_dir"] = staging_dir
            updates["generate_hf_staging_plan"] = result.model_dump()
            return _json(stub_tool_observation(result)), updates

        if name == "generate_mitoverse_update":
            merged = artifacts.get("merged_metadata") or {}
            if not merged:
                result = build_stub_result(
                    tool_name="generate_mitoverse_update",
                    success=False,
                    mode="local",
                    target="outputs/mitoverse_updates/",
                    planned_action="Generate MitoVerse row JSON/CSV/patch files",
                    message="Local update failed: merged_metadata missing.",
                )
                updates["generate_mitoverse_update_plan"] = result.model_dump()
                return _json(stub_tool_observation(result)), updates
            files = generate_mitoverse_update_files(merged, run_id)
            ok, checked = _paths_exist(files)
            result = build_stub_result(
                tool_name="generate_mitoverse_update",
                success=ok,
                mode="local",
                target=to_relative_path(Path(files[0]).parent) if files else "outputs/mitoverse_updates/",
                files_checked=checked,
                output_paths=checked,
                planned_action="Generate MitoVerse update files (no website API call)",
                message=(
                    "Local MitoVerse update executed (files written, no website update)."
                    if ok
                    else "Local MitoVerse update failed: output files missing."
                ),
            )
            updates["mitoverse_update_files"] = files
            updates["generate_mitoverse_update_plan"] = result.model_dump()
            return _json(stub_tool_observation(result)), updates

        if name == "pseudo_upload_hf":
            staging = artifacts.get("hf_staging_dir")
            if not staging:
                return _json({"error": "hf_staging_dir missing; call generate_hf_staging first."}), updates
            result = pseudo_upload_to_hf(staging)
            payload = result.model_dump()
            updates["hf_upload_plan"] = payload
            return _json(pseudo_tool_observation(result)), updates

        if name == "pseudo_push_github":
            files = artifacts.get("mitoverse_update_files") or []
            volume = (artifacts.get("merged_metadata") or {}).get("volume", "unknown")
            slug = safe_slug(volume)
            result = pseudo_push_to_github(
                files,
                branch_name=f"agent/add-{slug}",
                pr_title=f"Add MitoVerse volume: {volume}",
            )
            payload = result.model_dump()
            updates["github_push_plan"] = payload
            return _json(pseudo_tool_observation(result)), updates

        if name == "write_execution_report":
            state = {
                "run_id": run_id,
                "parsed_request": {"intent": "agent_react"},
                **artifacts,
            }
            path = write_execution_report(state)
            ok, checked = _paths_exist([path])
            result = build_stub_result(
                tool_name="write_execution_report",
                success=ok,
                mode="local",
                target=path,
                files_checked=checked,
                output_paths=checked if ok else [],
                planned_action="Write JSON execution report under outputs/execution_reports/",
                message=(
                    "Execution report written."
                    if ok
                    else "Execution report failed: file not found after write."
                ),
            )
            updates["execution_report_path"] = path
            updates["execution_report_plan"] = result.model_dump()
            return _json(stub_tool_observation(result)), updates

        if name == "fetch_mitoverse_catalog":
            _, snapshot = fetch_mitoverse_catalog_tool(force_refresh=bool(args.get("force_refresh")))
            payload = snapshot.model_dump()
            updates["mitoverse_catalog_snapshot"] = payload
            return _json({"observation": "mitoverse_catalog_snapshot", "data": payload}), updates

        if name == "lookup_mitoverse_volume":
            raw_path, label_path = _normalize_inspect_args(args)
            result = lookup_mitoverse_volume_tool(
                volume=_first(args.get("volume"), args.get("volume_id")),
                volume_id=args.get("volume_id"),
                dataset=args.get("dataset"),
                dataset_id=args.get("dataset_id"),
                raw_file_path=raw_path,
                label_file_path=label_path,
                force_refresh=bool(args.get("force_refresh")),
            )
            payload = result.model_dump()
            updates["mitoverse_lookup"] = payload
            return _json({"observation": "mitoverse_lookup", "found": result.found, "data": payload}), updates

        if name == "search_mitoverse_collection":
            raw_path, label_path = _normalize_inspect_args(args)
            shape = args.get("shape_xyz")
            result = search_mitoverse_collection_tool(
                volume=_first(args.get("volume"), args.get("volume_id")),
                volume_id=args.get("volume_id"),
                dataset=args.get("dataset"),
                dataset_id=args.get("dataset_id"),
                modality=args.get("modality"),
                organism=args.get("organism"),
                species=args.get("species"),
                organ=args.get("organ"),
                tissue=args.get("tissue"),
                tissue_region=args.get("tissue_region"),
                raw_file_path=raw_path,
                label_file_path=label_path,
                shape_xyz=shape,
                num_mito=args.get("num_mito"),
                limit=int(args.get("limit") or 15),
                force_refresh=bool(args.get("force_refresh")),
            )
            payload = result.model_dump()
            updates["mitoverse_search"] = payload
            return _json(
                {
                    "observation": "mitoverse_search",
                    "match_count": result.match_count,
                    "data": payload,
                }
            ), updates

        if name == "list_mitoverse_datasets":
            datasets = list_mitoverse_datasets_tool(force_refresh=bool(args.get("force_refresh")))
            payload = [row.model_dump() for row in datasets]
            updates["mitoverse_datasets"] = payload
            return _json({"observation": "mitoverse_datasets", "data": payload}), updates

    except Exception as exc:
        return _json({"error": str(exc)}), updates

    return _json({"error": f"Unhandled tool {name}"}), updates
