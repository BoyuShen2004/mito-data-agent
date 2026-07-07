"""FastAPI backend for the Mito Data Agent web UI.

The UI is intentionally thin: it POSTs a free-form prompt to ``/api/run`` and
renders whatever the multi-agent workflow returns (report text, structured
summary, and the supervisor/agent trace). All real work and formatting live in
``agents/`` and ``tools/`` — this module only exposes them over HTTP.

Endpoints
    GET  /                     the single-page UI
    GET  /api/health           backend status + active LLM backend
    GET  /api/examples         example prompts (from prompts/examples/*.md)
    POST /api/run              run the workflow on a prompt
    GET  /api/records          list the recorded-metadata ledger
    GET  /api/records/{volume} one record (+ version history)
    GET  /api/settings         current LLM settings (API key masked)
    POST /api/settings         update + persist LLM settings
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from mito_data_agent import config
from mito_data_agent.agents.runner import run_multi_agent
from mito_data_agent.llm.settings_store import (
    LLMConnectionSettings,
    apply_settings_to_config,
    load_settings,
    save_settings,
    settings_for_api,
)
from mito_data_agent.tools.metadata_store import get_record, get_store_path, list_records
from mito_data_agent.tools.reporting import render_report_text
from mito_data_agent.utils.paths import get_prompt_examples_dir, to_relative_path
from mito_data_agent.utils.prompts import load_prompt_file

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Friendly titles for the example prompt files (fallback = prettified filename).
_EXAMPLE_TITLES = {
    "freeform_upload_prompt.md": "Free-form upload",
    "upload_prompt.md": "Prepare upload",
    "readiness_prompt.md": "Check readiness",
    "metadata_only_prompt.md": "Record metadata only",
    "lookup_mitoverse_prompt.md": "Look up in MitoVerse",
}


@asynccontextmanager
async def _lifespan(_: FastAPI):
    # Load persisted LLM settings so the UI works without env vars.
    apply_settings_to_config(load_settings())
    yield


app = FastAPI(
    title="Mito Data Agent",
    description="Web UI for prompt-driven MitoVerse metadata recording",
    version="0.2.0",
    lifespan=_lifespan,
)


# --------------------------------------------------------------------------- #
# Request / response models
# --------------------------------------------------------------------------- #
class RunRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Free-form user request")


class SettingsUpdate(BaseModel):
    llm_backend: Optional[Literal["openai", "codex_cli"]] = None
    llm_model: Optional[str] = None
    openai_api_key: Optional[str] = None
    codex_path: Optional[str] = None


# --------------------------------------------------------------------------- #
# Static page
# --------------------------------------------------------------------------- #
@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "llm_backend": config.LLM_BACKEND,
        "llm_model": config.LLM_MODEL,
        "record_count": len(list_records()),
        "store_path": to_relative_path(get_store_path()),
    }


@app.get("/api/examples")
def examples() -> list[dict]:
    out: list[dict] = []
    examples_dir = get_prompt_examples_dir()
    if not examples_dir.exists():
        return out
    for path in sorted(examples_dir.glob("*.md")):
        title = _EXAMPLE_TITLES.get(path.name) or path.stem.replace("_", " ").title()
        try:
            text = load_prompt_file(path)
        except OSError:
            continue
        out.append({"title": title, "text": text})
    return out


@app.post("/api/run")
def run(req: RunRequest) -> dict:
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt must not be empty.")
    try:
        result = run_multi_agent(prompt, trace=True, print_trace_output=False)
    except Exception as exc:  # surface the failure to the UI instead of a 500 blob
        raise HTTPException(status_code=500, detail=f"Run failed: {exc}") from exc

    raw = result.get("raw", {})
    return {
        "run_id": raw.get("run_id"),
        "report_text": render_report_text(raw),
        "summary": result.get("summary", {}),
        "trace": result.get("trace", []),
    }


@app.get("/api/records")
def records() -> dict:
    return {
        "store_path": to_relative_path(get_store_path()),
        "records": list_records(),
    }


@app.get("/api/records/{volume}")
def record(volume: str) -> dict:
    rec = get_record(volume)
    if not rec:
        raise HTTPException(status_code=404, detail=f"No record for volume: {volume}")
    return rec


@app.get("/api/settings")
def get_settings() -> dict:
    return settings_for_api()


@app.post("/api/settings")
def update_settings(update: SettingsUpdate) -> dict:
    current = load_settings()
    data = current.model_dump()
    for key, value in update.model_dump(exclude_none=True).items():
        data[key] = value
    saved = save_settings(LLMConnectionSettings.model_validate(data))
    return settings_for_api(saved)


# Serve remaining static assets (favicon, etc.) if any are added later.
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
