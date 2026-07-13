"""Shared helpers for the developer data-management commands.

These build and tear down a *standard* mock dataset used during local
development. They are deterministic and idempotent where practical, and are the
single source of truth for what "dev data" means, so ``seed_dev`` and
``clear_dev_data`` stay in agreement.

Nothing here runs automatically — it is only invoked by the management commands
in ``core/management/commands/``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import AnnotatorProfile, Institution, UserProfile
from annotation.models import AnnotationSubmission, AnnotationTask, ReviewRecord
from annotation.services import assign_task_to_annotator, submit_annotation
from core.choices import UserRole
from projects.models import Project
from volumes.models import Volume
from volumes.services import create_tasks_from_volume, register_dataset

User = get_user_model()

# Standard demo password for every seeded account.
DEMO_PASSWORD = "demo12345"

# Sub-directory of MITO_DATA_ROOT that holds the mock input volumes. Kept
# separate so ``clear_dev_data --files`` can remove it without touching other
# data under the root.
MOCK_DIRNAME = "dev_mock"

# username -> role for the standard accounts.
STANDARD_ACCOUNTS = {
    "manager": UserRole.MANAGER,
    "alice": UserRole.ANNOTATOR,
    "bob": UserRole.ANNOTATOR,
    "lab_requester": UserRole.REQUESTER,
}

MOCK_CHUNKS = ["cortex_crop_1.tif", "cortex_crop_2.tif", "cortex_crop_3.tif"]

STANDARD_METADATA = {
    "organism": "Mus musculus",
    "tissue": "Cerebral cortex",
    "cell_type": "Neuron",
    "imaging_modality": "FIB-SEM",
    "imaging_instrument": "Zeiss Crossbeam",
    "sample_condition": "Chemically fixed",
    "dataset_source": "Demo lab",
    "description": "Standard mock dataset for local development.",
}


def _mock_dir() -> Path:
    return Path(settings.MITO_DATA_ROOT) / MOCK_DIRNAME


def _write_mock_volumes(log=print) -> Path:
    """Create small real TIFF volumes so shape auto-detection has something to read."""
    import numpy as np
    import tifffile

    directory = _mock_dir()
    directory.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(MOCK_CHUNKS):
        path = directory / name
        if not path.exists():
            # Slightly different shapes so the data looks realistic.
            tifffile.imwrite(str(path), np.zeros((48, 128, 96 + i * 8), dtype=np.uint8))
    log(f"  wrote {len(MOCK_CHUNKS)} mock TIFF volume(s) to {directory}")
    return directory


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
    if role == UserRole.REQUESTER:
        profile.institution_name = "Demo Lab"
    profile.save()

    if role == UserRole.ANNOTATOR:
        AnnotatorProfile.objects.get_or_create(
            user=user, defaults={"is_active_annotator": True, "max_active_tasks": 10}
        )
    log(f"  {'created' if created else 'updated'} {role} '{username}'")
    return user


def seed_standard_data(log=print) -> dict:
    """Create the standard mock dataset. Safe to run repeatedly."""
    log("Seeding standard mock data…")

    users = {
        name: _ensure_account(name, role, log)
        for name, role in STANDARD_ACCOUNTS.items()
    }
    manager = users["manager"]
    requester = users["lab_requester"]

    directory = _write_mock_volumes(log)

    # Requester registers the dataset (dataset -> project, chunks -> volumes).
    project, volumes = register_dataset(
        created_by=requester,
        dataset="DemoCortex",
        volume="cortex_vol_01",
        hpc_directory=str(directory),
        files=[
            {"name": name, "chunk_id": f"crop-{i + 1}"}
            for i, name in enumerate(MOCK_CHUNKS)
        ],
        metadata=STANDARD_METADATA,
    )
    log(f"  registered dataset '{project.dataset}' with {len(volumes)} chunk(s)")

    # Manager splits the first chunk into frame-based tasks and assigns two.
    tasks = create_tasks_from_volume(volumes[0], z_step=16)
    log(f"  split '{volumes[0].name}' into {len(tasks)} task(s)")
    if tasks:
        assign_task_to_annotator(tasks[0], annotator=users["alice"])
    if len(tasks) > 1:
        assign_task_to_annotator(tasks[1], annotator=users["bob"])
    log("  assigned tasks to alice and bob")

    # Alice submits her task so the manager dashboard has something to review.
    if tasks:
        label = SimpleUploadedFile(
            "crop-1_label.tif", b"II*\x00mock-label", content_type="image/tiff"
        )
        submit_annotation(
            task=tasks[0], annotator=users["alice"], label_file=label, notes="demo"
        )
        log("  alice submitted a label (awaiting review)")

    return {
        "project_id": project.id,
        "volumes": len(volumes),
        "tasks": len(tasks),
        "manager": manager.username,
    }


def clear_dev_data(*, keep_users: bool = False, remove_files: bool = False, log=print) -> dict:
    """Delete development data. Superusers are always preserved.

    Returns a dict of deleted counts.
    """
    log("Clearing development data…")

    # Delete files backing submissions before the rows disappear.
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

    if remove_files:
        directory = _mock_dir()
        if directory.exists():
            shutil.rmtree(directory)
            log(f"  removed mock file directory {directory}")

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
