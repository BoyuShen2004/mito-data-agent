"""External-tool proofreading provider.

Points the annotator at a configured external editor (``MITO_PROOFREADING_TOOL_URL``),
passing the task id as a query parameter. Whether that tool can write labels
back is deployment-specific; we conservatively report ``editable = True`` only
when a URL is configured, and still allow upload-based submission.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings

from ..interfaces import LaunchInfo, ProofreadingProvider


class ExternalToolProofreadingProvider(ProofreadingProvider):
    name = "external_tool"

    def get_launch_info(self, task) -> LaunchInfo:
        base = getattr(settings, "MITO_PROOFREADING_TOOL_URL", "")
        if not base:
            return LaunchInfo(
                mode="unavailable",
                message="MITO_PROOFREADING_TOOL_URL is not configured.",
                download_available=True,
            )
        sep = "&" if "?" in base else "?"
        url = f"{base}{sep}{urlencode({'task': task.id})}"
        return LaunchInfo(
            mode="edit",
            url=url,
            editable=True,
            download_available=True,
            message="Opens the configured external proofreading tool.",
        )
