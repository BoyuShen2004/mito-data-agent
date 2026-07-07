"""Run the supervisor-based multi-agent workflow from the command line.

    python -m mito_data_agent run --prompt "Prepare vol1 for upload..." --trace
"""

from __future__ import annotations

import argparse
import os

from mito_data_agent import config
from mito_data_agent.agents.runner import run_multi_agent
from mito_data_agent.cli.common import run_clear
from mito_data_agent.tools.reporting import render_cli_summary
from mito_data_agent.utils.prompts import load_prompt_file


def _read_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return args.prompt
    if args.prompt_file:
        return load_prompt_file(args.prompt_file)
    raise SystemExit("Provide --prompt or --prompt-file.")


def _apply_llm_cli_flags(args: argparse.Namespace) -> None:
    use_codex = args.llm_backend == "codex_cli" or os.getenv("USE_CODEX_CLI", "").lower() == "true"
    config.apply_runtime_config(
        llm_backend=args.llm_backend,
        llm_model=args.model,
        use_codex_cli=use_codex if args.llm_backend == "codex_cli" else None,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="mito_data_agent run",
        description="Supervisor-based multi-agent LangGraph workflow",
    )
    parser.add_argument("--prompt", type=str, help="User prompt text")
    parser.add_argument("--prompt-file", type=str, help="Path to prompt file")
    parser.add_argument("--trace", action="store_true", help="Print the supervisor/agent trace")
    parser.add_argument(
        "--clear-outputs",
        action="store_true",
        help="Delete all outputs/ artifacts, then exit (or continue if a prompt is given)",
    )
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation for --clear-outputs")
    parser.add_argument(
        "--llm-backend",
        choices=["openai", "codex_cli"],
        default=config.LLM_BACKEND,
        help="LLM backend for prompt parsing (default: openai)",
    )
    parser.add_argument("--model", default=config.LLM_MODEL, help="LLM model name for OpenAI backend")
    args = parser.parse_args(argv)

    _apply_llm_cli_flags(args)

    if args.clear_outputs:
        stats = run_clear(args.yes)
        if stats.get("cancelled"):
            return
        if not args.prompt and not args.prompt_file:
            return

    user_prompt = _read_prompt(args)
    result = run_multi_agent(user_prompt, trace=args.trace, print_trace_output=True)
    print(render_cli_summary(result["summary"]))
