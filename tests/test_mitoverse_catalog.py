"""Tests for MitoVerse catalog lookup/search tools."""

from __future__ import annotations

import json

import pytest

from mito_data_agent.schemas import MitoVerseCatalogSnapshot
from mito_data_agent.tools.mitoverse_catalog import (
    list_mitoverse_datasets,
    lookup_mitoverse_volume,
    search_mitoverse_collection,
)


@pytest.fixture()
def sample_catalog(tmp_path, monkeypatch):
    catalog = {
        "openorganelle_jrc_mus-liver_recon-1_test0": {
            "dataset_id": "openorganelle",
            "modality": "FIB-SEM",
            "species": "Mouse",
            "organ": "Liver",
            "tissue": "liver",
            "shape_zyx": [256, 1024, 1024],
            "voxel_nm": [8.0, 8.0, 8.0],
            "n_instances": 2,
            "zarr": "data/openorganelle/jrc_mus-liver_recon-1_test0.zarr",
        },
        "guay21_vol1": {
            "dataset_id": "guay21",
            "modality": "SBF-SEM",
            "species": "Human",
            "organ": "Blood",
            "tissue": "platelet",
            "shape_zyx": [100, 500, 500],
            "voxel_nm": [10.0, 10.0, 50.0],
            "n_instances": 12,
            "zarr": "data/guay21/vol1.zarr",
        },
    }
    cache = tmp_path / "mitoverse_catalog.json"
    cache.write_text(
        json.dumps(
            {
                "meta": {
                    "source_url": "test://catalog",
                    "fetched_at": "2026-07-04T00:00:00Z",
                    "volume_count": len(catalog),
                },
                "volumes": catalog,
            }
        ),
        encoding="utf-8",
    )

    def _fake_fetch(*, force_refresh: bool = False):
        raw = json.loads(cache.read_text(encoding="utf-8"))
        snapshot = MitoVerseCatalogSnapshot(
            source_url="test://catalog",
            explorer_url="https://pytorchconnectomics.github.io/mitoverse/",
            fetched_at=raw["meta"]["fetched_at"],
            volume_count=len(raw["volumes"]),
        )
        return raw["volumes"], snapshot

    monkeypatch.setattr(
        "mito_data_agent.tools.mitoverse_catalog.fetch_mitoverse_catalog",
        _fake_fetch,
    )
    return catalog


def test_lookup_volume_by_local_name(sample_catalog):
    result = lookup_mitoverse_volume(volume="jrc_mus-liver_recon-1_test0")
    assert result.found is True
    assert result.best_match is not None
    assert result.best_match.volume_id == "openorganelle_jrc_mus-liver_recon-1_test0"


def test_lookup_volume_by_file_path(sample_catalog):
    result = lookup_mitoverse_volume(
        raw_file_path="/data/jrc_mus-liver_recon-1_test0_0000.tiff",
        label_file_path="/data/jrc_mus-liver_recon-1_test0.tiff",
    )
    assert result.found is True
    assert "openorganelle_jrc_mus-liver_recon-1_test0" in result.message


def test_lookup_missing_volume(sample_catalog):
    result = lookup_mitoverse_volume(volume="vol1")
    assert result.found is False
    assert result.candidates
    assert result.candidates[0].volume_id == "guay21_vol1"


def test_search_with_partial_metadata(sample_catalog):
    result = search_mitoverse_collection(
        dataset_id="guay21",
        modality="SBF-SEM",
        species="Human",
    )
    assert result.match_count >= 1
    assert result.matches[0].volume_id == "guay21_vol1"


def test_list_datasets(sample_catalog):
    datasets = list_mitoverse_datasets()
    ids = {row.dataset_id for row in datasets}
    assert ids == {"openorganelle", "guay21"}


def test_catalog_agent_lookup(sample_catalog):
    """The catalog agent wraps the lookup tool and writes mitoverse_lookup to state."""
    from mito_data_agent.agents.catalog_agent import catalog_agent

    state = {
        "run_id": "run_test",
        "agent_trace": [],
        "step": 0,
        "parsed_request": {"volume": "jrc_mus-liver_recon-1_test0"},
    }
    out = catalog_agent(state)
    assert out["mitoverse_lookup"]["found"] is True
