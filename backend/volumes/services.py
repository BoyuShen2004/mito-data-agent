"""Deterministic service functions for volumes and frame-based task splitting."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from django.conf import settings

from core.choices import (
    LABEL_TYPE_TO_TASK_TYPE,
    LabelType,
    VolumeStatus,
)
from core.utils import inspect_volume_shape

from .models import Volume


def register_volume(
    *,
    project,
    name: str,
    image_path: str = "",
    image_file=None,
    label_path: str = "",
    label_file=None,
    label_type: str = LabelType.NONE,
    file_format: str | None = None,
    voxel_size=None,
    metadata: dict | None = None,
    autodetect_shape: bool = True,
) -> Volume:
    """Register (or upload) an image volume under a project.

    ``voxel_size`` may be a ``(z, y, x)`` tuple. If ``autodetect_shape`` is set
    and the image is a readable TIFF under ``MITO_DATA_ROOT``, the ``(x, y, z)``
    shape is filled in automatically.
    """
    volume = Volume(
        project=project,
        name=name,
        image_path=image_path or "",
        label_path=label_path or "",
        label_type=label_type,
        metadata=metadata or {},
    )
    if image_file is not None:
        volume.image_file = image_file
    if label_file is not None:
        volume.label_file = label_file
    if file_format is not None:
        volume.file_format = file_format
    if voxel_size is not None:
        volume.voxel_size_z, volume.voxel_size_y, volume.voxel_size_x = voxel_size

    volume.save()

    if autodetect_shape and volume.shape_z is None:
        _try_autodetect_shape(volume)

    return volume


def _try_autodetect_shape(volume: Volume) -> None:
    """Fill shape_x/y/z from the image file if it is a readable TIFF."""
    location = volume.image_location
    if not location:
        return
    # image_file names are relative to MITO_DATA_ROOT; image_path may be
    # absolute or relative to the same root.
    candidate = Path(location)
    if not candidate.is_absolute():
        candidate = Path(settings.MITO_DATA_ROOT) / location
    shape = inspect_volume_shape(candidate)
    if shape is not None:
        x, y, z = shape
        volume.shape_x, volume.shape_y, volume.shape_z = x, y, z
        volume.save(update_fields=["shape_x", "shape_y", "shape_z"])


def update_volume_metadata(volume: Volume, **fields) -> Volume:
    """Update whitelisted volume fields (metadata, shape, voxel size, label)."""
    allowed = {
        "name",
        "label_type",
        "label_path",
        "file_format",
        "shape_x",
        "shape_y",
        "shape_z",
        "voxel_size_x",
        "voxel_size_y",
        "voxel_size_z",
        "status",
    }
    changed = []
    for key, value in fields.items():
        if key == "metadata":
            volume.metadata = {**(volume.metadata or {}), **(value or {})}
            changed.append("metadata")
        elif key in allowed:
            setattr(volume, key, value)
            changed.append(key)
    if changed:
        volume.save(update_fields=changed)
    return volume


def split_volume_by_frames(shape_z: int, z_step: int = 16) -> list[tuple[int, int]]:
    """Pure helper: return ``(z_start, z_end)`` ranges covering ``[0, shape_z)``.

    A volume with ``shape_z=256`` and ``z_step=16`` yields 16 ranges. The last
    range is clamped to ``shape_z`` when it is not an exact multiple.
    """
    if not shape_z or shape_z <= 0:
        raise ValueError("shape_z must be a positive integer")
    if z_step <= 0:
        raise ValueError("z_step must be a positive integer")

    ranges = []
    z = 0
    while z < shape_z:
        z_end = min(z + z_step, shape_z)
        ranges.append((z, z_end))
        z = z_end
    return ranges


def infer_task_type(label_type: str, override: str | None = None) -> str:
    """Infer the task type for a volume's label state (override wins)."""
    if override:
        return override
    return LABEL_TYPE_TO_TASK_TYPE.get(label_type, LABEL_TYPE_TO_TASK_TYPE[LabelType.NONE])


def create_tasks_from_volume(
    volume: Volume,
    *,
    z_step: int = 16,
    payment_amount=0,
    task_type: str | None = None,
    priority: int = 0,
    instructions: str = "",
) -> list:
    """Create frame-based :class:`AnnotationTask` rows spanning the full XY plane.

    Task type is inferred from ``volume.label_type`` unless ``task_type`` is
    given (required override path for ``partial`` labels).
    """
    # Imported here to avoid a circular import at module load time.
    from annotation.models import AnnotationTask

    if not volume.shape_z:
        raise ValueError(
            f"Volume '{volume.name}' has no shape_z; set it before splitting."
        )

    resolved_type = infer_task_type(volume.label_type, task_type)
    y_end = volume.shape_y or 0
    x_end = volume.shape_x or 0
    amount = Decimal(str(payment_amount))

    tasks = []
    for z_start, z_end in split_volume_by_frames(volume.shape_z, z_step):
        tasks.append(
            AnnotationTask(
                project=volume.project,
                volume=volume,
                z_start=z_start,
                z_end=z_end,
                y_start=0,
                y_end=y_end,
                x_start=0,
                x_end=x_end,
                task_type=resolved_type,
                priority=priority,
                payment_amount=amount,
                instructions=instructions,
            )
        )
    created = AnnotationTask.objects.bulk_create(tasks)

    volume.status = VolumeStatus.SPLIT
    volume.save(update_fields=["status"])
    return created


# Backwards/forwards-compatible name matching the product spec.
def split_volume_into_tasks(volume, z_step=16, payment_amount=0, task_type=None):
    return create_tasks_from_volume(
        volume, z_step=z_step, payment_amount=payment_amount, task_type=task_type
    )
