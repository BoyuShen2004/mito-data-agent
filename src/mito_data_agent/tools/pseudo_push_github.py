"""Pseudo GitHub push — stub implementation (no GitHub API calls).

Replace this module with a real pusher when ALLOW_REAL_GITHUB_PUSH is enabled.
"""

from __future__ import annotations

from mito_data_agent.config import DEFAULT_GITHUB_REPO
from mito_data_agent.schemas import PseudoToolResult
from mito_data_agent.tools.pseudo_signal import build_pseudo_result
from mito_data_agent.utils.paths import resolve_path, to_relative_path


def pseudo_push_to_github(
    update_files: list[str],
    repo: str = DEFAULT_GITHUB_REPO,
    branch_name: str = "agent/add-volume",
    pr_title: str = "Add MitoVerse volume metadata",
) -> PseudoToolResult:
    """Validate update files and return a PR plan. Does not call GitHub APIs."""
    if branch_name in ("main", "master"):
        raise RuntimeError(
            f"Refusing to use protected branch name: {branch_name}"
        )

    files_checked: list[str] = []
    success = True
    missing: list[str] = []

    for fp in update_files:
        path = resolve_path(fp)
        rel = to_relative_path(path) or str(fp)
        files_checked.append(rel)
        if path is None or not path.exists():
            success = False
            missing.append(rel)

    if missing:
        message = (
            "Pseudo push executed (no GitHub API call). "
            f"Missing files: {', '.join(missing)}"
        )
    else:
        message = (
            "Pseudo push executed (no GitHub API call). "
            f"Would create branch '{branch_name}', commit {len(update_files)} "
            f"file(s), and open PR '{pr_title}' on {repo}."
        )

    return build_pseudo_result(
        tool_name="pseudo_push_github",
        success=success,
        target=repo,
        files_checked=files_checked,
        planned_action="Would create branch, commit update files, and open PR",
        message=message,
    )
