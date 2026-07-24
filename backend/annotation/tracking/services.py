"""Fork-aware SAM2 tracking orchestration (provider-agnostic).

``run_branch_tracking`` is the one place that turns a user's seed mask(s) for a
single logical mitochondrion into a propagated instance, handling forks the way
the spec requires:

1. each 8-connected branch of the seed is given its **own temporary track id**;
2. all branches are kept under one :class:`~annotation.tracking.branching.TrackGroup`;
3. the provider (CPU ``local`` or GPU ``sam2``) propagates each branch;
4. the whole group is **auto-merged into one final instance id** afterwards.

Pure-ish: it mutates the passed ``volume_mask`` array in place and returns a
metadata dict (temporary branch ids, final id, group membership) to persist for
audit / undo / re-run. No Django models are touched here.
"""

from __future__ import annotations

import numpy as np

from .branching import (
    TrackGroup,
    merge_group,
    next_free_id,
    split_binary_mask_components,
)
from .interfaces import PropagationRequest
from .registry import get_tracking_provider


def run_branch_tracking(
    *,
    image: np.ndarray,
    volume_mask: np.ndarray,
    seeds: dict[int, np.ndarray],
    z_range: tuple[int, int] | None = None,
    provider=None,
    group_id: int | None = None,
    reserved=None,
) -> dict:
    """Propagate one (possibly forked) mitochondrion and merge its branches.

    ``seeds`` maps ``z -> 2D bool mask`` — the seed slice(s) for one logical
    mito. Returns ``{"final_id", "branch_ids", "group"}`` and writes the merged
    instance into ``volume_mask``.
    """
    if image.ndim != 3:
        raise ValueError("image must be a 3D (Z, Y, X) array")
    z_max = image.shape[0] - 1
    z_range = z_range or (0, z_max)
    provider = provider or get_tracking_provider()
    reserved = {int(i) for i in (reserved or []) if int(i) > 0}

    if group_id is None:
        group_id = next_free_id(volume_mask, reserved)
    reserved.add(group_id)

    # 1. One temporary track id per fork branch. The first branch reuses the
    #    group id so a non-forking mito needs no merge later.
    branch_seeds: dict[int, dict[int, np.ndarray]] = {}
    branch_ids: list[int] = []
    for z, sl in sorted(seeds.items()):
        for comp in split_binary_mask_components(sl):
            if not branch_ids:
                bid = group_id
            else:
                bid = next_free_id(volume_mask, reserved | set(branch_ids))
            branch_ids.append(bid)
            branch_seeds.setdefault(bid, {})[int(z)] = comp

    if not branch_ids:
        return {"final_id": group_id, "branch_ids": [], "group": None}

    group = TrackGroup(
        group_id=group_id,
        branch_ids=branch_ids,
        seed_z=min(int(z) for z in seeds),
    )

    # 2. Propagate every branch across the z-range (GPU on a real provider).
    result = provider.propagate(
        PropagationRequest(image=image, seeds=branch_seeds, z_range=z_range)
    )

    # 3. Write each branch's propagated mask with its temporary id.
    for bid, per_z in result.masks.items():
        for z, m in per_z.items():
            volume_mask[int(z)][np.asarray(m, dtype=bool)] = bid

    # 4. Auto-merge the whole fork group into one final mitochondria instance.
    merge_group(volume_mask, group)

    return {
        "final_id": group.resolved_final_id(),
        "branch_ids": branch_ids,
        "group": group.to_dict(),
    }
