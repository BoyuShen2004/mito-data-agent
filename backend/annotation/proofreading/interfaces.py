"""Proofreading provider interface.

A provider bridges an annotation task to whatever tool the annotator uses. The
UI must be able to distinguish *viewing* from *editing*: a provider that only
returns a read-only viewer link must report ``editable = False`` so the app
never implies edits are possible when they are not.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field


@dataclass
class LaunchInfo:
    """How the client should let an annotator open a task.

    ``mode`` is one of:

    * ``edit``        — an integrated editor can write labels back.
    * ``view``        — a read-only viewer (annotator edits elsewhere, then
                        uploads via the existing submission flow).
    * ``download``    — no launch URL; the annotator downloads a task descriptor
                        and works locally.
    * ``unavailable`` — no integration configured.
    """

    mode: str = "unavailable"
    url: str = ""
    editable: bool = False
    download_available: bool = False
    message: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class ProofreadingProvider(ABC):
    name: str = "base"

    @abstractmethod
    def get_launch_info(self, task) -> LaunchInfo:
        """Return how the client should open ``task`` (view/edit/download)."""

    def create_session(self, task) -> dict:
        """Create/lookup any server-side session for ``task``.

        Default: no server-side session; the launch info is stateless.
        """
        return {"session": None}

    def get_launch_url(self, task) -> str:
        """Convenience: just the launch URL from :meth:`get_launch_info`."""
        return self.get_launch_info(task).url

    def prepare_download(self, task) -> dict:
        """Return a descriptor of what the annotator should download.

        Includes the image/label references and the task region so the work can
        be reproduced locally. Providers may override to package artifacts.
        """
        volume = task.volume
        return {
            "task_id": task.id,
            "volume": volume.name,
            "image_path": volume.image_location,
            "label_path": volume.label_location,
            "region": {
                "z_start": task.z_start,
                "z_end": task.z_end,
                "y_start": task.y_start,
                "y_end": task.y_end,
                "x_start": task.x_start,
                "x_end": task.x_end,
            },
        }

    def ingest_submission(self, task, artifact) -> dict:
        """Ingest a produced label ``artifact`` for ``task``.

        The MVP uses the existing upload-based submission service, so the default
        is a no-op acknowledgement. Providers with a callback/pull integration
        override this.
        """
        return {"ingested": False, "detail": "Uses upload-based submission."}
