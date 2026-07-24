"""Deterministic service functions for assignment, submission, and review."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import AnnotatorProfile
from core.choices import (
    ACTIVE_TASK_STATUSES,
    LabelType,
    QCStatus,
    ReviewDecision,
    SubmissionSource,
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


def _plan_balanced_assignments(tasks, profiles) -> dict[int, int]:
    """Propose ``{task_id: annotator_user_id}`` without persisting anything.

    ``tasks`` is an ordered iterable of :class:`AnnotationTask` (highest
    priority first); ``profiles`` a list of active ``AnnotatorProfile``. Mirrors
    the balancing used by :func:`assign_tasks_rule_based` (respect each
    annotator's remaining capacity; least-loaded wins, ties by user id) but only
    computes a plan so a manager can review and edit it before it is committed.
    """
    capacity: dict[int, int] = {}
    load: dict[int, int] = {}
    for profile in profiles:
        active = AnnotationTask.objects.filter(
            assigned_to=profile.user, status__in=ACTIVE_TASK_STATUSES
        ).count()
        remaining = max(profile.max_active_tasks - active, 0)
        if remaining > 0:
            capacity[profile.user_id] = remaining
            load[profile.user_id] = active

    plan: dict[int, int] = {}
    for task in tasks:
        available = [uid for uid, rem in capacity.items() if rem > 0]
        if not available:
            break
        user_id = min(available, key=lambda uid: (load[uid], uid))
        plan[task.id] = user_id
        capacity[user_id] -= 1
        load[user_id] += 1
    return plan


def preview_assign_project(project) -> dict:
    """Build an editable assignment plan for a project without committing it.

    Ensures each volume has a whole-volume task, then proposes an annotator for
    every currently-unassigned task (balanced across active annotators). Tasks
    that are already assigned keep their current annotator. Nothing about who is
    assigned to what is saved — the manager reviews/edits the returned plan and
    commits it via :func:`apply_assignment_plan`.

    Returns ``{"reviewed", "created_tasks", "skipped_volumes", "proposed"}``
    where ``proposed`` maps ``task_id -> proposed_annotator_id`` (``None`` when
    no annotator has spare capacity).
    """
    if not project.manager_reviewed:
        return {
            "reviewed": False,
            "created_tasks": 0,
            "skipped_volumes": 0,
            "proposed": {},
            "detail": "Project must be reviewed by a manager before assignment.",
        }

    ensured = ensure_volume_tasks(project)
    unassigned = list(
        AnnotationTask.objects.filter(
            project=project, status=TaskStatus.UNASSIGNED
        ).order_by("-priority", "created_at")
    )
    profiles = list(
        AnnotatorProfile.objects.filter(is_active_annotator=True).select_related("user")
    )
    proposed = _plan_balanced_assignments(unassigned, profiles)
    return {
        "reviewed": True,
        "created_tasks": ensured["created"],
        "skipped_volumes": ensured["skipped"],
        "proposed": proposed,
    }


def list_assignment_plan_rows(project) -> dict:
    """Ensure every volume has a whole-volume task and report the outcome,
    but — unlike :func:`preview_assign_project` — never propose annotators.

    Lets the assignment-plan UI show every volume that needs assigning (and
    let the manager start editing priority/difficulty/deadline/annotator
    right away) without first requiring a click on "Auto-fill balanced
    plan"; that button still owns proposing annotators, this just owns
    making sure a row exists to edit.
    """
    if not project.manager_reviewed:
        return {
            "reviewed": False,
            "created_tasks": 0,
            "skipped_volumes": 0,
            "detail": "Project must be reviewed by a manager before assignment.",
        }
    ensured = ensure_volume_tasks(project)
    return {
        "reviewed": True,
        "created_tasks": ensured["created"],
        "skipped_volumes": ensured["skipped"],
    }


# Task fields a manager may edit while curating an assignment plan.
PLAN_EDITABLE_FIELDS = ("priority", "difficulty", "instructions", "deadline")


def apply_assignment_plan(project, entries, *, annotators_by_id) -> dict:
    """Commit a manager-edited assignment plan atomically.

    ``entries`` is a list of dicts, each carrying a ``task_id``, an optional
    ``annotator_id`` (``None``/absent unassigns), and any of the editable task
    fields in :data:`PLAN_EDITABLE_FIELDS`. ``annotators_by_id`` maps user id to
    a validated annotator ``User``. Every task must belong to ``project``; the
    whole plan is applied in one transaction so a bad entry rolls back the rest.

    Returns ``{"updated", "assigned", "remaining_unassigned"}``.
    """
    task_map = {t.id: t for t in project.tasks.select_related("assigned_to")}
    updated = 0

    with transaction.atomic():
        for entry in entries:
            task = task_map.get(entry["task_id"])
            if task is None:
                raise ValueError(
                    f"Task {entry['task_id']} does not belong to this project."
                )

            field_updates = [
                f for f in PLAN_EDITABLE_FIELDS if f in entry
            ]
            for field in field_updates:
                setattr(task, field, entry[field])
            if field_updates:
                task.save(update_fields=field_updates)

            if "annotator_id" in entry:
                annotator_id = entry["annotator_id"]
                annotator = (
                    annotators_by_id.get(annotator_id)
                    if annotator_id is not None
                    else None
                )
                assign_task_to_annotator(task, annotator=annotator)

            updated += 1

    remaining = project.tasks.filter(status=TaskStatus.UNASSIGNED).count()
    assigned = project.tasks.exclude(status=TaskStatus.UNASSIGNED).count()
    return {
        "updated": updated,
        "assigned": assigned,
        "remaining_unassigned": remaining,
    }


def create_whole_volume_task(volume):
    """Create one task spanning a volume's full extent, if it has none.

    Returns the created :class:`AnnotationTask`, or ``None`` when the volume
    already has tasks (duplicate-safe) or has no detectable shape yet.
    ``deadline`` defaults to the project's own deadline — a manager can still
    override it per task in the assignment plan, but "same as the project"
    is the sane default rather than blank.
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
        deadline=volume.project.deadline,
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
    """Run the configured QC provider on a submission and persist the result.

    The checks themselves live behind the modular QC provider
    (``annotation.quality_control``); this function selects the provider, maps
    its structured report to a :class:`~core.choices.QCStatus`, and saves both.
    The default ``basic`` provider preserves the original file-level checks
    (linked to a task, present, non-empty, allowed extension).
    """
    from .quality_control.registry import get_qc_provider

    report = get_qc_provider().validate_submission(submission)

    if report.get("errors"):
        status = QCStatus.FAILED
    elif report.get("warnings"):
        status = QCStatus.WARNING
    else:
        status = QCStatus.PASSED

    submission.qc_status = status
    submission.qc_report = report
    submission.save(update_fields=["qc_status", "qc_report"])
    return report


def submit_annotation(
    *, task: AnnotationTask, annotator, label_file, notes: str = ""
) -> AnnotationSubmission:
    """Record an annotator's uploaded-file submission, run QC, mark submitted.

    Approving this submission does **not** currently change the volume's
    official label (that promotion only exists for in-app submissions today
    — see :func:`submit_inapp_annotation` and :func:`approve_submission`).
    Unchanged from before this module gained the in-app staging/approval
    workflow.
    """
    submission = AnnotationSubmission.objects.create(
        task=task, annotator=annotator, label_file=label_file, notes=notes,
        source=SubmissionSource.UPLOAD,
    )
    run_basic_qc(submission)

    task.status = TaskStatus.SUBMITTED
    task.submitted_at = timezone.now()
    task.save(update_fields=["status", "submitted_at"])
    return submission


def submit_inapp_annotation(
    *, task: AnnotationTask, annotator, notes: str = ""
) -> AnnotationSubmission:
    """Submit a task's in-app-edited *working* label copy for review.

    Unlike :func:`submit_annotation`, there is no file to upload — the
    "submission" is a checkpoint marking the working copy's *current* state
    (see :func:`annotation.label_paths.working_label_rel_path`) as ready for
    manager review. It stays purely a staging copy — the volume's official
    label is untouched — until :func:`approve_submission` promotes it.

    Raises ``ValueError`` if nothing has been painted/tracked yet (no working
    copy exists), so submitting is never a silent no-op.
    """
    from .label_paths import working_label_rel_path
    from .visualization.slice_io import resolve_path

    working_path = resolve_path(working_label_rel_path(task.volume))
    if not working_path.exists():
        raise ValueError(
            "Nothing has been annotated in-app for this task's volume yet — "
            "paint or track at least one slice before submitting."
        )

    submission = AnnotationSubmission.objects.create(
        task=task, annotator=annotator, notes=notes, source=SubmissionSource.INAPP,
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
    """Approve a submission: task -> approved, set approved_at.

    For an **in-app** submission (``source=inapp``), approval is also the
    one moment the volume's working label copy gets promoted to its
    *official* label — repointing ``label_path``/clearing ``label_file`` (see
    ``_repoint_label``) so every viewer now sees the approved result. Before
    this, nothing about the in-app edits was visible outside the editor
    itself; rejecting or requesting revision (see below) never promotes
    anything, so unapproved work never becomes "the" mask.

    Uploaded-file submissions are unchanged from before this staging/approval
    workflow existed: approving one does not touch ``Volume.label_path``/
    ``label_file`` at all (that pathway has never merged the upload back into
    the volume's label — out of scope here, see
    ``progress/history/14-mask-staging-and-approval.md``).
    """
    review = _record_review(submission, reviewer, ReviewDecision.APPROVED, comments)
    task = submission.task
    task.status = TaskStatus.APPROVED
    task.approved_at = timezone.now()
    task.save(update_fields=["status", "approved_at"])

    if submission.source == SubmissionSource.INAPP:
        _promote_working_label_to_official(task.volume)
    return review


def _promote_working_label_to_official(volume) -> None:
    """Repoint ``volume``'s official label at its current working copy.

    Only called from ``approve_submission`` for an in-app submission. If the
    working copy has somehow vanished since submit (it shouldn't —
    ``submit_inapp_annotation`` requires it to exist), this is a no-op rather
    than an error: approval already recorded the review decision and task
    status change above, and there's nothing sensible to promote.
    """
    from .label_paths import working_label_rel_path
    from .visualization.slice_io import resolve_path

    rel = working_label_rel_path(volume)
    if not resolve_path(rel).exists():
        return

    update_fields = _repoint_label(volume, rel)
    if volume.label_type == LabelType.NONE:
        volume.label_type = LabelType.PARTIAL
        update_fields.append("label_type")
    if update_fields:
        volume.save(update_fields=update_fields)


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


# --- Role-based view/edit access -------------------------------------------

def can_edit_task(user, task) -> bool:
    """May ``user`` *annotate* ``task``? Managers, or the assigned annotator.

    Requesters (Institutions) can never edit — enforced here so the API and the
    provider launch info agree with the UI.
    """
    from accounts.roles import is_annotator, is_manager

    if is_manager(user):
        return True
    uid = getattr(user, "id", None)
    return is_annotator(user) and task.assigned_to_id == uid


def can_view_task(user, task) -> bool:
    """May ``user`` *view* ``task``? Editors, the assignee, or the project owner.

    Requester + annotator both look at the same underlying task labels here, so
    progress monitoring reads one shared source of truth.
    """
    from accounts.roles import is_manager

    if is_manager(user) or can_edit_task(user, task):
        return True
    uid = getattr(user, "id", None)
    return task.assigned_to_id == uid or task.project.created_by_id == uid


def can_view_volume(user, volume) -> bool:
    """May ``user`` view a whole volume? Managers, the project owner, or an
    annotator with a task on it."""
    from accounts.roles import is_manager

    if is_manager(user):
        return True
    uid = getattr(user, "id", None)
    if volume.project.created_by_id == uid:
        return True
    return volume.tasks.filter(assigned_to_id=uid).exists()


# --- Provider-backed task helpers ------------------------------------------

def get_task_proofreading_info(task: AnnotationTask, user=None) -> dict:
    """Return launch info + a download descriptor for a task's proofreading.

    Delegates to the configured proofreading provider. When ``user`` is given
    and cannot edit the task, the launch is **downgraded to view-only** server
    side (``editable=False``) so a requester can never open an edit session even
    if the provider advertises one.
    """
    from .proofreading.registry import get_proofreading_provider

    provider = get_proofreading_provider()
    info = provider.get_launch_info(task).to_dict()
    info["provider"] = provider.name
    info["download"] = provider.prepare_download(task)

    if user is not None and not can_edit_task(user, task):
        info["editable"] = False
        if info["mode"] == "edit":
            from .visualization.registry import get_visualization_provider

            info["mode"] = "view"
            info["url"] = get_visualization_provider().get_view_url(task)
            info["message"] = (
                "View-only: you do not have edit access to this task."
            )
    return info


def get_task_download_descriptor(task: AnnotationTask) -> dict:
    """Return the descriptor an annotator downloads to work on a task locally."""
    from .proofreading.registry import get_proofreading_provider

    return get_proofreading_provider().prepare_download(task)


def get_visualization_state(volume_or_task) -> dict:
    """Return the viewer URL + state for a volume or task."""
    from .visualization.registry import get_visualization_provider

    provider = get_visualization_provider()
    state = provider.get_view_state(volume_or_task)
    state["url"] = provider.get_view_url(volume_or_task)
    return state


# --- Fork-aware SAM2 tracking (persistence) --------------------------------
#
# Everything below writes only the *working* label copy
# (``label_paths.working_label_rel_path`` — nested under
# ``labels/<project>/<dataset>/`` so the on-disk layout matches the project →
# dataset → volume hierarchy the frontend shows). It never touches
# ``volume.label_path``/``label_file`` (the *official*, approved label) —
# that only changes in ``approve_submission``, once a manager approves an
# in-app submission. Before that point, the working copy is purely a staging
# area: the annotator (or a manager editing directly) can paint/track freely
# without affecting what any other viewer sees as "the" label.

def _load_or_init_label(volume, shape):
    """Load a volume's working instance-label array, or start it empty."""
    import numpy as np

    from .visualization.slice_io import resolve_path

    if volume.label_location:
        path = resolve_path(volume.label_location)
        if path.exists():
            import tifffile

            arr = np.asarray(tifffile.imread(str(path)))
            if arr.shape == tuple(shape):
                return arr.astype(np.int32)
    return np.zeros(shape, dtype=np.int32)


def _save_label_volume(volume, label_mask) -> str:
    """Write the working instance labels under MITO_DATA_ROOT; return rel path.

    Always writes to the app-owned working-copy path
    (:func:`annotation.label_paths.working_label_rel_path`) — **never** back
    onto whatever ``volume.label_location`` currently resolves to. That
    location can be a file registered *by reference* (a path into someone
    else's data, e.g. an externally produced prediction/consensus volume)
    which this app does not own and must not mutate in place, or it can be
    the volume's own *official* (approved) label, which must not change
    until a manager approves the new submission (see ``approve_submission``).
    The first in-app edit "forks" a mutable working copy here;
    :func:`_load_or_init_label` seeds that copy from the current official
    label the first time it's read, so nothing is lost — it's just staged,
    not yet promoted.
    """
    import numpy as np
    import tifffile

    from .label_paths import working_label_rel_path
    from .visualization.slice_io import resolve_path

    rel = working_label_rel_path(volume)
    path = resolve_path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(str(path), label_mask.astype(np.uint16))
    from .visualization import slice_io

    slice_io.clear_caches()  # invalidate cached slices for the changed file
    return rel


def _repoint_label(volume, rel: str) -> list[str]:
    """Make ``volume.label_location`` resolve to ``rel`` from now on — i.e.
    promote it to the volume's *official* label. Called only from
    ``approve_submission``, once a manager approves an in-app submission;
    never from the paint/track paths (those only ever touch the working
    copy — see the module note above).

    ``label_location`` prefers ``label_file`` over ``label_path`` (see the
    model), so if an uploaded ``label_file`` is still set it must be cleared
    here too — otherwise every future read would keep resolving back to
    whatever it pointed at *before* this promotion and silently ignore it.
    """
    update_fields = []
    if volume.label_path != rel:
        volume.label_path = rel
        update_fields.append("label_path")
    if volume.label_file:
        volume.label_file = None
        update_fields.append("label_file")
    return update_fields


def track_task_fork(task: AnnotationTask, seeds_by_z, *, z_range=None) -> dict:
    """Run fork-aware SAM2 tracking for one mito on ``task`` and persist it.

    ``seeds_by_z`` maps ``z -> 2D bool mask``. Forks are split into temporary
    branch tracks, propagated, then auto-merged into one instance (see
    :func:`annotation.tracking.services.run_branch_tracking`). The merged
    label volume is written to the volume's *working* copy only (see the
    module note above) — it does not become the volume's official label
    until a submission referencing it is approved. Group membership is
    recorded in ``volume.metadata['tracking_groups']`` for audit / undo /
    re-run regardless (that's bookkeeping, not the label pixels themselves).
    """
    import numpy as np

    from .tracking.services import run_branch_tracking
    from .visualization.slice_io import _open_volume, resolve_path

    volume = task.volume
    if not volume.image_location:
        raise ValueError("Volume has no image to track on.")

    image = np.asarray(_open_volume(resolve_path(volume.image_location)))
    label_mask = _load_or_init_label(volume, image.shape)

    if z_range is None:
        z_range = (task.z_start, max(task.z_start, task.z_end - 1))

    result = run_branch_tracking(
        image=image, volume_mask=label_mask, seeds=seeds_by_z, z_range=z_range
    )

    _save_label_volume(volume, label_mask)
    groups = list((volume.metadata or {}).get("tracking_groups", []))
    if result.get("group"):
        groups.append(result["group"])
    volume.metadata = {**(volume.metadata or {}), "tracking_groups": groups}
    volume.save(update_fields=["metadata"])

    # Lifecycle: the propagated instance is new-to-review PROPOSED/TRACKING
    # if this is the first time it's tracked, else just marked EDITED (its
    # shape changed again) — mirrors the AI/WATERSHED "automated result
    # needs a human look" convention (see set_label_slice_ids's docstring).
    from .cellable_port.label_state import LabelOrigin

    final_id = result.get("final_id")
    if final_id:
        store, meta_path = _load_label_metadata_store(volume)
        if str(final_id) in store:
            store.mark_edited(final_id, default_origin=LabelOrigin.TRACKING)
        else:
            store.create_proposed(final_id, LabelOrigin.TRACKING)
        _save_label_metadata_store(store, meta_path)

    return result


# --- Label-id read/write (in-app brush/eraser editor) -----------------------
#
# This is the hot path — called on every slice navigation and every painted
# stroke — so unlike track_task_fork above (rare, needs a full in-memory
# array for its algorithm) it must never read or write more than the one
# touched slice. Measured cost of getting this wrong on a real-sized label
# volume: ~8.75s per stroke (full imread + full imwrite). Fixed cost with a
# writable memmap, touching one plane: ~0.015s.

def _writable_label(volume, shape):
    """A writable memmap over the volume's *working* label file, seeding it
    from the current official label (or zeros) the first time it's
    touched. Returns ``(memmap, owned_rel_path)``."""
    import numpy as np

    from .label_paths import working_label_rel_path
    from .visualization.slice_io import open_label_volume_writable, resolve_path

    owned_rel = working_label_rel_path(volume)
    owned_path = resolve_path(owned_rel)

    if not owned_path.exists():
        seed = None
        if volume.label_location:
            src = resolve_path(volume.label_location)
            if src.exists() and src != owned_path:
                import tifffile

                arr = np.asarray(tifffile.imread(str(src)))
                if arr.shape == tuple(shape):
                    seed = arr.astype(np.uint16)
        if seed is None:
            seed = np.zeros(shape, dtype=np.uint16)
        import tifffile

        owned_path.parent.mkdir(parents=True, exist_ok=True)
        tifffile.imwrite(str(owned_path), seed)  # one-time seed cost only

        from .visualization import slice_io

        # We already have the seed array in memory — cache its max now
        # rather than making the next caller re-scan the whole memmap for it.
        slice_io.set_label_max_id(owned_path, int(seed.max()) if seed.size else 0)

    return open_label_volume_writable(owned_path, shape), owned_rel


def _load_label_metadata_store(volume):
    """Load (or start empty) the per-label lifecycle-state sidecar for
    ``volume``'s working copy. Returns ``(store, path_str)``."""
    from .cellable_port.label_state import LabelMetadataStore
    from .label_paths import working_label_metadata_rel_path
    from .visualization.slice_io import resolve_path

    path = resolve_path(working_label_metadata_rel_path(volume))
    store = LabelMetadataStore()
    store.load(str(path))
    return store, str(path)


def _save_label_metadata_store(store, path_str: str) -> None:
    import os

    os.makedirs(os.path.dirname(path_str), exist_ok=True)
    store.save(path_str)


def get_label_slice_ids(volume, axis: str, index: int) -> dict:
    """Raw instance ids for one label slice, RLE-encoded for the editor."""
    import numpy as np

    from .visualization.slice_io import AXES, _open_volume, encode_label_rle, resolve_path

    if not volume.image_location:
        raise ValueError("Volume has no image.")
    image = _open_volume(resolve_path(volume.image_location))
    mm, _ = _writable_label(volume, image.shape)
    axis_i = AXES[axis]
    n = mm.shape[axis_i]
    idx = max(0, min(int(index), n - 1))
    if axis == "z":
        sl = np.asarray(mm[idx])
    elif axis == "y":
        sl = np.asarray(mm[:, idx, :])
    else:
        sl = np.asarray(mm[:, :, idx])
    return {"shape": list(sl.shape), "runs": encode_label_rle(sl)}


def set_label_slice_ids(volume, axis: str, index: int, shape, runs, *, origin: str = "manual") -> int:
    """Write one label slice's raw instance ids (from the editor) and persist.

    Touches only the written slice's pages on disk (see the module note
    above) — returns the max instance id now present in the whole volume, so
    the client can offer the next "new instance" id without a second round
    trip (a cheap ``mm.max()`` over an already-open memmap, not a fresh read).

    This only ever touches the *working* copy — never ``volume.label_path``/
    ``label_file``/``label_type`` (the official, approved label). Those only
    change in ``approve_submission``, once a manager approves a submission
    referencing this working copy.

    **Label lifecycle tracking** (``cellable_port/label_state.py``): diffs
    the slice's previous content against ``runs`` and updates the per-label
    state sidecar for every instance id whose pixels actually changed on
    this slice (added, removed, or repainted) — never for ids merely present
    but untouched, since a commit always resends the *whole* slice, not just
    a delta. ``origin`` (``"manual"`` — brush/erase/box-erase — or ``"ai"``
    — a committed Point/Box/Boundary preview) only matters for an id that
    doesn't exist in the store *yet*: a brand-new manual id starts EDITED
    (a human just drew it), a brand-new AI id starts PROPOSED with a
    single-slice snapshot recorded (so it can be reverted) — matching
    Cellable's ``get_or_create``/``_registerAutoSegmentationLabels``. An id
    that already has tracked state is always marked EDITED on further
    changes, regardless of ``origin`` or its prior state (including
    VERIFIED — Cellable's ``mark_edited`` re-edits a verified label back to
    EDITED too).
    """
    import numpy as np

    from .cellable_port.label_state import LabelOrigin
    from .visualization.slice_io import AXES, _open_volume, decode_label_rle, encode_label_rle, resolve_path

    if not volume.image_location:
        raise ValueError("Volume has no image.")
    image = _open_volume(resolve_path(volume.image_location))
    mm, owned_rel = _writable_label(volume, image.shape)
    axis_i = AXES[axis]
    n = mm.shape[axis_i]
    idx = max(0, min(int(index), n - 1))
    sl = decode_label_rle(runs, tuple(shape)).astype(mm.dtype)

    if axis == "z":
        old_sl = np.asarray(mm[idx]).copy()
        mm[idx] = sl
    elif axis == "y":
        old_sl = np.asarray(mm[:, idx, :]).copy()
        mm[:, idx, :] = sl
    else:
        old_sl = np.asarray(mm[:, :, idx]).copy()
        mm[:, :, idx] = sl
    mm.flush()

    from .visualization import slice_io

    max_id = slice_io.bump_label_max_id(resolve_path(owned_rel), mm, int(sl.max()))
    slice_io.invalidate_read_caches()

    changed = old_sl != sl
    if changed.any():
        touched_ids = (set(np.unique(old_sl[changed]).tolist()) | set(np.unique(sl[changed]).tolist())) - {0}
        if touched_ids:
            store, meta_path = _load_label_metadata_store(volume)
            ai_origin = LabelOrigin.AI if origin == "ai" else LabelOrigin.MANUAL
            for label_id in touched_ids:
                if str(label_id) in store:
                    store.mark_edited(label_id, default_origin=ai_origin)
                elif origin == "ai":
                    footprint = (sl == label_id).astype(np.int32)
                    store.create_proposed(
                        label_id,
                        LabelOrigin.AI,
                        snapshot_z=int(index) if axis == "z" else None,
                        snapshot_shape=tuple(shape),
                        snapshot_rle=encode_label_rle(footprint),
                    )
                else:
                    store.get_or_create(label_id, origin=LabelOrigin.MANUAL)
            _save_label_metadata_store(store, meta_path)

    return max_id


def get_label_max_id(volume) -> int:
    """Highest instance id currently in the volume's *working* label copy, or 0.

    Bootstraps the editor's "next new instance id" — must read the working
    copy (what the editor actually paints into), not ``label_location`` (the
    official, approved label, which can lag behind or be entirely empty
    while a task is still being annotated).

    Cached per file after the first call (see ``slice_io.label_max_id``) —
    an O(volume size) scan is fine once, not on every editor page load.
    """
    from .label_paths import working_label_rel_path
    from .visualization.slice_io import _open_volume, label_max_id, resolve_path

    path = resolve_path(working_label_rel_path(volume))
    if not path.exists():
        return 0
    arr = _open_volume(path)
    return label_max_id(path, arr)


# --- Cellable-ported interactive AI tools (Point/Box/Boundary mask) --------
#
# Read-only "preview a candidate mask" operations — unlike tracking/watershed
# below, these never write to the working label copy themselves. The client
# merges the returned mask into its already-loaded slice locally (same as a
# brush stroke) and commits through the existing ``set_label_slice_ids`` path
# above, so no new persistence code is needed here. See
# ``cellable_port/ai/efficient_sam.py`` (ported from Cellable's
# ``labelme/ai/efficient_sam.py``) for the model itself.

def _ai_embedding_cache_path(volume, axis, index):
    """Resolve the on-disk embedding-cache path for one (volume, axis,
    index) under the currently-configured EfficientSAM variant — see
    ``cellable_port/ai/embed_cache.py`` for the key/invalidation design.
    Returns ``None`` if there's no image to key off of."""
    from django.conf import settings as dj_settings

    from .cellable_port.ai import embed_cache
    from .visualization.slice_io import resolve_path

    if not volume.image_location:
        return None
    img_path = resolve_path(volume.image_location)
    try:
        mtime = img_path.stat().st_mtime
    except OSError:
        mtime = 0.0
    variant = getattr(dj_settings, "MITO_EFFICIENT_SAM_VARIANT", "vits")
    return embed_cache.cache_path_for(volume.id, axis, index, variant, mtime)


def predict_ai_mask(task, axis, index, mode, *, points=None, point_labels=None, box=None) -> dict:
    """Run the ported EfficientSAM model on one image slice.

    ``mode`` is ``"points"`` (Point Mask tool), ``"box"`` (Box Mask tool), or
    ``"boundary"`` (Boundary tool — the same points-mask prediction, then
    turned into a ring via erode/dilate, ported from Cellable's
    ``Canvas._finaliseImpl`` ai_boundary branch). Returns a boolean mask as
    ``{"shape": [h, w], "runs": [[0/1, count], ...]}`` — reusing
    :func:`annotation.visualization.slice_io.encode_label_rle` since a
    boolean mask is just a label slice with two possible values.

    The image fed to the model is normalized with
    :func:`cellable_port.ai.normalize.normalize_for_ai` (Cellable's own
    ``normalizeImg``), **not** ``slice_io.display_range`` — see that
    module's docstring for why a display-stable, whole-volume stretch and
    the per-slice non-zero-percentile stretch Cellable actually feeds its
    model are two different things, and conflating them was a real source
    of point/box mask divergence from local Cellable
    (`progress/history/21-cellable-parity-followups.md`). Brightness/
    contrast are **never** part of this — those are client-side CSS filters
    on the display image only (`progress/history/23-cellable-parity-ort-
    and-prompt-ux.md`): baking them into the AI input would make prediction
    quality depend on wherever the user last left those sliders, which is
    strictly worse than Cellable's own behavior, not "more faithful" to it.

    The embedding this computes is shared with :func:`warm_ai_embedding`
    via the same on-disk cache (``_ai_embedding_cache_path`` /
    ``cellable_port/ai/embed_cache.py``) — a slice warmed ahead of time (on
    slice-open or AI-tool entry) makes this call decoder-only.
    """
    import numpy as np

    from .cellable_port.ai.normalize import normalize_for_ai
    from .cellable_port.ai.registry import get_efficient_sam
    from .visualization.slice_io import AXES, encode_label_rle, read_slice

    volume = task.volume
    if axis not in AXES:
        raise ValueError(f"Unknown axis '{axis}'. Use one of {list(AXES)}.")
    if not volume.image_location:
        raise ValueError("Volume has no image.")

    raw = read_slice(volume.image_location, axis, index)
    image = normalize_for_ai(raw)
    cache_path = _ai_embedding_cache_path(volume, axis, index)

    model = get_efficient_sam()  # raises AiUnavailable if not installed/configured
    if mode == "points":
        mask = model.predict_mask_from_points(image, points, point_labels, disk_path=cache_path)
    elif mode == "box":
        mask = model.predict_mask_from_box(image, box, disk_path=cache_path)
    elif mode == "boundary":
        import scipy.ndimage as ndi

        full = model.predict_mask_from_points(image, points, point_labels, disk_path=cache_path)
        if not full.any():
            mask = full
        else:
            eroded = ndi.binary_erosion(full)
            dilated = ndi.binary_dilation(full, iterations=3)
            mask = dilated ^ eroded
    else:
        raise ValueError(f"Unknown predict mode '{mode}'.")

    return {"shape": list(mask.shape), "runs": encode_label_rle(mask.astype(np.int32))}


def warm_ai_embedding(task, axis, index) -> bool:
    """Pre-compute (and cache, in-process + on-disk) the EfficientSAM
    embedding for one slice, without predicting anything — called when the
    Annotate slice changes or an AI tool is entered, so the *first* actual
    click only has to run the (fast) decoder. Mirrors the intent of
    Cellable's background embedding thread (`app.py`'s
    ``_compute_and_cache_image_embedding``), adapted to a stateless request
    instead of a long-lived Qt session — see ``EfficientSam.warm``.

    Returns ``True`` if it ran, ``False`` if there's simply no image at this
    slice (not an error). Raises :class:`AiUnavailable` the same way
    :func:`predict_ai_mask` does if the model isn't installed/configured —
    callers should treat that as "nothing to warm," not a hard failure.
    """
    from .cellable_port.ai.normalize import normalize_for_ai
    from .cellable_port.ai.registry import get_efficient_sam
    from .visualization.slice_io import AXES, read_slice

    volume = task.volume
    if axis not in AXES or not volume.image_location:
        return False
    raw = read_slice(volume.image_location, axis, index)
    image = normalize_for_ai(raw)
    cache_path = _ai_embedding_cache_path(volume, axis, index)
    model = get_efficient_sam()
    model.warm(image, disk_path=cache_path)
    return True


# --- Cellable-ported 3D watershed (Seeds tool) ------------------------------

def run_watershed_task(task, target_label: int, seeds_zyx, *, padding: int = 5) -> dict:
    """Split ``target_label`` via 3D watershed seeded at ``seeds_zyx``
    (``[(z, y, x), ...]``), persisting the result to the volume's *working*
    label copy — same whole-volume read/mutate/write shape as
    :func:`track_task_fork` above (rare, user-triggered, needs real 3D array
    semantics), and subject to the same staging rule: this never touches
    ``volume.label_path``/``label_file``. See
    ``cellable_port/watershed.py`` (ported from Cellable's
    ``apply_3d_watershed``) for the segmentation itself.

    **Reads the working copy, not the official label** — unlike
    ``track_task_fork``'s deliberate "start tracking from the last-approved
    state" behavior (see that function's docstring), Seeds/watershed exists
    to refine an instance the annotator is actively painting *this task*, so
    it must see already-painted-but-not-yet-submitted pixels. Using
    ``_load_or_init_label`` (official-label fallback) here would silently
    ignore any brush work done since the last approval — wrong for this
    tool, since the whole point is "split the blob I just painted."
    """
    import numpy as np
    import tifffile

    from .cellable_port.watershed import WatershedError, run_watershed_3d
    from .label_paths import working_label_rel_path
    from .visualization.slice_io import resolve_path

    volume = task.volume
    working_path = resolve_path(working_label_rel_path(volume))
    if not working_path.exists():
        raise ValueError("Nothing has been painted for this volume yet.")
    label_mask = np.asarray(tifffile.imread(str(working_path))).astype(np.int32)
    try:
        result = run_watershed_3d(label_mask, target_label, seeds_zyx, padding=padding)
    except WatershedError as exc:
        raise ValueError(str(exc)) from exc
    _save_label_volume(volume, label_mask)

    # Lifecycle: the target label's shape just changed (mark EDITED); every
    # newly-split-off id is registered PROPOSED/WATERSHED with **no**
    # snapshot — matches Cellable's own
    # ``_registerAutoSegmentationLabels(..., store_snapshots=False)`` call
    # for watershed output (a multi-region split isn't a single easily
    # revertible "before" state the way one AI-mask commit is).
    from .cellable_port.label_state import LabelOrigin

    store, meta_path = _load_label_metadata_store(volume)
    store.mark_edited(result["target_label"], default_origin=LabelOrigin.WATERSHED)
    for new_id in result["new_label_ids"]:
        store.create_proposed(new_id, LabelOrigin.WATERSHED)
    _save_label_metadata_store(store, meta_path)

    return result


# --- Labels panel ("All" scope) + 3D labels preview -------------------------

def get_labels_summary(volume) -> dict:
    """Per-instance-id voxel count + first/last z + lifecycle state across
    the volume's whole *working* label copy — backs the Labels panel's
    "All labels" scope (search across the whole volume, not just the
    current slice), jump-to-slice, and the Filters Options surface (Show
    state filter, Hide Verified, sort by state, state legend counts). See
    ``cellable_port/labels_3d.py`` for the voxel-count/z-range half (cached,
    since it's an O(volume) scan) and ``cellable_port/label_state.py`` for
    the lifecycle-state half (the JSON sidecar, cheap to load every call).

    An id with no tracked metadata (e.g. pre-existing real data forked from
    an externally-produced official label, never explicitly touched by any
    of this app's own AI/watershed/tracking/paint paths) defaults to
    ``state="proposed", origin="unknown"`` — the same safe "needs a human
    look" default Cellable's own ``LabelMetadata`` falls back to.
    """
    from .cellable_port.label_state import LabelState
    from .cellable_port.labels_3d import label_summary
    from .label_paths import working_label_rel_path
    from .visualization.slice_io import resolve_path

    path = resolve_path(working_label_rel_path(volume))
    summary = label_summary(path)
    store, _ = _load_label_metadata_store(volume)

    stats = {"total": 0, "proposed": 0, "edited": 0, "verified": 0}
    rows = []
    for row in summary["labels"]:
        meta = store.get(row["id"])
        state = meta.state.value if meta else LabelState.PROPOSED.value
        origin = meta.origin.value if meta else "unknown"
        stats["total"] += 1
        stats[state] += 1
        rows.append(
            {
                **row,
                "state": state,
                "origin": origin,
                "verified_at": meta.verified_at if meta else "",
                "can_revert": bool(meta and meta.has_snapshot()),
            }
        )
    return {"labels": rows, "stats": stats}


def set_label_lifecycle_action(volume, label_id: int, action: str) -> dict:
    """Apply a Cellable-parity lifecycle action to one label: ``"verify"``,
    ``"unverify"`` (VERIFIED -> EDITED), ``"revert"`` (restore the single-
    slice snapshot recorded when an AI-mask-created label was proposed —
    only available when ``can_revert`` was true in :func:`get_labels_summary`),
    or ``"reject"`` (delete every voxel of this label from the working copy
    and drop its metadata). Ported from Cellable's ``verifyLabel``/
    ``unverifyLabel``/``revertLabelToProposed``/``rejectLabel``
    (``app.py``) — the confirm-before-destructive-action UI lives in the
    frontend (per ``progress/history/04-incident-data-safety.md``'s "no
    casual one-click destructive action" rule), not here.
    """
    import numpy as np

    from .label_paths import working_label_rel_path
    from .visualization import slice_io
    from .visualization.slice_io import AXES, _open_volume, decode_label_rle, resolve_path

    store, meta_path = _load_label_metadata_store(volume)
    label_int = int(label_id)

    if action == "verify":
        meta = store.verify(label_int)
    elif action == "unverify":
        meta = store.unverify(label_int)
        if meta is None:
            raise ValueError(f"Label {label_int} is not currently verified.")
    elif action in ("revert", "reject"):
        if action == "revert" and not store.can_revert(label_int):
            raise ValueError(f"Label {label_int} has no proposed snapshot to revert to.")
        if not volume.image_location:
            raise ValueError("Volume has no image.")
        image = _open_volume(resolve_path(volume.image_location))
        mm, owned_rel = _writable_label(volume, image.shape)
        mm[mm == label_int] = 0
        if action == "revert":
            meta = store.get(label_int)
            snap = decode_label_rle(meta.snapshot_rle, tuple(meta.snapshot_shape))
            z = meta.snapshot_z
            axis_i = AXES["z"]
            n = mm.shape[axis_i]
            idx = max(0, min(int(z), n - 1))
            current = np.asarray(mm[idx])
            current[snap > 0] = label_int
            mm[idx] = current
            store.revert(label_int)
        else:
            store.remove(label_int)
            meta = None
        mm.flush()
        slice_io.invalidate_read_caches()
    else:
        raise ValueError(f"Unknown lifecycle action '{action}'.")

    _save_label_metadata_store(store, meta_path)
    return {
        "label_id": label_int,
        "action": action,
        "state": meta.state.value if meta else None,
        "removed": meta is None,
    }


def get_labels_3d_preview(volume, label_ids: list[int]) -> dict:
    """Downsampled per-label voxel grids for the 3D labels panel. See
    ``cellable_port/labels_3d.py`` for why this is a block-max-pooled preview
    grid rather than a true iso-surface mesh."""
    from .cellable_port.labels_3d import labels_3d_preview
    from .label_paths import working_label_rel_path
    from .visualization.slice_io import resolve_path

    path = resolve_path(working_label_rel_path(volume))
    return labels_3d_preview(path, label_ids)


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
