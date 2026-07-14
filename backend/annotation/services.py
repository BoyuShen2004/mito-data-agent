"""Deterministic service functions for assignment, submission, and review."""

from __future__ import annotations

import os

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import AnnotatorProfile
from core.choices import (
    ACTIVE_TASK_STATUSES,
    QCStatus,
    ReviewDecision,
    TaskStatus,
)

from .models import AnnotationSubmission, AnnotationTask, ReviewRecord


# --- Assignment ------------------------------------------------------------

def assign_tasks_rule_based(project=None) -> dict:
    """Evenly distribute unassigned tasks across active annotators.

    Rules:
      * consider active annotators (``AnnotatorProfile.is_active_annotator``);
      * an annotator's load = tasks in ``assigned``/``in_progress`` status;
      * never exceed ``max_active_tasks``;
      * process tasks by priority desc, then created_at asc;
      * balance the work: each task goes to the eligible annotator with the
        fewest tasks assigned so far (existing load + this run), so volumes are
        spread out roughly evenly rather than piled onto one person.

    Returns a summary dict with the number assigned and per-annotator counts.
    """
    task_qs = AnnotationTask.objects.filter(status=TaskStatus.UNASSIGNED)
    if project is not None:
        task_qs = task_qs.filter(project=project)
    task_qs = task_qs.order_by("-priority", "created_at")

    # Build capacity + starting-load maps keyed by annotator user id.
    annotators = list(
        AnnotatorProfile.objects.filter(is_active_annotator=True).select_related("user")
    )
    capacity: dict[int, int] = {}
    load: dict[int, int] = {}
    for profile in annotators:
        active = AnnotationTask.objects.filter(
            assigned_to=profile.user, status__in=ACTIVE_TASK_STATUSES
        ).count()
        remaining = max(profile.max_active_tasks - active, 0)
        if remaining > 0:
            capacity[profile.user_id] = remaining
            load[profile.user_id] = active

    assigned_count = 0
    per_user: dict[int, int] = {}

    with transaction.atomic():
        for task in task_qs.select_for_update():
            available = [uid for uid, rem in capacity.items() if rem > 0]
            if not available:
                break
            # Least-loaded annotator wins; ties broken by user id for stability.
            user_id = min(available, key=lambda uid: (load[uid], uid))
            task.assigned_to_id = user_id
            task.status = TaskStatus.ASSIGNED
            task.assigned_at = timezone.now()
            task.save(update_fields=["assigned_to", "status", "assigned_at"])

            capacity[user_id] -= 1
            load[user_id] += 1
            per_user[user_id] = per_user.get(user_id, 0) + 1
            assigned_count += 1

    return {
        "assigned": assigned_count,
        "per_user": per_user,
        "remaining_unassigned": task_qs.model.objects.filter(
            status=TaskStatus.UNASSIGNED,
            **({"project": project} if project is not None else {}),
        ).count(),
    }


def create_whole_volume_task(volume):
    """Create one task spanning a volume's full extent, if it has none.

    Returns the created :class:`AnnotationTask`, or ``None`` when the volume
    already has tasks (duplicate-safe) or has no detectable shape yet.
    """
    from volumes.services import infer_task_type

    if volume.tasks.exists():
        return None
    if not volume.shape_z:
        return None
    return AnnotationTask.objects.create(
        project=volume.project,
        volume=volume,
        z_start=0,
        z_end=volume.shape_z,
        y_start=0,
        y_end=volume.shape_y or 0,
        x_start=0,
        x_end=volume.shape_x or 0,
        task_type=infer_task_type(volume.label_type),
    )


def ensure_volume_tasks(project) -> dict:
    """Create one whole-volume annotation task per volume that has none.

    Auto-assignment works at the volume level: rather than splitting a volume
    into frames, each volume becomes a single task spanning its full extent, so
    a whole volume can be handed to one annotator. Volumes that already have
    tasks (e.g. a manager split them manually) are left untouched. Volumes
    without a detectable shape are skipped.

    Returns ``{"created": n, "skipped": n}``.
    """
    created = 0
    skipped = 0
    for volume in project.volumes.all():
        if volume.tasks.exists():
            continue
        if create_whole_volume_task(volume) is not None:
            created += 1
        else:
            skipped += 1
    return {"created": created, "skipped": skipped}


def auto_assign_project(project) -> dict:
    """Turn each volume into a task and distribute the volumes evenly.

    Requires the project to be manager-reviewed. Volumes with no task get one
    whole-volume task; then all unassigned tasks are balanced across active
    annotators. Returns a summary dict (``reviewed`` is ``False`` when blocked).
    """
    if not project.manager_reviewed:
        return {
            "reviewed": False,
            "assigned": 0,
            "created_tasks": 0,
            "skipped_volumes": 0,
            "per_user": {},
            "remaining_unassigned": 0,
            "detail": "Project must be reviewed by a manager before assignment.",
        }

    ensured = ensure_volume_tasks(project)
    summary = assign_tasks_rule_based(project=project)
    summary["reviewed"] = True
    summary["created_tasks"] = ensured["created"]
    summary["skipped_volumes"] = ensured["skipped"]
    return summary


def assign_task_to_annotator(task: AnnotationTask, *, annotator) -> AnnotationTask:
    """Manually (re)assign a task to ``annotator`` (or unassign when ``None``).

    Updates the existing task in place. Reassignment keeps the same task row,
    so no duplicate annotation tasks are created.
    """
    if annotator is None:
        task.assigned_to = None
        task.status = TaskStatus.UNASSIGNED
        task.assigned_at = None
        task.save(update_fields=["assigned_to", "status", "assigned_at"])
        return task

    task.assigned_to = annotator
    task.assigned_at = timezone.now()
    # Keep an already-in-progress task in progress; otherwise mark as assigned.
    if task.status not in ACTIVE_TASK_STATUSES:
        task.status = TaskStatus.ASSIGNED
    task.save(update_fields=["assigned_to", "status", "assigned_at"])
    return task


# --- Submission + QC -------------------------------------------------------

def run_basic_qc(submission: AnnotationSubmission) -> dict:
    """Run simple checks on a submission and persist qc_status/qc_report.

    Checks: file present, non-zero size, allowed extension, linked to a task.
    """
    report = {"checks": [], "errors": [], "warnings": []}

    def check(name, ok, message="", level="errors"):
        report["checks"].append({"name": name, "ok": bool(ok)})
        if not ok:
            report[level].append(message or name)

    linked = submission.task_id is not None
    check("linked_to_task", linked, "Submission is not linked to a task")

    field = submission.label_file
    exists = bool(field) and field.storage.exists(field.name)
    check("file_exists", exists, "Label file does not exist on storage")

    size = 0
    if exists:
        try:
            size = field.size
        except (OSError, ValueError):
            size = 0
    check("non_empty", size > 0, "Label file is empty")

    name = field.name if field else ""
    ext = _matched_extension(name)
    check(
        "allowed_extension",
        bool(ext),
        f"Extension not allowed for '{os.path.basename(name)}'",
    )

    report["file_size"] = size
    report["extension"] = ext

    if report["errors"]:
        status = QCStatus.FAILED
    elif report["warnings"]:
        status = QCStatus.WARNING
    else:
        status = QCStatus.PASSED

    submission.qc_status = status
    submission.qc_report = report
    submission.save(update_fields=["qc_status", "qc_report"])
    return report


def _matched_extension(name: str) -> str:
    lower = name.lower()
    for ext in sorted(settings.MITO_ALLOWED_LABEL_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(ext):
            return ext
    return ""


def submit_annotation(
    *, task: AnnotationTask, annotator, label_file, notes: str = ""
) -> AnnotationSubmission:
    """Record an annotator's submission, run QC, and mark the task submitted."""
    submission = AnnotationSubmission.objects.create(
        task=task, annotator=annotator, label_file=label_file, notes=notes
    )
    run_basic_qc(submission)

    task.status = TaskStatus.SUBMITTED
    task.submitted_at = timezone.now()
    task.save(update_fields=["status", "submitted_at"])
    return submission


# --- Review ----------------------------------------------------------------

def review_submission(
    *, submission: AnnotationSubmission, reviewer, decision: str, comments: str = ""
) -> ReviewRecord:
    """Record a review decision and apply the resulting task-state change."""
    if decision == ReviewDecision.APPROVED:
        return approve_submission(submission, reviewer=reviewer, comments=comments)
    if decision == ReviewDecision.REJECTED:
        return reject_submission(submission, reviewer=reviewer, comments=comments)
    if decision == ReviewDecision.REVISION_REQUESTED:
        return request_revision(submission, reviewer=reviewer, comments=comments)
    raise ValueError(f"Unknown review decision: {decision}")


def _record_review(submission, reviewer, decision, comments) -> ReviewRecord:
    return ReviewRecord.objects.create(
        submission=submission,
        reviewer=reviewer,
        decision=decision,
        comments=comments,
    )


def approve_submission(submission, *, reviewer=None, comments="") -> ReviewRecord:
    """Approve a submission: task -> approved, set approved_at."""
    review = _record_review(submission, reviewer, ReviewDecision.APPROVED, comments)
    task = submission.task
    task.status = TaskStatus.APPROVED
    task.approved_at = timezone.now()
    task.save(update_fields=["status", "approved_at"])
    return review


def reject_submission(submission, *, reviewer=None, comments="") -> ReviewRecord:
    review = _record_review(submission, reviewer, ReviewDecision.REJECTED, comments)
    task = submission.task
    task.status = TaskStatus.REJECTED
    task.save(update_fields=["status"])
    return review


def request_revision(submission, *, reviewer=None, comments="") -> ReviewRecord:
    review = _record_review(
        submission, reviewer, ReviewDecision.REVISION_REQUESTED, comments
    )
    task = submission.task
    task.status = TaskStatus.REVISION_REQUESTED
    task.save(update_fields=["status"])
    return review


# --- Workload --------------------------------------------------------------

def calculate_annotator_workload(project=None) -> list[dict]:
    """Per-annotator task counts (active, submitted, approved, total)."""
    task_qs = AnnotationTask.objects.exclude(assigned_to__isnull=True)
    if project is not None:
        task_qs = task_qs.filter(project=project)

    rows = (
        task_qs.values("assigned_to", "assigned_to__username")
        .annotate(
            total=Count("id"),
            active=Count(
                "id", filter=Q(status__in=ACTIVE_TASK_STATUSES)
            ),
            submitted=Count("id", filter=Q(status=TaskStatus.SUBMITTED)),
            approved=Count("id", filter=Q(status=TaskStatus.APPROVED)),
        )
        .order_by("assigned_to__username")
    )
    return [
        {
            "annotator_id": r["assigned_to"],
            "username": r["assigned_to__username"],
            "total": r["total"],
            "active": r["active"],
            "submitted": r["submitted"],
            "approved": r["approved"],
        }
        for r in rows
    ]
