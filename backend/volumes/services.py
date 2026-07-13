"""Deterministic service functions for volumes and frame-based task splitting."""

from __future__ import annotations

import re
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


# Filename tokens that mark a file as a mask/label vs an image, used to auto-pair
# image + mask volumes that share a common base name in the same directory.
MASK_TOKENS = {
    "mask", "masks", "label", "labels", "seg", "segmentation", "segmentations",
    "gt", "groundtruth", "annotation", "annotations", "ann", "lbl",
}
IMAGE_TOKENS = {
    "image", "images", "img", "im", "raw", "data", "vol", "volume", "em", "grey",
    "gray",
}


def _stem(name: str) -> str:
    """Filename without its supported data extension."""
    ext = matched_data_extension(name)
    return name[: -len(ext)] if ext else name


def _name_tokens(stem: str) -> list[str]:
    return [t for t in re.split(r"[ _\-.]+", stem.lower()) if t]


def _is_mask_name(name: str) -> bool:
    return any(t in MASK_TOKENS for t in _name_tokens(_stem(name)))


def _core_key(name: str, *, is_mask: bool) -> str:
    """The shared identity of a volume with its role marker removed.

    A mask's core drops mask tokens (``cortex1_mask`` -> ``cortex1``); an image's
    core drops image tokens (``cortex1_image`` -> ``cortex1``, ``vol`` -> ``vol``)
    so an image and its mask resolve to the same core and get paired.
    """
    tokens = _name_tokens(_stem(name))
    drop = MASK_TOKENS if is_mask else IMAGE_TOKENS
    kept = [t for t in tokens if t not in drop]
    return "_".join(kept) if kept else _stem(name).lower()


def detect_volume_pairs(filenames: list[str]) -> tuple[list[dict], list[str]]:
    """Group filenames into ``(image, mask)`` pairs plus leftover unpaired files.

    A mask is paired with the image whose core name matches after each side's
    role markers are removed (e.g. ``_image``/``_mask``, ``_raw``/``_seg``, or a
    bare name vs a ``_label`` suffix). Returns ``(pairs, unpaired)`` where each
    pair is ``{"image", "mask", "base"}``.
    """
    images = sorted(n for n in filenames if not _is_mask_name(n))
    masks = sorted(n for n in filenames if _is_mask_name(n))

    images_by_core: dict[str, list[str]] = {}
    for image in images:
        images_by_core.setdefault(_core_key(image, is_mask=False), []).append(image)

    pairs: list[dict] = []
    used_images: set[str] = set()
    used_masks: set[str] = set()
    for mask in masks:
        core = _core_key(mask, is_mask=True)
        candidates = [i for i in images_by_core.get(core, []) if i not in used_images]
        if candidates:
            image = candidates[0]
            used_images.add(image)
            used_masks.add(mask)
            pairs.append({"image": image, "mask": mask, "base": core})

    # Images with no mask and masks with no image are surfaced as unpaired, so
    # nothing silently disappears from the folder listing.
    unpaired = [f for f in images if f not in used_images]
    unpaired += [m for m in masks if m not in used_masks]

    return (
        sorted(pairs, key=lambda p: p["image"].lower()),
        sorted(unpaired, key=str.lower),
    )


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
    pairs, unpaired = detect_volume_pairs([f["name"] for f in files])
    return {
        "directory": _stored_path(directory),
        "files": files,
        "pairs": pairs,
        "unpaired": unpaired,
    }


def register_dataset(
    *,
    created_by,
    dataset: str,
    volume: str,
    hpc_directory: str,
    pairs: list[dict] | None = None,
    files: list[dict] | None = None,
    metadata: dict | None = None,
    project=None,
    annotation_type: str | None = None,
    label_type: str = LabelType.NONE,
    description: str = "",
    reviewed: bool = False,
) -> tuple:
    """Register HPC file references as chunks/crops under a dataset + volume.

    ``dataset`` and ``volume`` are required. Every referenced file must be a
    supported ``.tif``/``.tiff``/``.nii.gz`` file in ``hpc_directory``.

    Registration is flexible about image/mask pairing:

    * ``pairs`` — explicit ``[{image, mask?, chunk_id?}, ...]`` entries. Each
      becomes one volume; when ``mask`` is given it is stored as the label. This
      lets a single image+mask pair be picked out of a folder of other volumes.
    * ``files`` — image-only ``[{path|name, chunk_id?}, ...]`` entries (no masks).
    * neither — the directory is auto-scanned and **all detected image+mask
      pairs plus any unpaired images** are registered.

    ``label_type`` is applied to volumes that get a mask (defaulting to
    ``prediction`` so they become proofreading tasks). Returns ``(project,
    [Volume, ...])``; a new project is created unless ``project`` is given.
    """
    from projects.services import create_project

    dataset = (dataset or "").strip()
    volume = (volume or "").strip()
    if not dataset:
        raise DataRegistrationError("A dataset name is required.")
    if not volume:
        raise DataRegistrationError("A volume name is required.")

    directory = resolve_hpc_directory(hpc_directory)

    def _resolve(raw_name: str, kind: str = "file"):
        name = (raw_name or "").strip()
        if not name:
            raise DataRegistrationError(f"A {kind} name is required.")
        base = Path(name).name  # basenames only; no path traversal
        ext = matched_data_extension(base)
        if not ext:
            raise DataRegistrationError(
                f"Unsupported file type: {base}. Only .tif, .tiff and "
                ".nii.gz are accepted."
            )
        candidate = (directory / base).resolve()
        if not candidate.is_file():
            raise DataRegistrationError(f"File not found in directory: {base}")
        return base, candidate, ext

    # Build the normalised list of entries:
    #   (image_base, image_path, image_ext, mask_base|None, mask_path|None, chunk_id)
    entries: list[tuple] = []
    if pairs:
        for item in pairs:
            image_base, image_path, image_ext = _resolve(item.get("image"), "image")
            mask_name = (item.get("mask") or "").strip()
            if mask_name:
                mask_base, mask_path, _ = _resolve(mask_name, "mask")
            else:
                mask_base = mask_path = None
            entries.append(
                (image_base, image_path, image_ext, mask_base, mask_path,
                 item.get("chunk_id", ""))
            )
    elif files:
        for item in files:
            image_base, image_path, image_ext = _resolve(
                item.get("path") or item.get("name"), "image"
            )
            entries.append(
                (image_base, image_path, image_ext, None, None,
                 item.get("chunk_id", ""))
            )
    else:
        scanned = scan_hpc_directory(hpc_directory)
        for pair in scanned["pairs"]:
            image_base, image_path, image_ext = _resolve(pair["image"], "image")
            mask_base, mask_path, _ = _resolve(pair["mask"], "mask")
            entries.append(
                (image_base, image_path, image_ext, mask_base, mask_path, "")
            )
        for name in scanned["unpaired"]:
            image_base, image_path, image_ext = _resolve(name, "image")
            entries.append((image_base, image_path, image_ext, None, None, ""))

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
            reviewed=reviewed,
        )

    # A provided mask implies a real label; default it to a proofreadable type.
    mask_label_type = label_type
    if not mask_label_type or mask_label_type == LabelType.NONE:
        mask_label_type = LabelType.PREDICTION

    created = []
    for image_base, image_path, image_ext, _mask_base, mask_path, chunk_id in entries:
        has_mask = mask_path is not None
        vol = register_volume(
            project=project,
            name=chunk_id or image_base,
            image_path=_stored_path(image_path),
            label_path=_stored_path(mask_path) if has_mask else "",
            label_type=mask_label_type if has_mask else LabelType.NONE,
            file_format=_file_format_for(image_ext),
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
