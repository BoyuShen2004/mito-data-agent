"""EfficientSAM (ONNX) point/box-prompt mask prediction.

Ported from ``cellable/labelme/ai/efficient_sam.py`` (the ``EfficientSam``
class + its module-level ``_compute_mask_from_points``/``_compute_mask_from_box``
helpers). Kept: the encoder/decoder ONNX inference itself, the small-object
cleanup (``skimage.morphology.remove_small_objects``), and an image-embedding
cache (an embedding only depends on the image, not the prompt, so re-clicking
several points on the same slice re-uses it) — now backed by both an
in-process LRU (keyed by image bytes) and an optional on-disk cache (see
``embed_cache.py``, ported from Cellable's
``utils/pre_compute_tiff_sam_feature.py`` idea).

Dropped vs. the original: the background ``threading.Thread`` that
pre-computed embeddings off the Qt event loop (mito's warm-up is a
lightweight, explicit "warm-embedding" request instead — see
``services.warm_ai_embedding`` — since a Django request/response cycle has
no equivalent to a long-lived Qt background thread to hand work off to).

**Thread-count fix (not a Cellable mechanism — Cellable runs on one local
desktop, this app runs on a shared HPC node):** ``onnxruntime`` defaults to
sizing its intra-op thread pool from the *physical* core count, which on a
SLURM allocation restricted to fewer CPUs (``-c 4``, cgroup-limited)
produces a flood of harmless-but-noisy ``pthread_setaffinity_np failed ...
Invalid argument`` messages — onnxruntime tries to pin threads to CPUs
outside the cgroup's affinity mask. ``_resolve_thread_count`` reads the
actual usable CPU count (SLURM's own env var first, then the process's real
affinity mask, then the OS-reported count) and both sessions are built with
an explicit ``SessionOptions`` instead of onnxruntime's own guess.
"""

from __future__ import annotations

import collections
import os
import threading

import numpy as np

_MAX_EMBEDDING_CACHE = 16
# Encoder + decoder are run one after another for a single request, never
# concurrently within one predict call — inter-op parallelism (independent
# graph branches running at once) buys nothing here and only adds thread-pool
# overhead, so it's pinned to 1 regardless of the intra-op count below.
_MAX_INTRA_OP_THREADS = 8


def _resolve_thread_count() -> int:
    """Usable CPU count for this process, capped sensibly.

    Priority: ``SLURM_CPUS_PER_TASK`` (what the scheduler actually granted,
    when running under `sbatch`/`srun`) -> ``os.sched_getaffinity(0)`` (the
    real cgroup-restricted affinity mask on Linux — more reliable than
    ``os.cpu_count()``, which reports the *node's* total CPUs regardless of
    what this process is actually allowed to use) -> ``os.cpu_count()`` (last
    resort, e.g. non-Linux or affinity unavailable) -> ``1``.
    """
    raw = os.environ.get("SLURM_CPUS_PER_TASK")
    if raw:
        try:
            n = int(raw)
            if n > 0:
                return min(n, _MAX_INTRA_OP_THREADS)
        except ValueError:
            pass
    sched_getaffinity = getattr(os, "sched_getaffinity", None)
    if sched_getaffinity is not None:
        try:
            n = len(sched_getaffinity(0))
            if n > 0:
                return min(n, _MAX_INTRA_OP_THREADS)
        except OSError:
            pass
    n = os.cpu_count() or 1
    return min(n, _MAX_INTRA_OP_THREADS)


def _session_options():
    import onnxruntime

    threads = _resolve_thread_count()
    opts = onnxruntime.SessionOptions()
    opts.intra_op_num_threads = threads
    opts.inter_op_num_threads = 1
    return opts


def _to_rgb(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return np.stack([image] * 3, axis=-1).astype(np.uint8)
    if image.ndim == 3 and image.shape[2] in (3, 4):
        return image[:, :, :3].astype(np.uint8)
    raise ValueError(f"Unsupported image shape {image.shape}. Must be 2D or 3D (H, W, C).")


class EfficientSam:
    def __init__(self, encoder_path: str, decoder_path: str):
        import onnxruntime

        opts = _session_options()
        self._encoder = onnxruntime.InferenceSession(encoder_path, sess_options=opts)
        self._decoder = onnxruntime.InferenceSession(decoder_path, sess_options=opts)
        self._lock = threading.Lock()
        self._embedding_cache: "collections.OrderedDict[bytes, np.ndarray]" = (
            collections.OrderedDict()
        )

    def _embed(self, image_rgb: np.ndarray, disk_path=None) -> np.ndarray:
        """Encoder embedding for ``image_rgb``, cached in-process (keyed by
        image bytes — an embedding only depends on the image, not the
        prompt) and, if ``disk_path`` is given, on disk too (see
        ``embed_cache.py``). A disk hit still gets folded into the
        in-process LRU so a second click on the same slice this session
        never re-reads the file."""
        key = image_rgb.tobytes()
        with self._lock:
            cached = self._embedding_cache.get(key)
            if cached is not None:
                self._embedding_cache.move_to_end(key)
                return cached

        if disk_path is not None:
            from . import embed_cache

            cached = embed_cache.load(disk_path)
            if cached is not None:
                self._store_embedding(key, cached)
                return cached

        batched = image_rgb.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        (embedding,) = self._encoder.run(
            output_names=None, input_feed={"batched_images": batched}
        )
        self._store_embedding(key, embedding)
        if disk_path is not None:
            from . import embed_cache

            embed_cache.save(disk_path, embedding)
        return embedding

    def _store_embedding(self, key: bytes, embedding: np.ndarray) -> None:
        with self._lock:
            self._embedding_cache[key] = embedding
            self._embedding_cache.move_to_end(key)
            while len(self._embedding_cache) > _MAX_EMBEDDING_CACHE:
                self._embedding_cache.popitem(last=False)

    def warm(self, image: np.ndarray, disk_path=None) -> None:
        """Compute (and cache, in-process + optionally on disk) the
        embedding for ``image`` without predicting anything — so the first
        real click on this slice only has to run the (fast) decoder. Mirrors
        the *intent* of Cellable's background embedding thread; see
        ``services.warm_ai_embedding`` for how it's triggered."""
        self._embed(_to_rgb(image), disk_path=disk_path)

    def predict_mask_from_points(
        self, image: np.ndarray, points, point_labels, disk_path=None
    ) -> np.ndarray:
        """``points``: ``[[x, y], ...]``; ``point_labels``: ``1`` (positive) /
        ``0`` (negative) per point, same convention as Cellable's ai_mask
        mode (shift+click = negative)."""
        rgb = _to_rgb(image)
        embedding = self._embed(rgb, disk_path=disk_path)
        return _decode_mask(self._decoder, rgb, embedding, points, point_labels)

    def predict_mask_from_box(self, image: np.ndarray, box_points, disk_path=None) -> np.ndarray:
        """``box_points``: ``[[x1, y1], [x2, y2]]``. SAM's box-prompt point
        labels are the fixed pair ``[2, 3]`` (top-left/bottom-right corner
        markers), same as Cellable's ``_compute_mask_from_box``."""
        rgb = _to_rgb(image)
        embedding = self._embed(rgb, disk_path=disk_path)
        return _decode_mask(self._decoder, rgb, embedding, box_points, [2, 3])


def _decode_mask(decoder, image, embedding, points, point_labels) -> np.ndarray:
    import skimage.morphology

    input_point = np.array(points, dtype=np.float32)[None, None, :, :]
    input_label = np.array(point_labels, dtype=np.float32)[None, None, :]
    masks, _, _ = decoder.run(
        None,
        {
            "image_embeddings": embedding,
            "batched_point_coords": input_point,
            "batched_point_labels": input_label,
            "orig_im_size": np.array(image.shape[:2], dtype=np.int64),
        },
    )
    mask = masks[0, 0, 0, :, :] > 0.0  # (1, 1, 3, H, W) -> (H, W)
    if mask.any():
        # `max_size` replaces the deprecated `min_size` as of skimage 0.26
        # (see that release's FutureWarning) — the two aren't quite the same
        # comparison (old: strictly smaller than min_size is removed; new:
        # smaller-than-**or-equal-to** max_size is removed), but since the
        # threshold here is a float percentage of a runtime-computed mask
        # sum rather than a fixed integer, the boundary case where that
        # off-by-one-pixel difference would actually matter essentially
        # never occurs — same ~5% small-object cleanup intent as Cellable,
        # just with the current (non-deprecated) keyword.
        skimage.morphology.remove_small_objects(mask, max_size=mask.sum() * 0.05, out=mask)
    return mask
