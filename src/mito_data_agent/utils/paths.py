"""Project path helpers."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

OUTPUT_SUBDIRS = ("hf_staging", "mitoverse_updates", "execution_reports", "metadata_store", "logs", "cache")


def get_project_root() -> Path:
    """Return the mito_data_agent project root (parent of src/)."""
    # utils/paths.py -> utils -> mito_data_agent -> src -> project root
    return Path(__file__).resolve().parents[3]


def resolve_path(path: str | Path | None) -> Path | None:
    """Resolve a path for file I/O (relative paths are anchored to the project root)."""
    if path is None or path == "":
        return None
    p = Path(path)
    if p.is_absolute():
        return p
    return (get_project_root() / p).resolve()


def to_relative_path(path: str | Path | None) -> str | None:
    """Return a project-relative path string for storage and display."""
    if path is None or path == "":
        return None
    p = Path(path)
    if not p.is_absolute():
        return str(p).replace("\\", "/")

    resolved = p.resolve()
    root = get_project_root().resolve()
    try:
        return str(resolved.relative_to(root)).replace("\\", "/")
    except ValueError:
        pass
    try:
        rel = resolved.relative_to(root.parent)
        return str(Path("..") / rel).replace("\\", "/")
    except ValueError:
        return str(path)


def normalize_stored_path(path: str | Path | None) -> str | None:
    """Normalize user or tool paths to relative form when possible."""
    if path is None or path == "":
        return None
    resolved = resolve_path(path)
    if resolved is None:
        return None
    return to_relative_path(resolved)


def get_outputs_dir() -> Path:
    """Return the outputs/ directory."""
    return get_project_root() / "outputs"


def get_prompt_examples_dir() -> Path:
    """Return the example-prompts directory (prompts/examples/)."""
    return get_project_root() / "prompts" / "examples"


def ensure_output_dirs() -> None:
    """Create all expected output subdirectories."""
    outputs = get_outputs_dir()
    for subdir in OUTPUT_SUBDIRS:
        subpath = outputs / subdir
        subpath.mkdir(parents=True, exist_ok=True)
        gitkeep = subpath / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()


def clear_outputs() -> dict[str, int]:
    """Remove all generated artifacts and run history under outputs/.

    Preserves the outputs/ folder structure and .gitkeep files.
    """
    outputs = get_outputs_dir()
    removed_files = 0
    removed_dirs = 0

    for subdir in OUTPUT_SUBDIRS:
        path = outputs / subdir
        if not path.exists():
            continue
        for item in list(path.iterdir()):
            if item.name == ".gitkeep":
                continue
            if item.is_dir():
                shutil.rmtree(item)
                removed_dirs += 1
            else:
                item.unlink()
                removed_files += 1

    ensure_output_dirs()
    return {"removed_files": removed_files, "removed_dirs": removed_dirs}


def safe_slug(text: str) -> str:
    """Make a volume name safe for folder and branch names."""
    slug = text.strip().lower()
    slug = re.sub(r"[^\w\-]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "unknown-volume"
