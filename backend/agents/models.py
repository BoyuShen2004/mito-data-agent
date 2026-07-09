from django.conf import settings
from django.db import models

from core.choices import AgentPlanStatus


class AgentPlan(models.Model):
    """Placeholder for future agent-assisted planning.

    Stores a proposed plan (JSON) that a manager can approve before it is
    applied by calling the deterministic service layer. No LangGraph logic is
    implemented for the MVP.
    """

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="agent_plans",
    )
    plan_type = models.CharField(max_length=100)
    plan_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20, choices=AgentPlanStatus.choices, default=AgentPlanStatus.PENDING
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_agent_plans",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_agent_plans",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"AgentPlan #{self.pk} ({self.plan_type})"
