"""Query the recorded metadata store from the command line.

    python -m mito_data_agent records                 # list all recorded volumes
    python -m mito_data_agent records --volume vol1    # show one record
    python -m mito_data_agent records --organism Human # filter by a metadata field
    python -m mito_data_agent records --json           # raw JSON output
"""

from __future__ import annotations

import argparse
import json

from mito_data_agent.tools.metadata_store import (
    get_record,
    get_store_path,
    list_records,
    query_records,
)
from mito_data_agent.utils.paths import to_relative_path

_FILTER_FIELDS = ("dataset", "modality", "organism", "organ", "tissue_region")


def _print_record(rec: dict) -> None:
    md = rec.get("metadata", {})
    print(f"● {rec.get('volume')}  (recorded {rec.get('times_recorded')}×, "
          f"updated {rec.get('updated_at')})")
    print(f"    validated: {rec.get('validation_success')}  | run: {rec.get('run_id')}")
    for key in ("dataset", "modality", "organism", "organ", "tissue_region",
                "resolution_nm", "shape_xyz", "num_mito"):
        if md.get(key) is not None:
            print(f"    {key}: {md.get(key)}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="mito_data_agent records",
        description="Query the local recorded-metadata store.",
    )
    parser.add_argument("--volume", help="Show the record for a single volume (name or slug)")
    for field in _FILTER_FIELDS:
        parser.add_argument(f"--{field}", help=f"Filter by {field} (substring match)")
    parser.add_argument("--json", action="store_true", help="Print raw JSON")
    args = parser.parse_args(argv)

    store_path = to_relative_path(get_store_path())

    if args.volume:
        rec = get_record(args.volume)
        if not rec:
            print(f"No record found for volume: {args.volume}  (store: {store_path})")
            return
        print(json.dumps(rec, indent=2, default=str) if args.json else "")
        if not args.json:
            _print_record(rec)
        return

    filters = {f: getattr(args, f) for f in _FILTER_FIELDS if getattr(args, f)}
    records = query_records(**filters) if filters else list_records()

    if args.json:
        print(json.dumps(records, indent=2, default=str))
        return

    if not records:
        print(f"No recorded metadata yet.  (store: {store_path})")
        return

    print(f"Recorded volumes: {len(records)}  (store: {store_path})\n")
    for rec in records:
        _print_record(rec)
        print()
