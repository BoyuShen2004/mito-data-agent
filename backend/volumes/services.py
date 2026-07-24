"""Deterministic service functions for volumes and frame-based task splitting."""

from __future__ import annotations

import json
import re
from pathlib import Path

from django.conf import settings

from core.choices import (
    LABEL_TYPE_TO_TASK_TYPE,
    FileFormat,
    LabelType,
    VolumeStatus,
)
from core.utils import inspect_volume_shape, inspect_volume_voxel_size

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


# nnU-Net marks the channel index with a 4-digit suffix on *image* files
# (``case_0000.nii.gz``); the matching label carries no suffix (``case.nii.gz``).
# Stripping it yields the case id both sides share, which is what pairs them.
_CHANNEL_SUFFIX_RE = re.compile(r"_(\d{4})$")


def case_key(name: str) -> str:
    """The case id a file belongs to: its stem minus any channel suffix.

    ``imagesTr/jrc_mus-kidney_crop129_0000.nii.gz`` and
    ``labelsTr/jrc_mus-kidney_crop129.nii.gz`` both yield
    ``jrc_mus-kidney_crop129``, which is what makes them a pair.
    """
    return _CHANNEL_SUFFIX_RE.sub("", _stem(Path(name).name))


def channel_index(name: str) -> int | None:
    """The nnU-Net channel index of a file, or None when it has no suffix."""
    match = _CHANNEL_SUFFIX_RE.search(_stem(Path(name).name))
    return int(match.group(1)) if match else None


def pair_by_case(
    image_names: list[str], mask_names: list[str]
) -> tuple[list[dict], list[str], list[str], list[str]]:
    """Pair images with masks by case id — the cross-directory workhorse.

    Images and masks may live in different directories; only their names are
    considered here. When a case has several channels the lowest one represents
    the volume and the rest are returned as ``extra_channels`` rather than being
    silently dropped.

    Returns ``(pairs, unmatched_images, unmatched_masks, extra_channels)``.
    """
    images_by_case: dict[str, list[str]] = {}
    for name in image_names:
        images_by_case.setdefault(case_key(name), []).append(name)
    masks_by_case: dict[str, list[str]] = {}
    for name in mask_names:
        masks_by_case.setdefault(case_key(name), []).append(name)

    pairs: list[dict] = []
    extra_channels: list[str] = []
    matched_images: set[str] = set()
    matched_masks: set[str] = set()

    for case in sorted(images_by_case):
        channels = sorted(
            images_by_case[case],
            key=lambda n: (channel_index(n) is None, channel_index(n) or 0, n.lower()),
        )
        image, rest = channels[0], channels[1:]
        extra_channels.extend(rest)
        masks = sorted(masks_by_case.get(case, []), key=str.lower)
        if masks:
            pairs.append({"image": image, "mask": masks[0], "case": case})
            matched_images.add(image)
            matched_masks.add(masks[0])

    unmatched_images = sorted(
        (n for n in image_names if n not in matched_images and n not in extra_channels),
        key=str.lower,
    )
    unmatched_masks = sorted(
        (n for n in mask_names if n not in matched_masks), key=str.lower
    )
    return (
        sorted(pairs, key=lambda p: p["case"].lower()),
        unmatched_images,
        unmatched_masks,
        sorted(extra_channels, key=str.lower),
    )


def detect_volume_pairs(filenames: list[str]) -> tuple[list[dict], list[str]]:
    """Group filenames from a *single* directory into pairs plus leftovers.

    Two conventions are supported, tried in order:

    1. nnU-Net in one folder — some files carry a ``_0000`` channel suffix and
       others do not (``vol1_0000.tiff`` + ``vol1.tiff``); the suffixed files are
       the images and the bare ones the masks.
    2. Role tokens in the name (``cortex1_image`` + ``cortex1_mask``).

    Returns ``(pairs, unpaired)`` where each pair is ``{"image", "mask", "base"}``.
    """
    suffixed = [n for n in filenames if channel_index(n) is not None]
    bare = [n for n in filenames if channel_index(n) is None]
    if suffixed and bare:
        pairs, un_images, un_masks, extras = pair_by_case(suffixed, bare)
        return (
            [{"image": p["image"], "mask": p["mask"], "base": p["case"]} for p in pairs],
            sorted(un_images + un_masks + extras, key=str.lower),
        )

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


# --- nnU-Net dataset.json -------------------------------------------------
#
# An nnU-Net dataset root sits one level above imagesTr/labelsTr and carries a
# dataset.json listing `training: [{image, label}]`. That list is authoritative:
# it pairs files without any name guessing, and its descriptive fields save the
# requester retyping metadata that is already recorded.

# Directory-name prefixes that mark a folder's role, and the split they imply.
_SPLIT_SUFFIXES = {"tr": "train", "ts": "test"}


def split_for_directory(name: str) -> str:
    """The nnU-Net split a directory name implies ('train'/'test'), else ''."""
    lowered = name.lower()
    for suffix, split in _SPLIT_SUFFIXES.items():
        if lowered.endswith(suffix) and (
            lowered.startswith("images") or lowered.startswith("labels")
        ):
            return split
    return ""


def _looks_like_mask_dir(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith(("label", "mask", "seg", "gt", "annotation"))


def _looks_like_image_dir(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith(("image", "img", "raw", "em"))


def read_dataset_manifest(directory: Path) -> dict | None:
    """Load ``dataset.json`` from ``directory`` or its parent, if present.

    Returns ``{"path", "pairs", "metadata"}`` where ``pairs`` are
    ``{"image", "mask", "image_dir", "mask_dir"}`` entries taken verbatim from
    the manifest's ``training`` list, or None when there is no readable manifest.
    """
    for candidate in (directory / "dataset.json", directory.parent / "dataset.json"):
        if not candidate.is_file():
            continue
        try:
            raw = json.loads(candidate.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(raw, dict):
            continue

        pairs = []
        for entry in raw.get("training") or []:
            if not isinstance(entry, dict):
                continue
            image, label = entry.get("image"), entry.get("label")
            if not image or not label:
                continue
            pairs.append(
                {
                    "image": Path(image).name,
                    "mask": Path(label).name,
                    "image_dir": Path(image).parent.name,
                    "mask_dir": Path(label).parent.name,
                    "case": case_key(image),
                }
            )

        metadata = {}
        for src, dest in (
            ("description", "description"),
            ("reference", "publication"),
            ("licence", "licence"),
            ("name", "dataset_source"),
        ):
            value = raw.get(src)
            if isinstance(value, str) and value.strip():
                metadata[dest] = value.strip()
        # Class and channel maps are structured, not free text; keep them as-is.
        if isinstance(raw.get("labels"), dict):
            metadata["label_classes"] = raw["labels"]
        if isinstance(raw.get("channel_names"), dict):
            metadata["channel_names"] = raw["channel_names"]

        return {"path": _stored_path(candidate), "pairs": pairs, "metadata": metadata}
    return None


def suggest_sibling_directories(directory: Path) -> dict:
    """Sibling folders that look like image/mask sets, for quick-picking.

    Lets a requester who typed ``.../imagesTr`` choose ``labelsTr`` vs
    ``labelsTr-instance`` (or the Ts split) without hunting for the path.
    """
    images, masks = [], []
    try:
        siblings = sorted(directory.parent.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return {"images": [], "masks": []}

    for entry in siblings:
        if not entry.is_dir():
            continue
        count = sum(1 for f in entry.iterdir() if f.is_file() and matched_data_extension(f.name)) \
            if _looks_like_mask_dir(entry.name) or _looks_like_image_dir(entry.name) else 0
        if not count:
            continue
        item = {
            "name": entry.name,
            "path": _stored_path(entry),
            "count": count,
            "split": split_for_directory(entry.name),
            "current": entry.resolve() == directory.resolve(),
        }
        if _looks_like_mask_dir(entry.name):
            masks.append(item)
        elif _looks_like_image_dir(entry.name):
            images.append(item)
    return {"images": images, "masks": masks}


def _list_data_files(directory: Path) -> list[dict]:
    """Supported data files directly inside ``directory``."""
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
    return files


def scan_data_sources(
    image_directory: str, mask_directory: str = ""
) -> dict:
    """Scan an image directory and an optional mask directory, and pair them.

    Images and masks routinely live in different folders (nnU-Net's
    ``imagesTr``/``labelsTr``), so both are scanned independently and paired by
    case id. When ``mask_directory`` is empty or the same folder, single-folder
    conventions are used instead.

    A ``dataset.json`` beside the directories is authoritative: if it describes
    exactly the two folders being scanned, its ``training`` list supplies the
    pairs and no name matching happens at all.
    """
    image_dir = resolve_hpc_directory(image_directory)
    mask_dir = resolve_hpc_directory(mask_directory) if (mask_directory or "").strip() else None

    image_files = _list_data_files(image_dir)
    image_names = [f["name"] for f in image_files]
    separate = mask_dir is not None and mask_dir != image_dir
    mask_files = _list_data_files(mask_dir) if separate else []
    mask_names = [f["name"] for f in mask_files]

    manifest = read_dataset_manifest(image_dir)
    pairing_source = "filename"
    extra_channels: list[str] = []

    if separate:
        manifest_pairs = _manifest_pairs_for(manifest, image_dir, mask_dir, image_names, mask_names)
        if manifest_pairs is not None:
            pairs = manifest_pairs
            paired_images = {p["image"] for p in pairs}
            paired_masks = {p["mask"] for p in pairs}
            unmatched_images = sorted((n for n in image_names if n not in paired_images), key=str.lower)
            unmatched_masks = sorted((n for n in mask_names if n not in paired_masks), key=str.lower)
            pairing_source = "dataset.json"
        else:
            pairs, unmatched_images, unmatched_masks, extra_channels = pair_by_case(
                image_names, mask_names
            )
    else:
        detected, unpaired = detect_volume_pairs(image_names)
        pairs = [{"image": p["image"], "mask": p["mask"], "case": p["base"]} for p in detected]
        unmatched_images, unmatched_masks = unpaired, []

    return {
        "image_directory": _stored_path(image_dir),
        "mask_directory": _stored_path(mask_dir) if separate else "",
        "image_files": image_files,
        "mask_files": mask_files,
        "pairs": pairs,
        "unmatched_images": unmatched_images,
        "unmatched_masks": unmatched_masks,
        "extra_channels": extra_channels,
        "pairing_source": pairing_source,
        "split": split_for_directory(image_dir.name),
        "suggestions": suggest_sibling_directories(image_dir),
        "dataset_metadata": (manifest or {}).get("metadata") or {},
        "manifest_path": (manifest or {}).get("path", ""),
    }


def _manifest_pairs_for(
    manifest: dict | None,
    image_dir: Path,
    mask_dir: Path,
    image_names: list[str],
    mask_names: list[str],
) -> list[dict] | None:
    """Manifest pairs, but only when they describe these two folders.

    Picking ``labelsTr-instance`` when the manifest documents ``labelsTr`` means
    the manifest does not apply; the caller falls back to name matching.
    """
    if not manifest or not manifest.get("pairs"):
        return None
    available_images, available_masks = set(image_names), set(mask_names)
    pairs = []
    for entry in manifest["pairs"]:
        if entry["image_dir"] != image_dir.name or entry["mask_dir"] != mask_dir.name:
            return None
        # A manifest listing files that are not on disk is stale, not authoritative.
        if entry["image"] not in available_images or entry["mask"] not in available_masks:
            return None
        pairs.append({"image": entry["image"], "mask": entry["mask"], "case": entry["case"]})
    return pairs or None


def scan_hpc_directory(hpc_directory: str) -> dict:
    """Single-directory scan (legacy shape, kept for existing callers)."""
    result = scan_data_sources(hpc_directory)
    return {
        "directory": result["image_directory"],
        "files": result["image_files"],
        "pairs": [
            {"image": p["image"], "mask": p["mask"], "base": p["case"]}
            for p in result["pairs"]
        ],
        "unpaired": result["unmatched_images"],
    }


def register_dataset(
    *,
    created_by,
    dataset: str,
    volume: str,
    image_directory: str = "",
    mask_directory: str = "",
    hpc_directory: str = "",
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

    ``dataset`` and ``volume`` are required, as is an image directory — given
    either as ``image_directory`` or, for older callers, ``hpc_directory``.
    Masks may live in a **separate** ``mask_directory`` (the usual nnU-Net
    ``imagesTr``/``labelsTr`` split); when it is omitted, masks are looked for
    alongside the images. Every referenced file must be a supported
    ``.tif``/``.tiff``/``.nii.gz`` file in its own directory.

    Registration is flexible about image/mask pairing:

    * ``pairs`` — explicit ``[{image, mask?, chunk_id?}, ...]`` entries. Each
      becomes one volume; when ``mask`` is given it is stored as the label,
      resolved against ``mask_directory``.
    * ``files`` — image-only ``[{path|name, chunk_id?}, ...]`` entries (no masks).
    * neither — the directories are scanned and **all detected image+mask pairs
      plus any unpaired images** are registered.

    ``label_type`` is applied to volumes that get a mask (defaulting to
    ``prediction`` so they become proofreading tasks). Returns ``(project,
    [Volume, ...])``; a new project is created unless ``project`` is given, and
    the volumes are grouped under a :class:`projects.Dataset` named ``dataset``.
    """
    from projects.services import create_project, get_or_create_dataset

    dataset = (dataset or "").strip()
    volume = (volume or "").strip()
    if not dataset:
        raise DataRegistrationError("A dataset name is required.")
    if not volume:
        raise DataRegistrationError("A volume name is required.")

    image_source = (image_directory or hpc_directory or "").strip()
    if not image_source:
        raise DataRegistrationError("An image directory is required.")
    directory = resolve_hpc_directory(image_source)
    mask_source = (mask_directory or "").strip()
    mask_dir = resolve_hpc_directory(mask_source) if mask_source else directory

    def _resolve(raw_name: str, kind: str = "file", *, where: Path | None = None):
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
        candidate = ((where or directory) / base).resolve()
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
                mask_base, mask_path, _ = _resolve(mask_name, "mask", where=mask_dir)
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
        scanned = scan_data_sources(image_source, mask_source)
        for pair in scanned["pairs"]:
            image_base, image_path, image_ext = _resolve(pair["image"], "image")
            mask_base, mask_path, _ = _resolve(pair["mask"], "mask", where=mask_dir)
            entries.append(
                (image_base, image_path, image_ext, mask_base, mask_path, "")
            )
        for name in scanned["unmatched_images"]:
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
            # Metadata describes the data, not the project, so it goes on the
            # dataset below — a project may hold several with differing values.
            metadata={},
            reviewed=reviewed,
        )

    # Metadata describes *this* data, so it belongs to the dataset. Registering
    # again under the same name adds volumes to the existing dataset.
    dataset_row = get_or_create_dataset(
        project=project,
        name=dataset,
        description=description,
        metadata=metadata or {},
        image_directory=_stored_path(directory),
        mask_directory=_stored_path(mask_dir) if mask_source else "",
    )

    # A provided mask implies a real label; default it to a proofreadable type.
    mask_label_type = label_type
    if not mask_label_type or mask_label_type == LabelType.NONE:
        mask_label_type = LabelType.PREDICTION

    # Which nnU-Net split these files came from, so train and test data stay
    # distinguishable once registered.
    split = split_for_directory(directory.name)

    created = []
    for image_base, image_path, image_ext, _mask_base, mask_path, chunk_id in entries:
        has_mask = mask_path is not None
        # The case id names the volume: 'case_00', not 'case_00_0000.tiff'.
        case = case_key(image_base)
        vol = register_volume(
            project=project,
            dataset=dataset_row,
            name=chunk_id or case,
            image_path=_stored_path(image_path),
            label_path=_stored_path(mask_path) if has_mask else "",
            label_type=mask_label_type if has_mask else LabelType.NONE,
            file_format=_file_format_for(image_ext),
            metadata={"split": split} if split else None,
        )
        vol.source_volume = volume
        vol.chunk_id = chunk_id or case
        vol.save(update_fields=["source_volume", "chunk_id"])
        created.append(vol)

    return project, created


def register_volume(
    *,
    project=None,
    dataset=None,
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
    """Register (or upload) an image volume under a project and dataset.

    Either ``project`` or ``dataset`` must be given; the project is taken from
    the dataset when omitted, keeping the denormalised FK consistent.

    ``voxel_size`` may be a ``(z, y, x)`` tuple. If ``autodetect_shape`` is set
    and the image is a readable TIFF under ``MITO_DATA_ROOT``, the ``(x, y, z)``
    shape is filled in automatically.
    """
    if project is None and dataset is None:
        raise DataRegistrationError("A project or dataset is required.")
    if project is None:
        project = dataset.project

    volume = Volume(
        project=project,
        dataset=dataset,
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

    if autodetect_shape and (volume.shape_z is None or volume.voxel_size_z is None):
        _try_autodetect_shape(volume)

    return volume


def _try_autodetect_shape(volume: Volume) -> None:
    """Fill shape and voxel size from the image file when they can be read.

    Shape comes from TIFF headers; voxel size from TIFF resolution/ImageJ
    metadata (or NIfTI pixdim). Each is only filled when it is still blank, so a
    manually-entered value is never overwritten.
    """
    location = volume.image_location
    if not location:
        return
    # image_file names are relative to MITO_DATA_ROOT; image_path may be
    # absolute or relative to the same root.
    candidate = Path(location)
    if not candidate.is_absolute():
        candidate = Path(settings.MITO_DATA_ROOT) / location

    changed: list[str] = []
    if volume.shape_z is None:
        shape = inspect_volume_shape(candidate)
        if shape is not None:
            volume.shape_x, volume.shape_y, volume.shape_z = shape
            changed += ["shape_x", "shape_y", "shape_z"]

    if volume.voxel_size_z is None:
        voxel = inspect_volume_voxel_size(candidate)
        if voxel is not None:
            z, y, x = voxel
            if z is not None:
                volume.voxel_size_z = z
                changed.append("voxel_size_z")
            if y is not None:
                volume.voxel_size_y = y
                changed.append("voxel_size_y")
            if x is not None:
                volume.voxel_size_x = x
                changed.append("voxel_size_x")

    if changed:
        volume.save(update_fields=changed)


def update_volume_metadata(volume: Volume, **fields) -> Volume:
    """Update whitelisted volume fields.

    ``image_path``/``label_path`` are editable so a wrong pairing can be fixed
    without re-registering, and ``dataset`` so a volume can be moved to the
    right dataset (its project follows).
    """
    allowed = {
        "name",
        "chunk_id",
        "source_volume",
        "label_type",
        "image_path",
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
        elif key == "dataset" and value is not None:
            volume.dataset = value
            # The project is denormalised from the dataset; keep them in step.
            volume.project = value.project
            changed.extend(["dataset", "project"])
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
                deadline=volume.project.deadline,
            )
        )
    created = AnnotationTask.objects.bulk_create(tasks)

    volume.status = VolumeStatus.SPLIT
    volume.save(update_fields=["status"])
    return created


# Backwards/forwards-compatible name matching the product spec.
def split_volume_into_tasks(volume, z_step=16, task_type=None):
    return create_tasks_from_volume(volume, z_step=z_step, task_type=task_type)
