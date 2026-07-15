"""Neuroglancer proofreading provider (read-only viewer).

Neuroglancer is a *viewer*: this adapter builds a view URL but reports
``editable = False`` so the UI never implies edits are written back. Annotators
still submit via upload. Editable Neuroglancer integrations (e.g. with a
segmentation backend) would be a separate, explicitly-editable provider.
"""

from __future__ import annotations

from django.conf import settings

from ..interfaces import LaunchInfo, ProofreadingProvider
from ...visualization.adapters.neuroglancer import build_neuroglancer_url


class NeuroglancerProofreadingProvider(ProofreadingProvider):
    name = "neuroglancer"

    def get_launch_info(self, task) -> LaunchInfo:
        base = getattr(settings, "MITO_NEUROGLANCER_BASE_URL", "")
        url = build_neuroglancer_url(task.volume, base)
        if not url:
            return LaunchInfo(
                mode="unavailable",
                message="MITO_NEUROGLANCER_BASE_URL is not configured.",
                download_available=True,
            )
        return LaunchInfo(
            mode="view",
            url=url,
            editable=False,
            download_available=True,
            message=(
                "Opens Neuroglancer for viewing only. Edit in your own tool "
                "and upload the corrected label."
            ),
        )
