from django.conf import settings
from django.db import models

from core.choices import AnnotationType, ProjectStatus


class Project(models.Model):
    """An annotation project grouping volumes, tasks, and their workflow."""

    title = models.CharField(max_length=255)
    institution = models.ForeignKey(
        "accounts.Institution",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects",
    )
    description = models.TextField(blank=True)
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title
