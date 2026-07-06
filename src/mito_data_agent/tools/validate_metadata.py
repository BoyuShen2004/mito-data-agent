"""Validate merged metadata against required MitoVerse columns."""

from __future__ import annotations

from mito_data_agent.config import REQUIRED_MITOVERSE_COLUMNS
from mito_data_agent.schemas import ValidationResult


def _is_valid_resolution(value) -> bool:
    if value is None:
        return False
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return False
    try:
        return all(float(v) > 0 for v in value)
    except (TypeError, ValueError):
        return False


def _is_valid_shape(value) -> bool:
    if value is None:
        return False
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return False
    try:
        return all(int(v) > 0 for v in value)
    except (TypeError, ValueError):
        return False


def _is_valid_num_mito(value) -> bool:
    if value is None:
        return False
    try:
        return int(value) >= 0
    except (TypeError, ValueError):
        return False


def validate_required_metadata(merged_metadata: dict) -> ValidationResult:
    """Check that all required MitoVerse columns are present and valid."""
    missing: list[str] = []
    warnings: list[str] = list(merged_metadata.get("warnings", []))

    for col in REQUIRED_MITOVERSE_COLUMNS:
        value = merged_metadata.get(col)
        if value is None or value == "":
            missing.append(col)

    if not _is_valid_resolution(merged_metadata.get("resolution_nm")):
        if "resolution_nm" not in missing:
            missing.append("resolution_nm")
        warnings.append("resolution_nm must be a length-3 numeric tuple.")

    if not _is_valid_shape(merged_metadata.get("shape_xyz")):
        if "shape_xyz" not in missing:
            missing.append("shape_xyz")
        warnings.append("shape_xyz must be a length-3 tuple of positive integers.")

    num_mito = merged_metadata.get("num_mito")
    if num_mito is not None:
        try:
            if int(num_mito) < 0:
                if "num_mito" not in missing:
                    missing.append("num_mito")
                warnings.append("num_mito must be >= 0.")
        except (TypeError, ValueError):
            if "num_mito" not in missing:
                missing.append("num_mito")
    elif "num_mito" not in missing:
        missing.append("num_mito")

    success = len(missing) == 0
    if success:
        message = "All required MitoVerse columns are present and valid."
    else:
        message = f"Missing or invalid fields: {', '.join(missing)}"

    return ValidationResult(
        success=success,
        missing_fields=missing,
        warnings=warnings,
        message=message,
    )
