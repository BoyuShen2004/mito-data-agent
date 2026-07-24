"""SAM2 GPU tracking adapter (HPC compute node).

Ports the MTS SAM2 approach (``sam2_bridge.py`` in this package, itself a
port of ``MTS/mts_mask_editor/core/sam2_wrapper.py`` + ``track_propagation.
py``): each fork branch is registered as its own SAM2 object id via
``add_mask_prompt`` and propagated with ``propagate_multi`` in both
directions. The model is heavy and GPU-only, so it must run on a compute node —
in production this adapter is invoked from the worker launched by a
``ProcessingJob`` (``MITO_PROCESSING_BACKEND=slurm``), never inside the web
request. ``torch``/``sam2`` are imported lazily (inside ``sam2_bridge.py``,
not here) so importing this module (and running the rest of the app / tests)
never requires them.

The actual SAM 2 model + weights are vendored under ``vendor/sam2/`` (see
``vendor/README.md``) rather than referencing an external checkout —
``MITO_SAM2_ROOT`` defaults to that vendored copy (``config/settings.py``),
so this provider works out of the box wherever this repo is checked out,
no sibling ``MTS`` directory required.
"""

from __future__ import annotations

from django.conf import settings

from ..interfaces import PropagationRequest, PropagationResult, TrackingProvider


class Sam2TrackingProvider(TrackingProvider):
    name = "sam2"
    requires_gpu = True

    def __init__(self):
        self._sam = None

    def _load(self):
        if self._sam is not None:
            return self._sam
        # Imported here (not at module scope) so non-GPU environments never
        # pull torch/sam2 in just by importing this adapters module.
        from .sam2_bridge import SAM2Wrapper

        sam2_root = getattr(settings, "MITO_SAM2_ROOT", "")
        if not sam2_root:
            raise RuntimeError(
                "MITO_SAM2_ROOT is not set and has no default — this should "
                "not happen unless config/settings.py was changed; see "
                "progress/development.md's SAM2 section."
            )
        checkpoint = getattr(settings, "MITO_SAM2_CHECKPOINT", "") or None
        config = getattr(settings, "MITO_SAM2_CONFIG", "") or None
        self._sam = SAM2Wrapper(sam2_root=sam2_root, checkpoint=checkpoint, config=config)
        return self._sam

    def propagate(self, request: PropagationRequest) -> PropagationResult:
        sam = self._load()
        z_lo, z_hi = request.z_range
        crop = request.image[z_lo : z_hi + 1]

        result = PropagationResult()
        for branch_id, seed_slices in request.seeds.items():
            sam.reset_session()
            sam.initialize_sequence(crop)
            for seed_z, mask in seed_slices.items():
                sam.add_mask_prompt(int(seed_z) - z_lo, obj_id=1, mask=mask)
            seeded_local = [int(z) - z_lo for z in seed_slices]
            raw = sam.propagate_multi(
                min(seeded_local),
                z_range=(0, crop.shape[0] - 1),
                direction="both",
                backward_start_slice=max(seeded_local),
            )
            # Remap local z back to absolute z.
            result.masks[branch_id] = {
                int(z) + z_lo: m for z, m in raw.items()
            }
        return result
