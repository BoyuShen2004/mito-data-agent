"""FastAPI server for the Mito Data Agent chat UI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional

import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from mito_data_agent.llm.connectivity import detect_codex, test_llm_connection
from mito_data_agent.llm.settings_store import (
    LLMConnectionSettings,
    apply_settings_to_config,
    load_settings,
    save_settings,
    settings_for_api,
)
from mito_data_agent.runner import run_agent, run_agent_stream
from mito_data_agent.utils.paths import get_examples_dir
from mito_data_agent.utils.prompts import load_prompt_file

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
EXAMPLES_DIR = get_examples_dir()


def _load_example(name: str, fallback: str) -> str:
    path = EXAMPLES_DIR / name
    if path.exists():
        return load_prompt_file(path)
    return fallback


app = FastAPI(
    title="Mito Data Agent",
    description="Chat UI for prompt-driven MitoVerse upload preparation",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    apply_settings_to_config(load_settings())


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User prompt for the agent")
    trace: bool = Field(
        default=False,
        description="Return LangGraph node-by-node trace (like LangGraph tutorial)",
    )


class ChatResponse(BaseModel):
    message: str
    summary: dict
    trace: list[dict] | None = None
    trace_text: str | None = None


class ExamplePrompt(BaseModel):
    title: str
    text: str


class LLMSettingsUpdate(BaseModel):
    llm_backend: Optional[Literal["openai", "codex_cli"]] = None
    llm_model: Optional[str] = None
    openai_api_key: Optional[str] = None
    codex_path: Optional[str] = None
    allow_rule_based_fallback: Optional[bool] = None


EXAMPLE_PROMPTS = [
    ExamplePrompt(
        title="Free-form upload (LLM)",
        text=_load_example("freeform_upload_prompt.md", "Upload vol1 to MitoVerse with raw and label paths..."),
    ),
    ExamplePrompt(
        title="Upload annotation",
        text=_load_example("upload_prompt.md", "Please upload this volume to MitoVerse.\nVolume: test\n..."),
    ),
    ExamplePrompt(
        title="Check readiness",
        text=_load_example("readiness_prompt.md", "Please check upload readiness.\nVolume: test\n..."),
    ),
    ExamplePrompt(
        title="Metadata only",
        text=_load_example("metadata_only_prompt.md", "Please update only MitoVerse metadata.\nVolume: test\n..."),
    ),
    ExamplePrompt(
        title="Lookup in MitoVerse",
        text=_load_example(
            "lookup_mitoverse_prompt.md",
            "Is jrc_mus-liver_recon-1_test0 already in the MitoVerse collection?",
        ),
    ),
]


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    settings = load_settings()
    codex = detect_codex()
    return {
        "status": "ok",
        "project_root": ".",
        "trace_default": os.environ.get("MITO_AGENT_TRACE", "") == "1",
        "llm_backend": settings.llm_backend,
        "llm_connected": settings.last_test_success,
        "codex_installed": codex["installed"],
    }


@app.get("/api/examples", response_model=list[ExamplePrompt])
async def examples():
    return EXAMPLE_PROMPTS


@app.get("/api/llm/settings")
async def get_llm_settings():
    return {
        **settings_for_api(),
        "codex": detect_codex(),
    }


@app.post("/api/llm/settings")
async def update_llm_settings(req: LLMSettingsUpdate):
    current = load_settings()
    data = current.model_dump()
    updates = req.model_dump(exclude_unset=True)
    if "openai_api_key" in updates and not updates["openai_api_key"]:
        updates.pop("openai_api_key")
    data.update(updates)
    settings = save_settings(LLMConnectionSettings.model_validate(data))
    return {
        **settings_for_api(settings),
        "codex": detect_codex(),
    }


@app.get("/api/llm/status")
async def llm_status():
    settings = load_settings()
    codex = detect_codex()
    return {
        "backend": settings.llm_backend,
        "model": settings.llm_model,
        "connected": settings.last_test_success,
        "message": settings.last_test_message,
        "codex": codex,
        "openai_api_key_set": bool(settings.openai_api_key),
    }


@app.post("/api/llm/test")
async def llm_test():
    try:
        return test_llm_connection()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    prompt = req.message.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    apply_settings_to_config(load_settings())
    try:
        use_trace = req.trace or os.environ.get("MITO_AGENT_TRACE", "") == "1"
        result = run_agent(prompt, trace=use_trace, print_trace=False)
        return ChatResponse(
            message=result["message"],
            summary=result["summary"],
            trace=result.get("trace") or None,
            trace_text=result.get("trace_text"),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Server-Sent Events: one event per LangGraph node, then final result."""
    prompt = req.message.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    apply_settings_to_config(load_settings())

    def event_generator():
        try:
            for event in run_agent_stream(prompt):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)}, default=str)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
