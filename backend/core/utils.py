"""Shared, dependency-light utilities.

Includes the volume-inspection helpers salvaged from the previous codebase
(fast TIFF shape reading from headers, and label mito-count) plus a slug helper.
These are deterministic and safe to call from views, services, management
commands, and future agent tools.
"""

from __future__ import annotations

import re
from pathlib import Path


def safe_slug(text: str) -> str:
    """Make a name safe for folders, URLs, and file stems."""
    slug = (text or "").strip().lower()
    slug = re.sub(r"[^\w\-]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "unnamed"


def array_shape_to_xyz(shape: tuple) -> tuple[int, int, int]:
    """Convert an array shape to ``(x, y, z)`` convention.

    - ``(z, y, x)`` -> ``(x, y, z)``
    - ``(y, x)`` -> ``(x, y, 1)``
    - more dims: use the last three as ``(z, y, x)``
    """
    if len(shape) == 2:
        y, x = shape
        return (int(x), int(y), 1)
    if len(shape) == 3:
        z, y, x = shape
        return (int(x), int(y), int(z))
    if len(shape) > 3:
        z, y, x = shape[-3], shape[-2], shape[-1]
        return (int(x), int(y), int(z))
    raise ValueError(f"Unsupported array shape: {shape}")


def read_tiff_shape_fast(path: str | Path) -> tuple[int, int, int]:
    """Read a TIFF's ``(x, y, z)`` shape from headers without loading the array."""
    import tifffile  # imported lazily so non-TIFF workflows don't need it

    with tifffile.TiffFile(str(path)) as tif:
        if tif.series:
            shape = tif.series[0].shape
        elif len(tif.pages) > 1:
            shape = (len(tif.pages),) + tif.pages[0].shape
        else:
            shape = tif.pages[0].shape
    return array_shape_to_xyz(shape)


def inspect_volume_shape(path: str | Path) -> tuple[int, int, int] | None:
    """Best-effort ``(x, y, z)`` shape for a supported volume file.

    Returns ``None`` if the shape cannot be determined (unsupported format,
    missing file, or a read error). Only TIFF is inspected without extra deps;
    other formats can be added here later.
    """
    p = Path(path)
    if not p.exists():
        return None
    suffix = p.suffix.lower()
    try:
        if suffix in {".tif", ".tiff"}:
            return read_tiff_shape_fast(p)
    except Exception:
        return None
    return None


def count_label_instances(path: str | Path) -> int | None:
    """Count unique non-zero labels in a TIFF label volume, or ``None``."""
    p = Path(path)
    if not p.exists() or p.suffix.lower() not in {".tif", ".tiff"}:
        return None
    try:
        import numpy as np
        import tifffile

        arr = tifffile.imread(str(p))
        unique = np.unique(arr)
        return int(np.sum(unique != 0))
    except Exception:
        return None
