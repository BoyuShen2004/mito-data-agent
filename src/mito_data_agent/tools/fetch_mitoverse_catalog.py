"""Fetch the public MitoVerse catalog from Hugging Face (cached locally)."""

from __future__ import annotations

from mito_data_agent.schemas import MitoVerseCatalogSnapshot
from mito_data_agent.tools.mitoverse_catalog import fetch_mitoverse_catalog


def fetch_mitoverse_catalog_tool(*, force_refresh: bool = False) -> tuple[dict[str, dict], MitoVerseCatalogSnapshot]:
    return fetch_mitoverse_catalog(force_refresh=force_refresh)
