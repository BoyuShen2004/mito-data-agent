"""On-demand slice IO with bounded LRU caches (Cellable memory patterns).

The web process must never load a whole EM volume into RAM. This module mirrors
Cellable's ``sliceCache`` / ``MAX_SLICE_PIXMAP_CACHE`` approach on the server:

* volumes are opened as **memory-maps** (``tifffile.memmap`` / ``np.load(mmap)``),
  so only the touched slices are paged in;
* decoded 2D slices are kept in a **bounded LRU** keyed by ``(path, mtime, axis,
  index)`` — revisiting a slice is instant, distant slices are evicted;
* open memmaps are themselves kept in a small LRU so switching volumes doesn't
  leak file handles.

Only the current slice (plus whatever neighbours the client prefetches) is ever
turned into a PNG and streamed, keeping both server RAM and client transfer
small. PNG encoding is a tiny built-in (no Pillow dependency).
"""

from __future__ import annotations

import io
import struct
import zlib
from collections import OrderedDict
from pathlib import Path

import numpy as np
from django.conf import settings
from PIL import Image

# Bounded like Cellable's MAX_SLICE_PIXMAP_CACHE (256) / a few open volumes.
MAX_SLICE_CACHE = 256
MAX_OPEN_VOLUMES = 8
# Encoded-response cache is smaller per entry than the raw-array cache above,
# so it can afford to hold more: on a CPU-only HPC node, the expensive part of
# serving a slice is compression, not decoding, and this makes a revisited
# slice (very common when scrubbing back and forth) cost nothing to re-encode.
MAX_ENCODED_CACHE = 512
# Writable label memmaps stay open across requests (paint strokes reuse the
# same handle) — kept intentionally small since these are actively edited.
MAX_OPEN_LABEL_VOLUMES = 4

AXES = {"z": 0, "y": 1, "x": 2}

_slice_cache: "OrderedDict[tuple, np.ndarray]" = OrderedDict()
_volume_cache: "OrderedDict[tuple, np.ndarray]" = OrderedDict()
_range_cache: "OrderedDict[tuple, tuple[float, float]]" = OrderedDict()
_encoded_cache: "OrderedDict[tuple, bytes]" = OrderedDict()
_label_volume_cache: "OrderedDict[tuple, np.memmap]" = OrderedDict()
_label_max_cache: dict[str, int] = {}


class SliceIOError(Exception):
    pass


# --- path resolution --------------------------------------------------------

def resolve_path(location: str) -> Path:
    """Resolve a stored image/label location against ``MITO_DATA_ROOT``."""
    p = Path(location)
    if not p.is_absolute():
        p = Path(settings.MITO_DATA_ROOT) / location
    return p


# --- bounded LRU helpers ----------------------------------------------------

def _lru_get(cache: OrderedDict, key):
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    return None


def _lru_put(cache: OrderedDict, key, value, limit: int):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > limit:
        cache.popitem(last=False)


def clear_caches() -> None:
    _slice_cache.clear()
    _volume_cache.clear()
    _range_cache.clear()
    _encoded_cache.clear()
    _label_volume_cache.clear()
    _label_max_cache.clear()


def invalidate_read_caches() -> None:
    """Drop only the *read-side* caches (decoded slices, encoded PNG/JPEG
    bytes) so viewers see a just-written edit. Deliberately leaves open
    volume/label memmaps alone — those aren't stale (a memmap always reflects
    the file's current bytes) and re-opening them on every stroke would
    reintroduce exactly the cost this module exists to avoid.
    """
    _slice_cache.clear()
    _encoded_cache.clear()


def cache_stats() -> dict:
    return {
        "slices": len(_slice_cache),
        "volumes": len(_volume_cache),
        "encoded": len(_encoded_cache),
        "label_volumes": len(_label_volume_cache),
    }


# --- volume + slice access --------------------------------------------------

def _open_volume(path: Path) -> np.ndarray:
    """Return a (Z, Y, X) memory-mapped/array view of the volume, LRU-cached."""
    if not path.exists():
        raise SliceIOError(f"File not found: {path}")
    key = (str(path), path.stat().st_mtime)
    cached = _lru_get(_volume_cache, key)
    if cached is not None:
        return cached

    suffix = path.suffix.lower()
    arr: np.ndarray
    try:
        if suffix in {".tif", ".tiff"}:
            import tifffile

            try:
                arr = tifffile.memmap(str(path))
            except (ValueError, MemoryError):
                arr = tifffile.imread(str(path))
        elif suffix == ".npy":
            arr = np.load(str(path), mmap_mode="r")
        elif suffix in {".nii", ".gz"}:
            import nibabel as nib

            # nibabel is (X, Y, Z); transpose to (Z, Y, X).
            arr = np.asarray(nib.load(str(path)).dataobj).transpose(2, 1, 0)
        else:
            raise SliceIOError(f"Unsupported volume format: {path.suffix}")
    except SliceIOError:
        raise
    except Exception as exc:  # pragma: no cover - format-specific failures
        raise SliceIOError(f"Could not open {path.name}: {exc}") from exc

    if arr.ndim == 2:
        arr = arr[np.newaxis, ...]
    elif arr.ndim > 3:
        arr = arr.reshape((-1,) + arr.shape[-2:])

    _lru_put(_volume_cache, key, arr, MAX_OPEN_VOLUMES)
    return arr


def open_label_volume_writable(path: Path, shape: tuple[int, int, int]) -> np.memmap:
    """Open (or create) a label volume as a **writable** memmap, LRU-cached.

    This is the difference between a paint stroke costing milliseconds and
    costing multiple seconds. Editing one slice must only touch that slice's
    pages on disk — reading or writing the *whole* volume (``tifffile.imread``
    / ``imwrite``) on every stroke is O(volume size), not O(slice size), and
    for a real EM label volume (gigabytes) that is an 8+ second stall per
    stroke (measured). ``mm[idx] = ...; mm.flush()`` touches only that plane.

    The handle is kept open and reused across requests (small LRU — these are
    actively-edited files, unlike the read-only volume cache) so repeated
    edits on the same task don't even pay the (cheap, ~2ms) re-open cost.
    """
    import tifffile

    key = (str(path),)
    cached = _lru_get(_label_volume_cache, key)
    if cached is not None and cached.shape == tuple(shape):
        return cached

    if path.exists():
        mm = tifffile.memmap(str(path), mode="r+")
        if mm.shape != tuple(shape):
            # Stale/mismatched file (e.g. the image was replaced) — start
            # fresh rather than silently misaligning slices.
            mm = tifffile.memmap(str(path), shape=shape, dtype=np.uint16, mode="w+")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        mm = tifffile.memmap(str(path), shape=shape, dtype=np.uint16, mode="w+")

    _lru_put(_label_volume_cache, key, mm, MAX_OPEN_LABEL_VOLUMES)
    return mm


def label_max_id(path: Path, mm: np.memmap) -> int:
    """The label volume's highest instance id, cached per process.

    ``mm.max()`` is an O(volume size) scan — cheap once, but calling it on
    every single paint stroke was the other multi-second-per-stroke cost
    alongside the old full read/write (see ``open_label_volume_writable``).
    Computed at most once per file per process; :func:`bump_label_max_id`
    updates it incrementally (O(slice size)) after that.
    """
    key = str(path)
    cached = _label_max_cache.get(key)
    if cached is not None:
        return cached
    val = int(mm.max()) if mm.size else 0
    _label_max_cache[key] = val
    return val


def set_label_max_id(path: Path, value: int) -> None:
    """Seed the cached max for a file we just wrote directly (already had
    the full array in memory — avoids a redundant memmap rescan later)."""
    _label_max_cache[str(path)] = value


def bump_label_max_id(path: Path, mm: np.memmap, slice_max: int) -> int:
    """Fold one freshly-written slice's max into the cached volume-wide max.

    May overestimate after an edit that erases the volume's *only* instance
    of the previous max id (it never rescans down) — harmless: this value is
    only ever used to suggest the next unused id, and skipping a retired
    number costs nothing.
    """
    new_val = max(label_max_id(path, mm), slice_max)
    _label_max_cache[str(path)] = new_val
    return new_val


def display_range(location: str) -> tuple[float, float]:
    """The intensity range a *raw* slice is normalised against, volume-wide.

    Raw slices are streamed once per (axis, index) and re-windowed in the
    browser, so every slice of a volume must be mapped with the *same* lo/hi —
    otherwise brightness would jump as you scroll. uint8 data uses the natural
    0–255; anything else is sampled (a few slices, 0.5/99.5 percentiles) so
    16-bit EM stacks are not crushed to black by their dtype range.
    """
    path = resolve_path(location)
    key = (str(path), path.stat().st_mtime if path.exists() else 0)
    cached = _lru_get(_range_cache, key)
    if cached is not None:
        return cached

    arr = _open_volume(path)
    if arr.dtype == np.uint8:
        rng = (0.0, 255.0)
    else:
        n = arr.shape[0]
        picks = sorted({0, n // 2, max(0, n - 1)})
        sample = np.concatenate(
            [np.asarray(arr[i], dtype=np.float32).ravel() for i in picks]
        )
        lo, hi = (float(v) for v in np.percentile(sample, [0.5, 99.5]))
        if hi <= lo:
            lo, hi = float(sample.min()), float(sample.max())
        if hi <= lo:
            hi = lo + 1.0
        rng = (lo, hi)
    _lru_put(_range_cache, key, rng, MAX_OPEN_VOLUMES)
    return rng


def volume_meta(location: str) -> dict:
    """Shape/axes/dtype for a volume, read from headers (no full load)."""
    arr = _open_volume(resolve_path(location))
    z, y, x = arr.shape
    lo, hi = display_range(location)
    return {
        "shape": {"z": int(z), "y": int(y), "x": int(x)},
        "dtype": str(arr.dtype),
        "axes": list(AXES),
        # What ``?raw=1`` normalised against, so the client can label its
        # brightness/contrast sliders in real intensity units.
        "display_range": {"lo": lo, "hi": hi},
    }


def read_slice(location: str, axis: str, index: int) -> np.ndarray:
    """Return one 2D slice along ``axis`` (``z``/``y``/``x``), LRU-cached."""
    if axis not in AXES:
        raise SliceIOError(f"Unknown axis '{axis}'. Use one of {list(AXES)}.")
    path = resolve_path(location)
    mtime = path.stat().st_mtime if path.exists() else 0
    key = (str(path), mtime, axis, int(index))
    cached = _lru_get(_slice_cache, key)
    if cached is not None:
        return cached

    arr = _open_volume(path)
    axis_i = AXES[axis]
    n = arr.shape[axis_i]
    idx = max(0, min(int(index), n - 1))
    if axis == "z":
        sl = arr[idx]
    elif axis == "y":
        sl = arr[:, idx, :]
    else:
        sl = arr[:, :, idx]
    sl = np.ascontiguousarray(sl)
    _lru_put(_slice_cache, key, sl, MAX_SLICE_CACHE)
    return sl


# --- rendering --------------------------------------------------------------

def _window_level(arr: np.ndarray, window: float | None, level: float | None) -> np.ndarray:
    """Map an image slice to uint8 using brightness/contrast (window/level)."""
    a = arr.astype(np.float32)
    if level is None or window is None or window <= 0:
        lo, hi = float(a.min()), float(a.max())
    else:
        lo, hi = level - window / 2.0, level + window / 2.0
    if hi <= lo:
        hi = lo + 1.0
    return np.clip((a - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)


def _label_color(label_id: int) -> tuple[int, int, int]:
    """Deterministic, well-spread RGB for an instance id (0 == background)."""
    if label_id <= 0:
        return (0, 0, 0)
    h = (label_id * 2654435761) & 0xFFFFFF
    return ((h >> 16) & 0xFF, (h >> 8) & 0xFF, h & 0xFF)


def colorize_labels(label_slice: np.ndarray, alpha: int = 180) -> np.ndarray:
    """Turn an instance-id slice into an RGBA overlay (background transparent)."""
    h, w = label_slice.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    for lid in np.unique(label_slice):
        if lid <= 0:
            continue
        r, g, b = _label_color(int(lid))
        mask = label_slice == lid
        rgba[mask] = (r, g, b, alpha)
    return rgba


def encode_png(arr: np.ndarray) -> bytes:
    """Encode a uint8 HxW (grayscale) or HxWx{3,4} (RGB/RGBA) array as PNG."""
    a = np.ascontiguousarray(arr, dtype=np.uint8)
    if a.ndim == 2:
        color_type, channels = 0, 1
    elif a.ndim == 3 and a.shape[2] == 3:
        color_type, channels = 2, 3
    elif a.ndim == 3 and a.shape[2] == 4:
        color_type, channels = 6, 4
    else:
        raise SliceIOError(f"Cannot encode array of shape {a.shape} as PNG")

    h, w = a.shape[:2]
    # Prepend the per-scanline filter byte (type 0 = None) in one numpy op —
    # a Python loop over rows dominated slice latency for 1k×1k slices.
    raw = np.zeros((h, w * channels + 1), dtype=np.uint8)
    raw[:, 1:] = a.reshape(h, w * channels)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + chunk(b"IEND", b"")
    )


def render_image_slice_png(
    location: str, axis: str, index: int, *, window=None, level=None
) -> bytes:
    """Read + window/level + PNG-encode one image slice.

    When ``window``/``level`` are both omitted, the slice is normalised
    against the volume-wide :func:`display_range` instead of its own
    min/max — the same mapping every slice of the volume uses, so a single
    fetch per slice is stable and brightness/contrast can then be adjusted
    client-side with no further network round trips. Kept for callers that
    explicitly want lossless PNG (and for back-compat); the default client
    flow now uses :func:`render_image_slice_jpeg` — much smaller and, on a
    CPU-only node, much cheaper to encode (libjpeg-turbo via Pillow).
    """
    sl = read_slice(location, axis, index)
    if window is None and level is None:
        lo, hi = display_range(location)
        mapped = np.clip((sl.astype(np.float32) - lo) / (hi - lo) * 255.0, 0, 255).astype(
            np.uint8
        )
        return encode_png(mapped)
    return encode_png(_window_level(sl, window, level))


def encode_jpeg(arr: np.ndarray, quality: int = 87) -> bytes:
    """JPEG-encode a uint8 grayscale array (Pillow / libjpeg-turbo).

    For photographic-style EM intensity data this is both smaller *and* an
    order of magnitude faster to produce than the hand-rolled PNG encoder
    above (benchmarked: ~2x smaller, ~9x faster on a 2758x2514 slice) — no
    GPU involved, libjpeg-turbo is a well-optimised C library that runs
    entirely on CPU and releases the GIL while it works. Only used for the
    intensity image; label overlays stay lossless PNG (need exact instance
    boundaries + alpha transparency).
    """
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(arr, dtype=np.uint8), mode="L").save(
        buf, format="JPEG", quality=quality
    )
    return buf.getvalue()


def render_image_slice_jpeg(location: str, axis: str, index: int, *, quality: int = 87) -> bytes:
    """Read + normalise (volume-wide display range) + JPEG-encode one slice.

    Cached by encoded bytes, not just the decoded array: re-visiting a slice
    (scrubbing back and forth is the common case) costs nothing to re-encode.
    """
    path = resolve_path(location)
    mtime = path.stat().st_mtime if path.exists() else 0
    key = ("jpeg", str(path), mtime, axis, int(index), quality)
    cached = _lru_get(_encoded_cache, key)
    if cached is not None:
        return cached
    sl = read_slice(location, axis, index)
    lo, hi = display_range(location)
    mapped = np.clip((sl.astype(np.float32) - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)
    out = encode_jpeg(mapped, quality=quality)
    _lru_put(_encoded_cache, key, out, MAX_ENCODED_CACHE)
    return out


def render_label_slice_png(location: str, axis: str, index: int) -> bytes:
    """Read + colorize + PNG-encode one label slice as an RGBA overlay."""
    path = resolve_path(location)
    mtime = path.stat().st_mtime if path.exists() else 0
    key = ("label-png", str(path), mtime, axis, int(index))
    cached = _lru_get(_encoded_cache, key)
    if cached is not None:
        return cached
    sl = read_slice(location, axis, index)
    out = encode_png(colorize_labels(sl))
    _lru_put(_encoded_cache, key, out, MAX_ENCODED_CACHE)
    return out


# --- label id RLE (editor read/write) ---------------------------------------
# The in-app editor paints instance ids directly (brush/eraser), so it needs
# the *raw* ids of a slice, not a colorized overlay — and a compact encoding
# to send a whole edited slice back. Run-length encoding a label slice is
# tiny (mostly background / a handful of instances) even though the raw
# array itself (e.g. 1024x1024 int32) would not be.

def encode_label_rle(label_slice: np.ndarray) -> list[list[int]]:
    """Row-major run-length encode a 2D int label slice: ``[[id, count], ...]``."""
    flat = np.ascontiguousarray(label_slice).ravel()
    if flat.size == 0:
        return []
    change = np.flatnonzero(np.diff(flat)) + 1
    starts = np.concatenate(([0], change))
    ends = np.concatenate((change, [flat.size]))
    return [[int(flat[s]), int(e - s)] for s, e in zip(starts, ends)]


def decode_label_rle(runs: list, shape: tuple[int, int]) -> np.ndarray:
    """Inverse of :func:`encode_label_rle`."""
    h, w = shape
    flat = np.empty(h * w, dtype=np.int32)
    pos = 0
    for label_id, count in runs:
        flat[pos : pos + count] = int(label_id)
        pos += int(count)
    if pos != h * w:
        raise SliceIOError(
            f"RLE covers {pos} pixels, expected {h * w} for shape {shape}."
        )
    return flat.reshape(h, w)
