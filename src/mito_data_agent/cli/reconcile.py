"""Reconcile stored record + sidecar names with the on-disk data files.

    python -m mito_data_agent reconcile            # apply the renames
    python -m mito_data_agent reconcile --dry-run  # preview only

Renames any recorded volume whose name doesn't match its actual data file (e.g.
``MitoHardLiver`` -> ``jrc_mus-liver_recon-1_test0``) so each ``<name>.metadata.json``
matches the TIFFs beside it. The ``dataset`` name and history are preserved.
"""

from __future__ import annotations

import argparse

from mito_data_agent.tools.metadata_store import get_store_path, reconcile_record_names
from mito_data_agent.utils.paths import to_relative_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="mito_data_agent reconcile",
        description="Rename stored records/sidecars to match on-disk data files.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args(argv)

    changes = reconcile_record_names(dry_run=args.dry_run)
    store = to_relative_path(get_store_path())

    if not changes:
        print(f"Everything is consistent — no records to rename.  (store: {store})")
        return

    verb = "Would rename" if args.dry_run else "Renamed"
    print(f"{verb} {len(changes)} record(s) to match on-disk data:")
    for c in changes:
        line = f"  {c['old']}  →  {c['new']}"
        if c.get("removed_sidecar"):
            line += f"   (removed stale {c['removed_sidecar']})"
        print(line)
    if args.dry_run:
        print("\nRe-run without --dry-run to apply.")
