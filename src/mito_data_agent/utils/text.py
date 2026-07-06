"""Text parsing helpers for metadata fields."""

from __future__ import annotations

import re
from typing import Optional


def normalize_key(text: str) -> str:
    """Normalize a metadata key for matching."""
    return re.sub(r"[\s_/]+", "_", text.strip().lower())


def parse_resolution_string(text: str) -> Optional[tuple[float, float, float]]:
    """Parse resolution strings like 8x8x40 nm, 8,8,40, or [8, 8, 40]."""
    if not text:
        return None

    cleaned = text.strip()
    cleaned = re.sub(r"\s*nm\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("×", "x").replace("X", "x")

    # Bracket or comma-separated
    bracket_match = re.match(r"^\[?\s*([\d.]+)\s*[,x]\s*([\d.]+)\s*[,x]\s*([\d.]+)\s*\]?$", cleaned)
    if bracket_match:
        return (
            float(bracket_match.group(1)),
            float(bracket_match.group(2)),
            float(bracket_match.group(3)),
        )

    # x-separated
    parts = re.split(r"[x,]", cleaned)
    if len(parts) == 3:
        try:
            return (float(parts[0]), float(parts[1]), float(parts[2]))
        except ValueError:
            return None

    return None


def parse_shape_string(text: str) -> Optional[tuple[int, int, int]]:
    """Parse shape strings like 250x250x164, 250,250,164, or [250, 250, 164]."""
    if not text:
        return None

    cleaned = text.strip().replace("×", "x").replace("X", "x")

    bracket_match = re.match(r"^\[?\s*(\d+)\s*[,x]\s*(\d+)\s*[,x]\s*(\d+)\s*\]?$", cleaned)
    if bracket_match:
        return (
            int(bracket_match.group(1)),
            int(bracket_match.group(2)),
            int(bracket_match.group(3)),
        )

    parts = re.split(r"[x,]", cleaned)
    if len(parts) == 3:
        try:
            return (int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return None

    return None


def parse_int_from_text(text: str) -> Optional[int]:
    """Extract the first integer from text."""
    if not text:
        return None
    match = re.search(r"-?\d+", text.strip())
    if match:
        return int(match.group())
    return None
