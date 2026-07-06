"""Simple file I/O helpers."""

from __future__ import annotations

import json
from pathlib import Path

from mito_data_agent.utils.paths import to_relative_path


def write_json(path: str | Path, data: dict) -> str:
    """Write a dict as pretty JSON and return the relative path string."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    return to_relative_path(p) or str(p)


def write_text(path: str | Path, text: str) -> str:
    """Write text to a file and return the relative path string."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return to_relative_path(p) or str(p)
