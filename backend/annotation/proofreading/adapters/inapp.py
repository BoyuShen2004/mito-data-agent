"""In-app annotation-editor proofreading provider.

Reports that the SPA's built-in editor can open a task in **edit** mode: the
editor streams slices from the slice-IO endpoints, edits labels with the
brush/polygon/SAM tools, runs fork-aware SAM2 tracking, and saves back through
the existing submission flow. Role gating (requesters get view-only) is applied
in the service layer, not here — a provider only advertises the capability.
"""

from __future__ import annotations

from ..interfaces import LaunchInfo, ProofreadingProvider


class InAppProofreadingProvider(ProofreadingProvider):
    name = "inapp"

    def get_launch_info(self, task) -> LaunchInfo:
        return LaunchInfo(
            mode="edit",
            url=f"/editor/tasks/{task.id}",
            editable=True,
            download_available=True,
            message="Open the in-app annotation editor to label this task.",
            extra={"editor": "inapp"},
        )
