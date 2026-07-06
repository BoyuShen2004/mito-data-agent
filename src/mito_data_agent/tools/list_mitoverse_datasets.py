"""List dataset groups in the MitoVerse catalog."""

from __future__ import annotations

from mito_data_agent.schemas import MitoVerseDatasetSummary
from mito_data_agent.tools.mitoverse_catalog import list_mitoverse_datasets


def list_mitoverse_datasets_tool(*, force_refresh: bool = False) -> list[MitoVerseDatasetSummary]:
    return list_mitoverse_datasets(force_refresh=force_refresh)
