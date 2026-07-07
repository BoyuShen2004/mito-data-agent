"""Central configuration for the Mito Data Agent."""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Swap tool implementations (e.g. pseudo_upload_hf → real upload) when ready.
ALLOW_REAL_HF_UPLOAD = False
ALLOW_REAL_GITHUB_PUSH = False
ALLOW_REAL_MITOVERSE_UPDATE = False
ALLOW_DATASET_SEARCH = False
ALLOW_MITOVERSE_CATALOG_LOOKUP = True
ALLOW_MODEL_TRAINING = False
ALLOW_EXTERNAL_DOWNLOAD = False

DEFAULT_HF_REPO_ID = "pytc/MitoVerse"
DEFAULT_GITHUB_REPO = "pytorchconnectomics/mitoverse"
MITOVERSE_CATALOG_URL = "https://huggingface.co/datasets/pytc/MitoVerse/raw/main/catalog.json"
MITOVERSE_EXPLORER_URL = "https://pytorchconnectomics.github.io/mitoverse/"

DEFAULT_DATA_DIR = os.getenv("MITO_AGENT_DATA_DIR", "../mito_data_agent_data")

# This is an agentic system: prompt parsing and routing are LLM-driven, with no
# rule-based fallback. An LLM backend must be configured.
LLM_BACKEND = os.getenv("MITO_AGENT_LLM_BACKEND", "openai")
LLM_MODEL = os.getenv("MITO_AGENT_LLM_MODEL", "gpt-5.5")
USE_CODEX_CLI = os.getenv("USE_CODEX_CLI", "false").lower() == "true"

REQUIRED_MITOVERSE_COLUMNS = [
    "volume",
    "dataset",
    "modality",
    "organism",
    "organ",
    "tissue_region",
    "resolution_nm",
    "shape_xyz",
    "num_mito",
]

ALLOWED_INTENTS = None  # populated from task registry; see get_allowed_intents()


def get_allowed_intents() -> list[str]:
    from mito_data_agent.tasks import get_registered_intents

    return get_registered_intents()


def apply_runtime_config(
    *,
    llm_backend: str | None = None,
    llm_model: str | None = None,
    use_codex_cli: bool | None = None,
    openai_api_key: str | None = None,
    codex_path: str | None = None,
) -> None:
    """Override LLM settings from CLI flags (mutates module-level config)."""
    global LLM_BACKEND, LLM_MODEL, USE_CODEX_CLI

    if llm_backend is not None:
        LLM_BACKEND = llm_backend
    if llm_model is not None:
        LLM_MODEL = llm_model
    if use_codex_cli is not None:
        USE_CODEX_CLI = use_codex_cli
        if use_codex_cli:
            LLM_BACKEND = "codex_cli"
    if openai_api_key is not None:
        global _RUNTIME_OPENAI_API_KEY
        _RUNTIME_OPENAI_API_KEY = openai_api_key
    if codex_path is not None:
        global _RUNTIME_CODEX_PATH
        _RUNTIME_CODEX_PATH = codex_path


# Runtime overrides from Web UI settings store (preferred over env vars)
_RUNTIME_OPENAI_API_KEY: str | None = None
_RUNTIME_CODEX_PATH: str | None = None
