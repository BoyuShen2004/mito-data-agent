"""Unified CLI entry point: python -m mito_data_agent <command>."""

from __future__ import annotations

import sys

from mito_data_agent.cli import agent, clear, web

COMMANDS = {
    "agent": agent.main,
    "web": web.main,
    "clear": clear.main,
}

USAGE = """\
Mito Data Agent — LangGraph agent for MitoVerse upload preparation

Usage:
  python -m mito_data_agent agent --prompt-file examples/upload_prompt.md
  python -m mito_data_agent web
  python -m mito_data_agent clear -y

Commands:
  agent   Run the LangGraph agent (CLI)
  web     Start the chat web UI
  clear   Delete all outputs/ and run history
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
