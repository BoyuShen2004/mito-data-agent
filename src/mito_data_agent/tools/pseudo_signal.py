"""Simple success/failure signals for stub tools (local outputs or pseudo external ops)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from mito_data_agent.schemas import PseudoToolResult
from mito_data_agent.utils.paths import resolve_path, to_relative_path

Signal = Literal["ok", "failed"]
StubMode = Literal["pseudo", "local"]


def stub_signal(success: bool) -> Signal:
    return "ok" if success else "failed"


def build_stub_result(
    *,
    tool_name: str,
    success: bool,
    mode: StubMode,
    target: str,
    planned_action: str,
    message: str,
    files_checked: list[str] | None = None,
    output_paths: list[str] | None = None,
) -> PseudoToolResult:
    """Standard stub-tool payload: executed=True, no external write in MVP."""
    return PseudoToolResult(
        tool_name=tool_name,
        mode=mode,
        executed=True,
        signal=stub_signal(success),
        success=success,
        real_write_performed=False,
        target=target,
        files_checked=files_checked or [],
        output_paths=output_paths or [],
        planned_action=planned_action,
        message=message,
    )


def build_pseudo_result(
    *,
    tool_name: str,
    success: bool,
    target: str,
    planned_action: str,
    message: str,
    files_checked: list[str] | None = None,
) -> PseudoToolResult:
    """Shorthand for external pseudo tools (HF / GitHub)."""
    return build_stub_result(
        tool_name=tool_name,
        success=success,
        mode="pseudo",
        target=target,
        planned_action=planned_action,
        message=message,
        files_checked=files_checked,
    )


def stub_tool_observation(result: PseudoToolResult) -> dict[str, Any]:
    """JSON observation returned to the LLM after a stub tool runs."""
    return {
        "observation": "stub_tool_result",
        "signal": result.signal,
        "data": result.model_dump(),
    }


def pseudo_tool_observation(result: PseudoToolResult) -> dict[str, Any]:
    return stub_tool_observation(result)


def _paths_exist(paths: list[str | Path]) -> tuple[bool, list[str]]:
    checked: list[str] = []
    all_exist = True
    for raw in paths:
        rel = to_relative_path(raw) or str(raw)
        checked.append(rel)
        resolved = resolve_path(raw)
        if resolved is None or not resolved.exists():
            all_exist = False
    return all_exist, checked
