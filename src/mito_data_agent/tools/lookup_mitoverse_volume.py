"""Look up a single volume in the MitoVerse collection."""

from __future__ import annotations

from mito_data_agent.schemas import MitoVerseLookupResult
from mito_data_agent.tools.mitoverse_catalog import lookup_mitoverse_volume


def lookup_mitoverse_volume_tool(
    *,
    volume: str | None = None,
    volume_id: str | None = None,
    dataset: str | None = None,
    dataset_id: str | None = None,
    raw_file_path: str | None = None,
    label_file_path: str | None = None,
    force_refresh: bool = False,
) -> MitoVerseLookupResult:
    return lookup_mitoverse_volume(
        volume=volume,
        volume_id=volume_id,
        dataset=dataset,
        dataset_id=dataset_id,
        raw_file_path=raw_file_path,
        label_file_path=label_file_path,
        force_refresh=force_refresh,
    )
