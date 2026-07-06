"""Run the LangGraph agent from the command line."""

from __future__ import annotations

import argparse
import os

from mito_data_agent import config
from mito_data_agent.cli.common import run_clear
from mito_data_agent.runner import run_agent
from mito_data_agent.utils.prompts import load_prompt_file


def _read_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return args.prompt
    if args.prompt_file:
        return load_prompt_file(args.prompt_file)
    raise SystemExit("Provide --prompt or --prompt-file.")


def _apply_llm_cli_flags(args: argparse.Namespace) -> None:
    use_codex = args.llm_backend == "codex_cli" or os.getenv("USE_CODEX_CLI", "").lower() == "true"
    if args.llm_backend == "codex_cli":
        use_codex = True
    config.apply_runtime_config(
        llm_backend=args.llm_backend,
        llm_model=args.model,
        use_codex_cli=use_codex if args.llm_backend == "codex_cli" else None,
        allow_rule_based_fallback=args.allow_rule_based_fallback,
    )


def _print_summary(summary: dict) -> None:
    print("\n=== Mito Data Agent Summary ===")
    print(f"Intent:              {summary.get('intent', 'unknown')}")
    print(f"Run ID:              {summary.get('run_id')}")
    print(f"Execution report:    {summary.get('execution_report_path')}")
    print(f"HF staging dir:      {summary.get('hf_staging_dir')}")
    print(f"MitoVerse updates:   {summary.get('mitoverse_update_files')}")

    if summary.get("resolution_nm"):
        print(
            f"Resolution (nm):     {summary['resolution_nm']} "
            f"(source: {summary.get('resolution_source', 'prompt')})"
        )
    if summary.get("shape_xyz"):
        print(
            f"Shape (x,y,z):       {summary['shape_xyz']} "
            f"(source: {summary.get('shape_source', 'prompt')})"
        )
    if summary.get("num_mito") is not None:
        print(
            f"# Mito:              {summary['num_mito']} "
            f"(source: {summary.get('num_mito_source', 'prompt')})"
        )

    if summary.get("hf_upload_success") is not None:
        print(
            f"Pseudo HF upload:    success={summary['hf_upload_success']}, "
            f"real_write={summary['hf_real_write']}"
        )
    if summary.get("github_push_success") is not None:
        print(
            f"Pseudo GitHub push:  success={summary['github_push_success']}, "
            f"real_write={summary['github_real_write']}"
        )

    errors = summary.get("errors", [])
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")

    warnings = summary.get("warnings", [])
    if warnings:
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings[:10]:
            print(f"  - {w}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Mito Data Agent — LLM-powered LangGraph MVP")
    parser.add_argument("--prompt", type=str, help="User prompt text")
    parser.add_argument("--prompt-file", type=str, help="Path to prompt file")
    parser.add_argument(
        "--clear-outputs",
        action="store_true",
        help="Delete all outputs/ artifacts and run history, then exit",
    )
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation for --clear-outputs")
    parser.add_argument("--trace", action="store_true", help="Print LangGraph node-by-node trace")
    parser.add_argument(
        "--llm-backend",
        choices=["openai", "codex_cli"],
        default=config.LLM_BACKEND,
        help="LLM backend for prompt parsing (default: openai)",
    )
    parser.add_argument(
        "--model",
        default=config.LLM_MODEL,
        help="LLM model name for OpenAI backend",
    )
    parser.add_argument(
        "--allow-rule-based-fallback",
        action="store_true",
        help="Allow rule-based parser if LLM fails (not recommended)",
    )
    args = parser.parse_args(argv)

    _apply_llm_cli_flags(args)

    if args.clear_outputs:
        stats = run_clear(args.yes)
        if stats.get("cancelled"):
            return
        if not args.prompt and not args.prompt_file:
            return

    user_prompt = _read_prompt(args)
    result = run_agent(user_prompt, trace=args.trace, print_trace=True)
    _print_summary(result["summary"])
