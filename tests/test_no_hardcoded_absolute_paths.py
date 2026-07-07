"""Guard against hard-coded machine-specific absolute paths in source assets."""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SCAN_ROOTS = ("src/mito_data_agent", "tests", "prompts")
SCAN_SUFFIXES = {".py", ".md", ".html", ".toml"}
SKIP_PARTS = {".egg-info", "__pycache__", ".pytest_cache"}

# Machine-specific prefixes that must not appear in committed source/examples.
FORBIDDEN_PATTERNS = (
    re.compile(r'["\']/projects/weilab/shenb'),
    re.compile(r'["\']/home/shenb'),
)


def _iter_scan_files() -> list[Path]:
    files: list[Path] = []
    for rel in SCAN_ROOTS:
        root = PROJECT_ROOT / rel
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in SCAN_SUFFIXES:
                continue
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            files.append(path)
    return files


def test_no_hardcoded_absolute_paths_in_source():
    offenders: list[str] = []
    for path in _iter_scan_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
                break
    assert not offenders, (
        "Hard-coded absolute paths found. Use relative paths via utils.paths instead:\n"
        + "\n".join(f"  - {p}" for p in sorted(offenders))
    )
