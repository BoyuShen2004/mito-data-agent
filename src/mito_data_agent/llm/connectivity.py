"""Test LLM backend connectivity with OpenClaw-style terminal logs."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any

from mito_data_agent.llm.settings_store import LLMConnectionSettings, load_settings, save_settings


def _log_line(log: list[str], line: str) -> None:
    log.append(line)


def _run_cmd(log: list[str], cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    _log_line(log, f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.stdout.strip():
        for ln in result.stdout.strip().splitlines():
            _log_line(log, ln)
    if result.stderr.strip():
        for ln in result.stderr.strip().splitlines():
            _log_line(log, f"[stderr] {ln}")
    _log_line(log, f"[exit {result.returncode}]")
    return result


def detect_codex() -> dict[str, Any]:
    path = shutil.which("codex")
    return {
        "installed": path is not None,
        "path": path,
        "version": _codex_version(path) if path else None,
    }


def _codex_version(codex_path: str) -> str | None:
    try:
        r = subprocess.run([codex_path, "--version"], capture_output=True, text=True, timeout=15)
        return r.stdout.strip() or r.stderr.strip() or None
    except Exception:
        return None


def test_llm_connection(settings: LLMConnectionSettings | None = None) -> dict[str, Any]:
    """Run a backend connectivity test and return terminal-style logs."""
    s = settings or load_settings()
    log: list[str] = []
    success = False
    message = ""

    _log_line(log, "=== Mito Data Agent · LLM connection test ===")
    _log_line(log, f"backend: {s.llm_backend}")

    if s.llm_backend == "codex_cli":
        codex = s.codex_path or shutil.which("codex")
        if not codex:
            message = "Codex CLI not found on PATH."
            _log_line(log, message)
            _log_line(log, "Install Codex, then run: codex login")
        else:
            _log_line(log, f"Using Codex at: {codex}")
            doctor = _run_cmd(log, [codex, "doctor"], timeout=90)
            ping = _run_cmd(
                log,
                [
                    codex,
                    "exec",
                    "--full-auto",
                    'Return ONLY JSON: {"intent":"upload_annotation","volume":"connection_test","notes":["ping"]}',
                ],
                timeout=120,
            )
            success = ping.returncode == 0
            if success:
                message = "Connected to Codex CLI successfully."
                _log_line(log, "✓ Codex connection OK")
            else:
                message = "Codex CLI found but exec failed. Run `codex login` in your terminal."
                _log_line(log, "✗ Codex exec failed — try: codex login")
            if doctor.returncode != 0:
                _log_line(log, "Note: codex doctor reported issues (see above).")

    elif s.llm_backend == "openai":
        if not s.openai_api_key:
            message = "OpenAI API key not set. Enter it in the Web UI connection panel."
            _log_line(log, message)
        else:
            try:
                from openai import OpenAI

                _log_line(log, f"Testing OpenAI model: {s.llm_model}")
                client = OpenAI(api_key=s.openai_api_key)
                models = client.models.list()
                _log_line(log, f"✓ OpenAI API key valid (models available: {len(list(models.data)[:1])}+)")
                success = True
                message = "Connected to OpenAI API successfully."
            except Exception as exc:
                message = f"OpenAI connection failed: {exc}"
                _log_line(log, f"✗ {message}")

    s.last_test_success = success
    s.last_test_message = message
    save_settings(s)

    return {
        "success": success,
        "message": message,
        "backend": s.llm_backend,
        "terminal_log": log,
        "codex": detect_codex(),
    }
