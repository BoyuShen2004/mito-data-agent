"""Shared CLI helpers."""

from __future__ import annotations

from mito_data_agent.utils.paths import get_outputs_dir, to_relative_path


def confirm_clear(skip: bool, *, verbose: bool = False) -> bool:
    """Ask the user before deleting outputs/."""
    if skip:
        return True
    print(f"This will delete everything under: {to_relative_path(get_outputs_dir())}")
    if verbose:
        print("  - outputs/hf_staging/")
        print("  - outputs/mitoverse_updates/")
        print("  - outputs/execution_reports/")
        print("  - outputs/logs/")
    answer = input("\nContinue? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def run_clear(skip_confirm: bool, *, verbose: bool = False) -> dict[str, int]:
    """Confirm (optional) and clear all outputs."""
    from mito_data_agent.utils.paths import clear_outputs, get_outputs_dir, to_relative_path

    if not confirm_clear(skip_confirm, verbose=verbose):
        print("Cancelled.")
        return {"removed_files": 0, "removed_dirs": 0, "cancelled": True}

    stats = clear_outputs()
    print(
        f"Cleared outputs: {stats['removed_files']} file(s), "
        f"{stats['removed_dirs']} director(ies) removed."
    )
    if verbose:
        print(f"Fresh output dirs ready under {to_relative_path(get_outputs_dir())}")
    return {**stats, "cancelled": False}
