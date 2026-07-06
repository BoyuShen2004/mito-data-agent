"""Pseudo Hugging Face upload — stub implementation (no HF API calls).

Replace this module with a real uploader when ALLOW_REAL_HF_UPLOAD is enabled.
"""

from __future__ import annotations

from mito_data_agent.config import DEFAULT_HF_REPO_ID
from mito_data_agent.schemas import PseudoToolResult
from mito_data_agent.tools.pseudo_signal import build_pseudo_result
from mito_data_agent.utils.paths import resolve_path, to_relative_path


def pseudo_upload_to_hf(
    hf_staging_dir: str,
    hf_repo_id: str = DEFAULT_HF_REPO_ID,
) -> PseudoToolResult:
    """Validate staging artifacts and return an upload plan. Does not call HF APIs."""
    staging = resolve_path(hf_staging_dir)
    files_checked: list[str] = []
    success = True
    messages: list[str] = []

    if staging is None or not staging.exists():
        success = False
        messages.append(f"Staging directory not found: {hf_staging_dir}")
    else:
        for name in ("metadata.json", "manifest.json"):
            fp = staging / name
            files_checked.append(to_relative_path(fp) or str(fp))
            if not fp.exists():
                success = False
                messages.append(f"Missing required file: {fp}")

    message = (
        "Pseudo upload executed (no Hugging Face API call). "
        + ("Checks passed." if success else "Checks failed: " + "; ".join(messages))
    )

    return build_pseudo_result(
        tool_name="pseudo_upload_hf",
        success=success,
        target=hf_repo_id,
        files_checked=files_checked,
        planned_action="Would upload HF staging folder to dataset repo",
        message=message,
    )
