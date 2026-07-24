"""Shared, dependency-light volume-inspection utilities.

Fast TIFF shape/voxel-size reading from headers, without loading pixel data.
These are deterministic and safe to call from views, services, management
commands, and future agent tools.
"""

from __future__ import annotations

from pathlib import Path


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


def _tiff_voxel_size(path: str | Path) -> tuple[float, float, float] | None:
    """Read a TIFF's ``(z, y, x)`` voxel size from its headers, if recorded.

    ImageJ hyperstacks store the z-spacing (and physical unit) in the ImageJ
    metadata block, while the in-plane x/y spacing comes from the standard
    ``XResolution``/``YResolution`` tags (pixels per unit → spacing = 1/res).
    Returns ``None`` when nothing usable is found; individual axes may be
    ``None`` when only some are recorded.
    """
    import tifffile

    with tifffile.TiffFile(str(path)) as tif:
        page = tif.pages[0]
        ij = tif.imagej_metadata or {}

        def _spacing_from_tag(tag_name: str) -> float | None:
            tag = page.tags.get(tag_name)
            if not tag or not tag.value:
                return None
            value = tag.value
            # Resolution tags are RATIONAL (numerator, denominator) = px/unit.
            if isinstance(value, tuple) and len(value) == 2 and value[0]:
                num, den = value
                return den / num
            if value:
                return 1.0 / float(value)
            return None

        z = ij.get("spacing")
        z = float(z) if isinstance(z, (int, float)) and z else None
        y = _spacing_from_tag("YResolution")
        x = _spacing_from_tag("XResolution")

    if z is None and y is None and x is None:
        return None
    return (z, y, x)


def inspect_volume_voxel_size(
    path: str | Path,
) -> tuple[float, float, float] | None:
    """Best-effort ``(z, y, x)`` voxel size for a supported volume file.

    Reads the physical spacing recorded in the file's headers (TIFF resolution
    tags / ImageJ metadata; NIfTI pixdim when nibabel is available). Returns
    ``None`` when it cannot be determined, so callers can leave the field blank.
    """
    p = Path(path)
    if not p.exists():
        return None
    name = p.name.lower()
    try:
        if name.endswith((".tif", ".tiff")):
            return _tiff_voxel_size(p)
        if name.endswith((".nii", ".nii.gz")):
            import nibabel as nib

            zooms = nib.load(str(p)).header.get_zooms()
            if len(zooms) >= 3:
                x, y, z = float(zooms[0]), float(zooms[1]), float(zooms[2])
                return (z, y, x)
    except Exception:
        return None
    return None
