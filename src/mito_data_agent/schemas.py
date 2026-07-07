"""Pydantic schemas for parsed requests, file inspection, and validation."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class ParsedDataset(BaseModel):
    """One volume/dataset's metadata parsed from the prompt.

    Used when a single prompt describes *several* datasets — each becomes an entry
    in ``ParsedUserRequest.datasets`` so the agent can record them all.
    """

    volume: Optional[str] = None
    dataset: Optional[str] = None
    modality: Optional[str] = None
    organism: Optional[str] = None
    organ: Optional[str] = None
    tissue_region: Optional[str] = None
    resolution_nm: Optional[tuple[float, float, float]] = None
    shape_xyz: Optional[tuple[int, int, int]] = None
    num_mito: Optional[int] = None
    raw_file_path: Optional[str] = None
    label_file_path: Optional[str] = None
    metadata_file_path: Optional[str] = None
    provenance: Optional[str] = None
    source_url: Optional[str] = None
    annotator: Optional[str] = None
    notes: list[str] = Field(default_factory=list)

    @field_validator("resolution_nm", "shape_xyz", mode="before")
    @classmethod
    def _list_to_tuple(cls, value):
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="before")
    @classmethod
    def _normalize_null_strings(cls, data):
        if not isinstance(data, dict):
            return data
        for key, val in list(data.items()):
            if val in ("null", "None", ""):
                data[key] = None
        return data


class ParsedUserRequest(BaseModel):
    """Structured output from prompt parsing."""

    intent: str = Field(
        description="Registered task intent (see mito_data_agent.tasks registry)",
    )
    volume: Optional[str] = None
    dataset: Optional[str] = None
    modality: Optional[str] = None
    organism: Optional[str] = None
    organ: Optional[str] = None
    tissue_region: Optional[str] = None
    resolution_nm: Optional[tuple[float, float, float]] = None
    shape_xyz: Optional[tuple[int, int, int]] = None
    num_mito: Optional[int] = None
    raw_file_path: Optional[str] = None
    label_file_path: Optional[str] = None
    metadata_file_path: Optional[str] = None
    provenance: Optional[str] = None
    source_url: Optional[str] = None
    annotator: Optional[str] = None
    # When the prompt describes multiple datasets, each is listed here (the first
    # is also mirrored into the top-level fields above for backward compatibility).
    datasets: list[ParsedDataset] = Field(default_factory=list)
    requested_actions: list[
        Literal[
            "prepare_hf_upload",
            "update_mitoverse_metadata",
            "check_files",
            "open_github_pr",
        ]
    ] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("resolution_nm", "shape_xyz", mode="before")
    @classmethod
    def _list_to_tuple(cls, value):
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="before")
    @classmethod
    def _normalize_null_strings(cls, data):
        if not isinstance(data, dict):
            return data
        for key, val in list(data.items()):
            if val in ("null", "None", ""):
                data[key] = None
        return data


class FileInspectionResult(BaseModel):
    """Low-level file existence and shape checks."""

    raw_file_exists: bool
    label_file_exists: bool
    raw_shape_xyz: Optional[tuple[int, int, int]] = None
    label_shape_xyz: Optional[tuple[int, int, int]] = None
    shape_match: Optional[bool] = None
    label_dtype: Optional[str] = None
    file_format: Optional[str] = None
    num_mito: Optional[int] = None
    unique_label_count: Optional[int] = None
    warnings: list[str] = Field(default_factory=list)


class VolumeObservation(BaseModel):
    """File-derived observations for Resolution, Shape, and # Mito."""

    raw_file_path: Optional[str] = None
    label_file_path: Optional[str] = None
    metadata_file_path: Optional[str] = None

    resolution_nm: Optional[tuple[float, float, float]] = None
    shape_xyz: Optional[tuple[int, int, int]] = None
    num_mito: Optional[int] = None

    raw_shape_xyz: Optional[tuple[int, int, int]] = None
    label_shape_xyz: Optional[tuple[int, int, int]] = None

    shape_source: Optional[
        Literal["raw_file", "label_file", "prompt", "metadata_file", "unknown"]
    ] = None
    resolution_source: Optional[
        Literal["metadata_file", "prompt", "unknown"]
    ] = None
    num_mito_source: Optional[Literal["label_file", "prompt", "unknown"]] = None

    observations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MitoVerseVolumeRow(BaseModel):
    """A complete MitoVerse table row."""

    volume: str
    dataset: str
    modality: str
    organism: str
    organ: str
    tissue_region: str
    resolution_nm: tuple[float, float, float]
    shape_xyz: tuple[int, int, int]
    num_mito: int
    provenance: Optional[str] = None
    source_url: Optional[str] = None
    annotator: Optional[str] = None
    raw_file_path: Optional[str] = None
    label_file_path: Optional[str] = None
    metadata_file_path: Optional[str] = None
    notes: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    """Result of required-metadata validation."""

    success: bool
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    message: str


class LocalVolumeEntry(BaseModel):
    """One discovered annotated volume on disk."""

    volume_id: str
    raw_file_path: Optional[str] = None
    label_file_path: Optional[str] = None
    raw_size_bytes: Optional[int] = None
    label_size_bytes: Optional[int] = None
    raw_shape_xyz: Optional[tuple[int, int, int]] = None
    label_shape_xyz: Optional[tuple[int, int, int]] = None
    num_mito: Optional[int] = None
    warnings: list[str] = Field(default_factory=list)


class LocalDataInventory(BaseModel):
    """Scan result for the local annotated-volume data directory."""

    data_dir: str
    volumes: list[LocalVolumeEntry] = Field(default_factory=list)
    unpaired_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PseudoToolResult(BaseModel):
    """Result from stub tools: local artifact writes or pseudo external ops."""

    tool_name: str
    mode: Literal["pseudo", "local"] = "pseudo"
    executed: bool = True
    signal: Literal["ok", "failed"]
    success: bool
    real_write_performed: bool
    target: str
    files_checked: list[str] = Field(default_factory=list)
    output_paths: list[str] = Field(default_factory=list)
    planned_action: str
    message: str


class MitoVerseCatalogSnapshot(BaseModel):
    """Metadata about the cached public MitoVerse catalog."""

    source_url: str
    explorer_url: str
    fetched_at: Optional[str] = None
    volume_count: int = 0


class MitoVerseCatalogMatch(BaseModel):
    """One catalog row match."""

    volume_id: str
    dataset_id: Optional[str] = None
    in_collection: bool = True
    match_score: float = 0.0
    matched_by: str = ""
    entry: dict[str, Any] = Field(default_factory=dict)


class MitoVerseLookupResult(BaseModel):
    """Result of checking whether a volume exists in MitoVerse."""

    query: dict[str, Any] = Field(default_factory=dict)
    found: bool
    best_match: Optional[MitoVerseCatalogMatch] = None
    candidates: list[MitoVerseCatalogMatch] = Field(default_factory=list)
    catalog: MitoVerseCatalogSnapshot
    message: str


class MitoVerseSearchResult(BaseModel):
    """Multi-hint search over the MitoVerse catalog."""

    query: dict[str, Any] = Field(default_factory=dict)
    match_count: int
    matches: list[MitoVerseCatalogMatch] = Field(default_factory=list)
    catalog: MitoVerseCatalogSnapshot
    message: str


class MitoVerseDatasetSummary(BaseModel):
    """One dataset_id group in the catalog."""

    dataset_id: str
    volume_count: int
    example_volume_ids: list[str] = Field(default_factory=list)
