"""Unified CLI entry point: python -m mito_data_agent <command>."""

from __future__ import annotations

import sys

from mito_data_agent.cli import clear, records, run

COMMANDS = {
    "run": run.main,
    "records": records.main,
    "clear": clear.main,
}

USAGE = """\
Mito Data Agent — supervisor-based multi-agent workflow for MitoVerse metadata

Usage:
  python -m mito_data_agent run --prompt-file prompts/examples/upload_prompt.md --trace
  python -m mito_data_agent records --volume vol1
  python -m mito_data_agent clear -y

Commands:
  run      Run the supervisor-based multi-agent workflow (CLI, --trace)
  records  Query the recorded-metadata store
  clear    Delete all outputs/ and run history
"""


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(USAGE)
        raise SystemExit(0 if len(sys.argv) >= 2 else 1)

    command = sys.argv[1]
    if command not in COMMANDS:
        print(f"Unknown command: {command}\n")
        print(USAGE)
        raise SystemExit(1)

    # Pass remaining args to the subcommand parser.
    COMMANDS[command](sys.argv[2:])


if __name__ == "__main__":
    main()
