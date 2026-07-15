"""Basic file-level submission QC.

This is the modular home of the original ``run_basic_qc`` checks: the label file
must be linked to a task, exist on storage, be non-empty, and carry an allowed
extension. Behaviour is preserved; the result is now returned in the standard
provider shape (``passed``/``checks``/``metrics``/``warnings``/``errors``).
"""

from __future__ import annotations

import os

from django.conf import settings

from ..interfaces import QualityControlProvider, add_check, empty_report


class BasicQualityControlProvider(QualityControlProvider):
    name = "basic"

    def validate_submission(self, submission) -> dict:
        report = empty_report()

        add_check(
            report,
            "linked_to_task",
            submission.task_id is not None,
            "Submission is not linked to a task",
        )

        field = submission.label_file
        exists = bool(field) and field.storage.exists(field.name)
        add_check(report, "file_exists", exists, "Label file does not exist on storage")

        size = 0
        if exists:
            try:
                size = field.size
            except (OSError, ValueError):
                size = 0
        add_check(report, "non_empty", size > 0, "Label file is empty")

        name = field.name if field else ""
        ext = matched_label_extension(name)
        add_check(
            report,
            "allowed_extension",
            bool(ext),
            f"Extension not allowed for '{os.path.basename(name)}'",
        )

        report["metrics"].update(self.calculate_metrics(submission))
        report["metrics"]["file_size"] = size
        report["metrics"]["extension"] = ext
        # Backwards-compatible top-level keys some callers/tests may read.
        report["file_size"] = size
        report["extension"] = ext
        return report

    def calculate_metrics(self, submission) -> dict:
        field = submission.label_file
        return {"filename": os.path.basename(field.name) if field else ""}


def matched_label_extension(name: str) -> str:
    """Return the allowed label extension ``name`` ends with, or ``""``.

    Longest-match first so ``.nii.gz`` beats ``.gz``.
    """
    lower = name.lower()
    for ext in sorted(settings.MITO_ALLOWED_LABEL_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(ext):
            return ext
    return ""
