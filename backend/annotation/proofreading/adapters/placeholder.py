"""Placeholder proofreading provider.

No editor is integrated: the annotator downloads a task descriptor, works in
their own tool, and uploads the result through the existing submission flow.
This is the default so the app is honest about what is (not) wired up.
"""

from __future__ import annotations

from ..interfaces import LaunchInfo, ProofreadingProvider


class PlaceholderProofreadingProvider(ProofreadingProvider):
    name = "placeholder"

    def get_launch_info(self, task) -> LaunchInfo:
        return LaunchInfo(
            mode="download",
            url="",
            editable=False,
            download_available=True,
            message=(
                "No online editor is configured. Download the task data, "
                "annotate in your own tool, then upload the label file."
            ),
        )
