"""Run ID helpers."""

from datetime import datetime


def make_run_id() -> str:
    """Return a readable timestamp-based run id, e.g. run_YYYYMMDD_HHMMSS."""
    return datetime.now().strftime("run_%Y%m%d_%H%M%S")
