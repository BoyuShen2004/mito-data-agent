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

import shutil
from pathlib import Path

from django.conf import settings
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


def _clear_data_root() -> int:
    """Delete everything *inside* ``MITO_DATA_ROOT`` (not the directory
    itself, so its permissions/ownership survive a wipe). Returns how many
    top-level entries were removed.

    Safe to do unconditionally: nothing this app doesn't own ever lives
    under this root — registered-by-reference volumes only ever store an
    absolute (or root-relative-but-external) path *elsewhere*; everything
    actually written inside the root (`volumes/`, `submissions/`, and
    per-project/dataset working label copies) is content this app generated
    and can regenerate. There is no dev/prod distinction to worry about
    either — the caller (`clear_dev_data`) is only ever reachable with
    ``DEBUG`` on (`DevResetView`, `clear_dev_data`/`reset_dev` management
    commands).
    """
    root = Path(settings.MITO_DATA_ROOT)
    if not root.is_dir():
        return 0
    removed = 0
    for entry in root.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
        removed += 1
    return removed


def clear_dev_data(*, keep_users: bool = False, log=print) -> dict:
    """Delete development data. Superusers are always preserved.

    Removes projects, volumes, tasks, submissions, reviews, and institutions,
    **and everything the app itself ever wrote under ``MITO_DATA_ROOT``** —
    uploaded image/label/submission files (Django `FileField`s) *and* the
    in-app editor's working label copies (`annotation.label_paths`, written
    directly by path, not through a `FileField`, so they need this — a
    per-`FileField` `.delete()` loop alone would miss them entirely; that was
    a real bug, see `progress/history/17-fix-dev-reset-orphaned-files.md`).
    Registered-*by-reference* volumes only store a path string pointing
    outside `MITO_DATA_ROOT` (someone else's HPC data) — those are never
    touched, only the DB row referencing them. Non-superuser accounts are
    removed too unless ``keep_users`` is set. Returns a dict of deleted counts.
    """
    log("Clearing development data…")

    counts = {
        "reviews": ReviewRecord.objects.all().delete()[0],
        "submissions": AnnotationSubmission.objects.all().delete()[0],
        "tasks": AnnotationTask.objects.all().delete()[0],
        "volumes": Volume.objects.all().delete()[0],
        "projects": Project.objects.all().delete()[0],
        "institutions": Institution.objects.all().delete()[0],
    }

    files_removed = _clear_data_root()
    log(f"  cleared {files_removed} item(s) under MITO_DATA_ROOT")

    # The Django dev server is a long-running process — deleting working
    # label files out from under it without also dropping slice_io's caches
    # leaves a stale *writable* memmap handle open (keyed only by path, not
    # mtime/inode — unlike the read-side volume cache). A later request for
    # the same path (e.g. a volume re-registered after reset landing on the
    # same id, which SQLite rowid reuse makes possible — see
    # `annotation/test_tracking.py`'s setUp comment on the same issue) would
    # then silently read/write the orphaned old file instead of the new one.
    # `track_task_fork`/`_save_label_volume` already clear these caches after
    # a full label rewrite for the same reason; a full data reset is at least
    # as disruptive to what's on disk.
    from annotation.visualization import slice_io

    slice_io.clear_caches()

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
