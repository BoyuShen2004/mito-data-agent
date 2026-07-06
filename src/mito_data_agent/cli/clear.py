"""Clear agent outputs and run history."""

from __future__ import annotations

import argparse

from mito_data_agent.cli.common import run_clear


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Clear all Mito Data Agent outputs and run history"
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )
    args = parser.parse_args(argv)
    run_clear(args.yes, verbose=True)
