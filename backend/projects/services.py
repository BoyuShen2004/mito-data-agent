"""Deterministic service functions for projects.

These are the stable building blocks reused by views, admin actions,
management commands, and (later) agent tools. They take plain arguments and
return model instances or plain dicts.
"""

from __future__ import annotations

from django.utils import timezone

from core.choices import TaskStatus

from .models import Project


def create_project(
    *,
    title: str,
    created_by=None,
    institution=None,
    description: str = "",
    annotation_target: str = "mitochondria",
    annotation_type: str | None = None,
    deadline=None,
    status: str | None = None,
    dataset: str = "",
    metadata: dict | None = None,
    reviewed: bool = False,
) -> Project:
    """Create and return a new :class:`Project`.

    ``reviewed`` marks the project as manager-reviewed on creation (used when a
    manager registers data directly); requester-registered data stays pending.
    """
    kwargs = {
        "title": title,
        "created_by": created_by,
        "institution": institution,
        "description": description,
        "annotation_target": annotation_target,
        "dataset": dataset or "",
        "metadata": metadata or {},
        "manager_reviewed": reviewed,
    }
    if reviewed:
        kwargs["reviewed_by"] = created_by
        kwargs["reviewed_at"] = timezone.now()
    if annotation_type is not None:
        kwargs["annotation_type"] = annotation_type
    if status is not None:
        kwargs["status"] = status
    if deadline is not None:
        kwargs["deadline"] = deadline
    return Project.objects.create(**kwargs)


def calculate_project_progress(project: Project) -> dict:
    """Return counts and a completion percentage for a project's tasks."""
    tasks = project.tasks.all()
    total = tasks.count()

    status_counts = {status.value: 0 for status in TaskStatus}
    for task in tasks.only("status"):
        status_counts[task.status] = status_counts.get(task.status, 0) + 1

    approved = status_counts.get(TaskStatus.APPROVED, 0)
    percent = round(100 * approved / total, 1) if total else 0.0

    return {
        "total_tasks": total,
        "approved_tasks": approved,
        "percent_complete": percent,
        "status_counts": status_counts,
        "volumes": project.volumes.count(),
    }
