from django.conf import settings
from django.db import models

from core.choices import UserRole


class Institution(models.Model):
    """An organisation that owns or requests annotation projects."""

    name = models.CharField(max_length=255, unique=True)
    institution_type = models.CharField(max_length=100, blank=True)
    contact_email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class UserProfile(models.Model):
    """Role and institution attached to a Django ``User``."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(
        max_length=20, choices=UserRole.choices, default=UserRole.ANNOTATOR
    )
    institution = models.ForeignKey(
        Institution,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )
    institution_name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.user.get_username()} ({self.get_role_display()})"

    @property
    def is_manager(self) -> bool:
        return self.role == UserRole.MANAGER

    @property
    def is_annotator(self) -> bool:
        return self.role == UserRole.ANNOTATOR


class AnnotatorProfile(models.Model):
    """Annotation-specific capacity and quality info.

    Annotation work is unpaid; no wage/pay-rate fields are tracked.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="annotator_profile",
    )
    is_active_annotator = models.BooleanField(default=True)
    max_active_tasks = models.PositiveIntegerField(default=5)
    quality_score = models.FloatField(default=0.0)
    notes = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"Annotator: {self.user.get_username()}"
