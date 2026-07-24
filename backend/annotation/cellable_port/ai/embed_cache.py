"""On-disk EfficientSAM embedding cache.

Ported *idea* from ``cellable/labelme/utils/pre_compute_tiff_sam_feature.py``
(background-computes ``embedding_dir/slice_{i}.npy`` files so scrubbing
through an already-visited slice never re-runs the encoder) — adapted from
"one file per slice index in a fixed local directory" to mito's multi-volume,
multi-model-variant web backend, where the same slice index means nothing
without also knowing *which volume*, *which axis*, and *which EfficientSAM
weight tier* produced it.

**Cache key**: ``volume_id`` + ``axis`` + ``index`` + ``variant`` (``vits``/
``vitt``) + the source image file's mtime. The mtime is what makes this
safe against silently poisoning accuracy: swap the model variant (a
different path, already part of the key) or replace/re-register the
underlying image file (a new mtime) and old entries simply become
unreachable — never loaded, never mistaken for a match. There is no cleanup
of orphaned old-mtime files (this is a cache, not a store of record; see
``progress/history/23-cellable-parity-ort-and-prompt-ux.md`` for why that
tradeoff — same reasoning `slice_io.py`'s in-memory caches already use:
simplicity over eager cleanup for something that's cheap to regenerate).

Lives under ``MITO_DATA_ROOT/embeddings/`` — sibling to (never inside) the
per-volume working-label folders, so ``core.dev_data.clear_dev_data``'s
whole-root wipe already clears it for free, and it's obviously not
annotation data if anyone browses the data root directly.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from django.conf import settings


def cache_path_for(volume_id: int, axis: str, index: int, variant: str, image_mtime: float) -> Path:
    root = Path(settings.MITO_DATA_ROOT) / "embeddings" / variant / f"volume_{volume_id}"
    return root / f"{axis}_{int(index)}_{int(image_mtime)}.npy"


def load(path: Path) -> np.ndarray | None:
    if not path.exists():
        return None
    try:
        return np.load(str(path))
    except (OSError, ValueError):
        # A half-written or corrupted cache file is just a miss, not an
        # error worth surfacing — the caller recomputes and overwrites it.
        return None


def save(path: Path, embedding: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # `np.save` appends `.npy` itself unless the given name already ends
    # with it — the tmp name must end in `.npy` too, or the file actually
    # lands at `<tmp>.npy` while `os.replace` looks for it at `<tmp>`.
    tmp = path.parent / f"{path.stem}.tmp.npy"
    np.save(str(tmp), embedding)
    os.replace(str(tmp), str(path))
