"""Deterministic service functions for volumes and frame-based task splitting."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings

from core.choices import (
    LABEL_TYPE_TO_TASK_TYPE,
    FileFormat,
    LabelType,
    VolumeStatus,
)
from core.utils import inspect_volume_shape

from .models import Volume

# Only these data-file extensions may be registered for annotation. ``.nii.gz``
# is a compound extension, so extension matching uses ``str.endswith``.
SUPPORTED_DATA_EXTENSIONS = (".tif", ".tiff", ".nii.gz")


class DataRegistrationError(ValueError):
    """Raised when an HPC directory or file fails validation."""


def matched_data_extension(name: str) -> str:
    """Return the supported extension a filename ends with, or ``""``."""
    lower = name.lower()
    for ext in sorted(SUPPORTED_DATA_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(ext):
            return ext
    return ""


def _file_format_for(ext: str) -> str:
    if ext in (".tif", ".tiff"):
        return FileFormat.TIFF
    return FileFormat.OTHER


def resolve_hpc_directory(hpc_directory: str) -> Path:
    """Resolve an HPC directory value (absolute, or relative to the data root).

    Validates that the value is non-empty and points to an existing directory.
    Raises :class:`DataRegistrationError` otherwise.
    """
    raw = (hpc_directory or "").strip()
    if not raw:
        raise DataRegistrationError("An HPC directory is required.")
    path = Path(raw)
    if not path.is_absolute():
        path = Path(settings.MITO_DATA_ROOT) / raw
    path = path.resolve()
    if not path.exists():
        raise DataRegistrationError(f"Directory does not exist: {raw}")
    if not path.is_dir():
        raise DataRegistrationError(f"Not a directory: {raw}")
    return path


def _stored_path(abs_path: Path) -> str:
    """Store a path relative to the data root when possible, else absolute."""
    root = Path(settings.MITO_DATA_ROOT).resolve()
    try:
        return str(abs_path.resolve().relative_to(root))
    except ValueError:
        return str(abs_path.resolve())


def scan_hpc_directory(hpc_directory: str) -> dict:
    """List supported data files directly inside ``hpc_directory``."""
    directory = resolve_hpc_directory(hpc_directory)
    files = []
    for entry in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        if not entry.is_file():
            continue
        ext = matched_data_extension(entry.name)
        if not ext:
            continue
        try:
            size = entry.stat().st_size
        except OSError:
            size = 0
        files.append(
            {
                "name": entry.name,
                "path": _stored_path(entry),
                "extension": ext,
                "size": size,
            }
        )
    return {"directory": _stored_path(directory), "files": files}


def register_dataset(
    *,
    created_by,
    dataset: str,
    volume: str,
    hpc_directory: str,
    files: list[dict] | None = None,
    metadata: dict | None = None,
    project=None,
    annotation_type: str | None = None,
    label_type: str = LabelType.NONE,
    description: str = "",
) -> tuple:
    """Register HPC file references as chunks/crops under a dataset + volume.

    ``dataset`` and ``volume`` are required. Every file must be a supported
    ``.tif``/``.tiff``/``.nii.gz`` file that exists in ``hpc_directory``. When
    ``files`` is omitted, all supported files in the directory are registered.

    Returns ``(project, [Volume, ...])``. When ``project`` is given the chunks
    are attached to it; otherwise a new project is created for the dataset.
    """
    from projects.services import create_project

    dataset = (dataset or "").strip()
    volume = (volume or "").strip()
    if not dataset:
        raise DataRegistrationError("A dataset name is required.")
    if not volume:
        raise DataRegistrationError("A volume name is required.")

    directory = resolve_hpc_directory(hpc_directory)

    # Resolve the list of files to register (explicit selection or full scan).
    if files:
        entries = []
        for item in files:
            raw_name = (item.get("path") or item.get("name") or "").strip()
            if not raw_name:
                raise DataRegistrationError("Each file needs a name or path.")
            base = Path(raw_name).name  # basenames only; no traversal
            candidate = (directory / base).resolve()
            ext = matched_data_extension(base)
            if not ext:
                raise DataRegistrationError(
                    f"Unsupported file type: {base}. Only .tif, .tiff and "
                    ".nii.gz are accepted."
                )
            if not candidate.is_file():
                raise DataRegistrationError(
                    f"File not found in directory: {base}"
                )
            entries.append((base, candidate, ext, item.get("chunk_id", "")))
    else:
        scanned = scan_hpc_directory(hpc_directory)["files"]
        entries = [
            (f["name"], (directory / f["name"]).resolve(), f["extension"], "")
            for f in scanned
        ]

    if not entries:
        raise DataRegistrationError(
            "No supported files (.tif, .tiff, .nii.gz) found to register."
        )

    if project is None:
        project = create_project(
            title=dataset,
            dataset=dataset,
            created_by=created_by,
            description=description,
            annotation_type=annotation_type,
            metadata=metadata or {},
        )

    created = []
    for base, abs_path, ext, chunk_id in entries:
        vol = register_volume(
            project=project,
            name=chunk_id or base,
            image_path=_stored_path(abs_path),
            label_type=label_type,
            file_format=_file_format_for(ext),
        )
        vol.source_volume = volume
        vol.chunk_id = chunk_id
        vol.save(update_fields=["source_volume", "chunk_id"])
        created.append(vol)

    return project, created


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
                instructions=instructions,
            )
        )
    created = AnnotationTask.objects.bulk_create(tasks)

    volume.status = VolumeStatus.SPLIT
    volume.save(update_fields=["status"])
    return created


# Backwards/forwards-compatible name matching the product spec.
def split_volume_into_tasks(volume, z_step=16, task_type=None):
    return create_tasks_from_volume(volume, z_step=z_step, task_type=task_type)
