"""Search the MitoVerse collection with partial metadata hints."""

from __future__ import annotations

from mito_data_agent.schemas import MitoVerseSearchResult
from mito_data_agent.tools.mitoverse_catalog import search_mitoverse_collection


def search_mitoverse_collection_tool(
    *,
    volume: str | None = None,
    volume_id: str | None = None,
    dataset: str | None = None,
    dataset_id: str | None = None,
    modality: str | None = None,
    organism: str | None = None,
    species: str | None = None,
    organ: str | None = None,
    tissue: str | None = None,
    tissue_region: str | None = None,
    raw_file_path: str | None = None,
    label_file_path: str | None = None,
    shape_xyz: list[int] | None = None,
    num_mito: int | None = None,
    limit: int = 15,
    force_refresh: bool = False,
) -> MitoVerseSearchResult:
    return search_mitoverse_collection(
        volume=volume,
        volume_id=volume_id,
        dataset=dataset,
        dataset_id=dataset_id,
        modality=modality,
        organism=organism,
        species=species,
        organ=organ,
        tissue=tissue,
        tissue_region=tissue_region,
        raw_file_path=raw_file_path,
        label_file_path=label_file_path,
        shape_xyz=shape_xyz,
        num_mito=num_mito,
        limit=limit,
        force_refresh=force_refresh,
    )
