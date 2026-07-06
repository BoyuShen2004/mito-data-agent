"""Persisted LLM connection settings (no env vars required for Web UI)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from mito_data_agent.utils.paths import get_outputs_dir


class LLMConnectionSettings(BaseModel):
    """LLM backend configuration saved from the Web UI or CLI."""

    llm_backend: Literal["openai", "codex_cli"] = "codex_cli"
    llm_model: str = "gpt-4.1"
    openai_api_key: Optional[str] = None
    codex_path: Optional[str] = None
    allow_rule_based_fallback: bool = False
    last_test_success: Optional[bool] = None
    last_test_message: Optional[str] = None


def _settings_path() -> Path:
    path = get_outputs_dir() / "logs" / "llm_connection.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _default_codex_path() -> Optional[str]:
    return shutil.which("codex")


def default_settings() -> LLMConnectionSettings:
    """Pick Codex CLI automatically when installed."""
    codex = _default_codex_path()
    return LLMConnectionSettings(
        llm_backend="codex_cli" if codex else "openai",
        codex_path=codex,
    )


def load_settings() -> LLMConnectionSettings:
    path = _settings_path()
    if not path.exists():
        settings = default_settings()
        save_settings(settings)
        return settings
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        settings = LLMConnectionSettings.model_validate(data)
    except (json.JSONDecodeError, ValueError):
        settings = default_settings()
    if settings.llm_backend == "codex_cli" and not settings.codex_path:
        settings.codex_path = _default_codex_path()
    return settings


def save_settings(settings: LLMConnectionSettings) -> LLMConnectionSettings:
    path = _settings_path()
    path.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    apply_settings_to_config(settings)
    return settings


def apply_settings_to_config(settings: LLMConnectionSettings | None = None) -> LLMConnectionSettings:
    """Push saved settings into runtime config used by LLMClient."""
    from mito_data_agent import config

    s = settings or load_settings()
    config.LLM_BACKEND = s.llm_backend
    config.LLM_MODEL = s.llm_model
    config.USE_CODEX_CLI = s.llm_backend == "codex_cli"
    config.ALLOW_RULE_BASED_FALLBACK = s.allow_rule_based_fallback
    config._RUNTIME_OPENAI_API_KEY = s.openai_api_key  # type: ignore[attr-defined]
    config._RUNTIME_CODEX_PATH = s.codex_path  # type: ignore[attr-defined]
    return s


def settings_for_api(settings: LLMConnectionSettings | None = None) -> dict:
    """API-safe view (mask API key)."""
    s = settings or load_settings()
    data = s.model_dump()
    key = data.get("openai_api_key")
    if key:
        data["openai_api_key_set"] = True
        data["openai_api_key"] = None
        data["openai_api_key_preview"] = key[:7] + "…" + key[-4:] if len(key) > 12 else "••••"
    else:
        data["openai_api_key_set"] = False
        data["openai_api_key_preview"] = None
    return data
