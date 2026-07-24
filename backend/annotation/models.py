from django.conf import settings
from django.db import models

from core.choices import (
    DifficultyLevel,
    PriorityLevel,
    QCStatus,
    ReviewDecision,
    SubmissionSource,
    TaskStatus,
    TaskType,
)
from core.storage import get_mito_storage


def submission_upload_to(instance, filename):
    return f"submissions/task_{instance.task_id}/{filename}"


class AnnotationTask(models.Model):
    """A frame-based annotation unit covering a z-range of a volume."""

    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="tasks"
    )
    volume = models.ForeignKey(
        "volumes.Volume", on_delete=models.CASCADE, related_name="tasks"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="annotation_tasks",
    )

    z_start = models.PositiveIntegerField()
    z_end = models.PositiveIntegerField()
    y_start = models.PositiveIntegerField(default=0)
    y_end = models.PositiveIntegerField()
    x_start = models.PositiveIntegerField(default=0)
    x_end = models.PositiveIntegerField()

    task_type = models.CharField(max_length=30, choices=TaskType.choices)
    status = models.CharField(
        max_length=20, choices=TaskStatus.choices, default=TaskStatus.UNASSIGNED
    )
    priority = models.IntegerField(
        choices=PriorityLevel.choices, default=PriorityLevel.NORMAL
    )
    difficulty = models.IntegerField(
        choices=DifficultyLevel.choices, default=DifficultyLevel.MODERATE
    )
    instructions = models.TextField(blank=True)
    deadline = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["volume_id", "z_start"]

    def __str__(self) -> str:
        return f"Task #{self.pk} {self.volume.name} z[{self.z_start}:{self.z_end}]"

    @property
    def frame_label(self) -> str:
        return f"z {self.z_start}–{self.z_end}"


class AnnotationSubmission(models.Model):
    """A label file submitted by an annotator for a task."""

    task = models.ForeignKey(
        AnnotationTask, on_delete=models.CASCADE, related_name="submissions"
    )
    annotator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submissions",
    )
    # Null/blank for an in-app submission (``source=inapp``) — there's no
    # uploaded file, the "submission" is a checkpoint of the volume's working
    # label copy (see ``annotation.label_paths.working_label_rel_path``).
    label_file = models.FileField(
        storage=get_mito_storage, upload_to=submission_upload_to,
        blank=True, null=True,
    )
    source = models.CharField(
        max_length=10, choices=SubmissionSource.choices, default=SubmissionSource.UPLOAD,
    )
    notes = models.TextField(blank=True)
    qc_status = models.CharField(
        max_length=20, choices=QCStatus.choices, default=QCStatus.NOT_RUN
    )
    qc_report = models.JSONField(default=dict, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self) -> str:
        return f"Submission #{self.pk} for task #{self.task_id}"


class ReviewRecord(models.Model):
    """A manager/reviewer decision on a submission."""

    submission = models.ForeignKey(
        AnnotationSubmission, on_delete=models.CASCADE, related_name="reviews"
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviews",
    )
    decision = models.CharField(max_length=20, choices=ReviewDecision.choices)
    comments = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reviewed_at"]

    def __str__(self) -> str:
        return f"Review #{self.pk} ({self.get_decision_display()})"
