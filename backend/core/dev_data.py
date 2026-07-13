"""Shared helpers for the developer data-management commands.

Seeding creates only **accounts** — one manager and several annotators — and
*no* pre-registered datasets, volumes, or tasks. Any data used during
development is registered manually by developers through the app.

Automated test fixtures are a completely separate concern: the test suite builds
its own throwaway data in temporary directories and never touches these helpers
or the development database.

Nothing here runs automatically — it is only invoked by the management commands
in ``core/management/commands/``.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

from accounts.models import AnnotatorProfile, Institution, UserProfile
from annotation.models import AnnotationSubmission, AnnotationTask, ReviewRecord
from core.choices import UserRole
from projects.models import Project
from volumes.models import Volume

User = get_user_model()

# Standard demo password for every seeded account.
DEMO_PASSWORD = "demo12345"

# The standard development accounts: one manager and four annotators. The
# manager is a superuser, so it survives ``clear_dev_data``. Developers register
# data manually (as the manager, or by signing up a requester through the app).
STANDARD_ACCOUNTS = {
    "manager": UserRole.MANAGER,
    "alice": UserRole.ANNOTATOR,
    "bob": UserRole.ANNOTATOR,
    "carol": UserRole.ANNOTATOR,
    "dave": UserRole.ANNOTATOR,
}


def _ensure_account(username: str, role: str, log=print):
    is_manager = role == UserRole.MANAGER
    user, created = User.objects.get_or_create(
        username=username,
        defaults={"is_staff": is_manager, "is_superuser": is_manager},
    )
    user.set_password(DEMO_PASSWORD)
    user.is_staff = is_manager
    user.is_superuser = is_manager
    user.save()

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.role = role
    profile.save()

    if role == UserRole.ANNOTATOR:
        AnnotatorProfile.objects.get_or_create(
            user=user, defaults={"is_active_annotator": True, "max_active_tasks": 10}
        )
    log(f"  {'created' if created else 'updated'} {role} '{username}'")
    return user


def seed_standard_data(log=print) -> dict:
    """Create the standard development accounts (no data). Safe to run repeatedly."""
    log("Seeding standard development accounts…")
    for name, role in STANDARD_ACCOUNTS.items():
        _ensure_account(name, role, log)

    managers = [n for n, r in STANDARD_ACCOUNTS.items() if r == UserRole.MANAGER]
    annotators = [n for n, r in STANDARD_ACCOUNTS.items() if r == UserRole.ANNOTATOR]
    return {
        "managers": managers,
        "annotators": annotators,
    }


def clear_dev_data(*, keep_users: bool = False, log=print) -> dict:
    """Delete development data. Superusers are always preserved.

    Removes projects, volumes, tasks, submissions, reviews, and institutions
    (plus the files the app itself stored for them). Non-superuser accounts are
    removed too unless ``keep_users`` is set. Returns a dict of deleted counts.
    """
    log("Clearing development data…")

    # Delete files the app stored before the rows that reference them disappear.
    # (Registered volumes only reference external HPC paths, which we never touch.)
    for sub in AnnotationSubmission.objects.all():
        if sub.label_file:
            sub.label_file.delete(save=False)
    for vol in Volume.objects.all():
        for field in (vol.image_file, vol.label_file):
            if field:
                field.delete(save=False)

    counts = {
        "reviews": ReviewRecord.objects.all().delete()[0],
        "submissions": AnnotationSubmission.objects.all().delete()[0],
        "tasks": AnnotationTask.objects.all().delete()[0],
        "volumes": Volume.objects.all().delete()[0],
        "projects": Project.objects.all().delete()[0],
        "institutions": Institution.objects.all().delete()[0],
    }

    if not keep_users:
        # Preserve superusers so admin access survives a wipe.
        qs = User.objects.filter(is_superuser=False)
        counts["users"] = qs.count()
        qs.delete()
    else:
        counts["users"] = 0

    for key, value in counts.items():
        log(f"  deleted {value} {key}")
    return counts


def data_summary() -> dict:
    """Current row counts, for the ``dev_status`` command."""
    return {
        "users": User.objects.count(),
        "superusers": User.objects.filter(is_superuser=True).count(),
        "requesters": UserProfile.objects.filter(role=UserRole.REQUESTER).count(),
        "annotators": UserProfile.objects.filter(role=UserRole.ANNOTATOR).count(),
        "projects": Project.objects.count(),
        "volumes": Volume.objects.count(),
        "tasks": AnnotationTask.objects.count(),
        "submissions": AnnotationSubmission.objects.count(),
        "reviews": ReviewRecord.objects.count(),
    }
