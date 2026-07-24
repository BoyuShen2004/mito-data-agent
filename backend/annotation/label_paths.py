"""Where a volume's *working* (in-progress, editable) label copy lives.

Deliberately its own tiny module with no other imports from this app —
``annotation/services.py`` (the editor/tracking backend) and
``annotation/quality_control/adapters/basic.py`` (QC for in-app submissions,
which have no uploaded file to check) both need this path, and keeping it
here instead of importing one from the other avoids any import-order
question between them.

Layout: ``<project name>/<dataset name>/volume_<volume id>_labels.tif``
directly under ``MITO_DATA_ROOT`` — no extra ``labels/`` level (the data
root's own job here *is* holding labels; an app-wide folder just named
"labels" under it was redundant) and no numeric id prefixes on the
project/dataset folders (a previous version had them for rename-stability;
removed because they made the folder names look wrong/unrecognizable —
uniqueness is still guaranteed by the filename, `volume_<id>_labels.tif`,
which is what's actually looked up; see the module docstring further down
for why a folder-name collision between two differently-named projects is
harmless). Volumes without a ``dataset`` (only possible for rows predating
the ``Dataset`` model — see ``volumes/MODULE.md``) fall back to a
``no-dataset`` bucket per project.

Mirrors the project → dataset → volume hierarchy the frontend shows, so a
backend developer (or anyone) browsing ``data/`` on disk can match a file to
what they see in the app.
"""

from __future__ import annotations

import re

_MAX_NAME_LEN = 80
# The only path components an OS resolves specially — must never be allowed
# to stand alone as a sanitized project/dataset directory name (they'd
# resolve to "the current directory" / "the parent directory" instead of an
# actual project/dataset folder).
_RESERVED_NAMES = {".", ".."}


def _safe_name(value: str, fallback: str) -> str:
    """A folder-name-safe version of ``value`` that still looks like the
    project/dataset's actual name (unlike a lowercased, hyphenated slug) —
    keeps spacing, case, and most punctuation, and only touches what would
    actually break as a single path component:

    - ``/`` and ``\\`` (would otherwise split into extra directory levels,
      or on Windows, be a drive/path separator) — replaced with ``-``.
    - Control characters (e.g. embedded newlines/nulls) — replaced with ``-``.
    - Leading/trailing spaces and dots — stripped (trailing dots/spaces are
      invalid or silently dropped on some filesystems; leading dots would
      make the folder look like a hidden file).

    Project/dataset names are free-text user input (``CharField``), so this
    is a real input boundary — without it, a title containing ``/`` could
    otherwise escape the intended directory or create unintended nesting.
    Falls back to ``fallback`` if nothing usable survives (empty, or exactly
    ``.``/``..``).
    """
    value = re.sub(r"[\\/\x00-\x1f]", "-", value.strip())
    value = value.strip(" .")[:_MAX_NAME_LEN].strip(" .")
    if not value or value in _RESERVED_NAMES:
        return fallback
    return value


def project_folder_rel_path(project) -> str:
    """Path (relative to ``MITO_DATA_ROOT``) of ``project``'s own folder.

    Exists so the on-disk layout mirrors the project → dataset → volume
    hierarchy the moment a project is registered — not just once someone
    starts annotating (that's when the *label* file itself first appears;
    see :func:`working_label_rel_path`).
    """
    return _safe_name(project.title, "project")


def dataset_folder_rel_path(project, dataset) -> str:
    """Path (relative to ``MITO_DATA_ROOT``) of ``dataset``'s folder within
    ``project``'s. Same rationale as :func:`project_folder_rel_path`: created
    at registration time, before any volume or label exists.
    """
    dataset_dir = _safe_name(dataset.name, "dataset") if dataset else "no-dataset"
    return f"{project_folder_rel_path(project)}/{dataset_dir}"


def working_label_rel_path(volume) -> str:
    """Path (relative to ``MITO_DATA_ROOT``) of ``volume``'s working label
    copy — the file the in-app editor and SAM2 tracking always read/write,
    regardless of what ``volume.label_path``/``label_file`` (the *official*,
    approved label — see ``annotation.services.approve_submission``)
    currently points at.

    Not guaranteed globally unique by folder name alone (two different
    projects named the same thing share a folder) — that's fine: the
    filename, ``volume_<volume.id>_labels.tif``, is what's actually unique
    and what every read/write in this app looks up by, so a folder-name
    collision only means two projects' files sit in the same directory, not
    that any file ever gets confused for another's.
    """
    dataset_dir = dataset_folder_rel_path(volume.project, volume.dataset)
    return f"{dataset_dir}/volume_{volume.id}_labels.tif"


def working_label_metadata_rel_path(volume) -> str:
    """Path (relative to ``MITO_DATA_ROOT``) of the JSON sidecar holding
    per-label lifecycle state (Proposed/Edited/Verified) for this volume's
    working label copy — mirrors Cellable's ``LabelMetadataStore.
    get_sidecar_path`` (``<mask>_metadata.json``), see
    ``annotation/cellable_port/label_state.py``."""
    from .cellable_port.label_state import LabelMetadataStore

    return LabelMetadataStore.sidecar_path(working_label_rel_path(volume))
