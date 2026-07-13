from django.conf import settings
from django.db import models

from core.choices import AnnotationType, ProjectStatus


class Project(models.Model):
    """An annotation project grouping volumes, tasks, and their workflow."""

    title = models.CharField(max_length=255)
    # Dataset name this project registers. Required at registration time; a
    # dataset may contain one or more volumes (see ``volumes.Volume``).
    dataset = models.CharField(max_length=255, blank=True)
    institution = models.ForeignKey(
        "accounts.Institution",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects",
    )
    description = models.TextField(blank=True)
    # Optional biomedical EM metadata that cannot be derived from the files
    # (organism, tissue, cell type, imaging modality, instrument, conditions,
    # source, publication, notes, …). Kept flexible as structured JSON.
    metadata = models.JSONField(default=dict, blank=True)
    annotation_target = models.CharField(max_length=100, default="mitochondria")
    annotation_type = models.CharField(
        max_length=30,
        choices=AnnotationType.choices,
        default=AnnotationType.INSTANCE,
    )
    status = models.CharField(
        max_length=20, choices=ProjectStatus.choices, default=ProjectStatus.DRAFT
    )
    deadline = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_projects",
    )

    # Manager review gate: requester-registered data must be reviewed by a
    # manager before its volumes can be split or assigned. Manager-registered
    # data is reviewed on creation.
    manager_reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_projects",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title
