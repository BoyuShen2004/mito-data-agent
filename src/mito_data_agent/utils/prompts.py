"""Load prompt text from .md files."""

from __future__ import annotations

import re
from pathlib import Path


_HUMAN_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def load_prompt_file(path: str | Path) -> str:
    """Read a prompt .md file and strip human-only HTML comments."""
    text = Path(path).read_text(encoding="utf-8")
    text = _HUMAN_COMMENT.sub("", text)
    return text.strip()
