# Mito Data Agent

A **LLM-powered** LangGraph agent for prompt-driven annotated mitochondria volume upload preparation.

## What this project is

**Mito Data Agent** is an AI agent that uses an **LLM to understand free-form annotator prompts**, then runs a LangGraph workflow to inspect files, validate metadata, and prepare dry-run artifacts for Hugging Face staging and MitoVerse table updates.

**LLM is required** for prompt parsing (`REQUIRE_LLM_FOR_PROMPT_PARSING=True`). Rule-based parsing exists only as an optional fallback.

## What this project does

- **LLM parses free-form natural language** into structured MitoVerse metadata (no Key: value required)
- LangGraph orchestrates inspect → observe → merge → validate → generate artifacts
- Python tools read TIFF files and extract **Shape** and **# Mito** (LLM does not fabricate these)
- Generates Hugging Face staging and MitoVerse update files (dry-run)
- Pseudo upload/push simulation with full execution reports

## What this project does not do

- No real Hugging Face upload
- No real GitHub push
- No real MitoVerse website update
- No dataset search
- No external downloads
- No model training
- No segmentation inference

## Install

```bash
cd mito_data_agent
pip install -e ".[dev]"
```

## CLI commands

Entry point (all subcommands):

```bash
python -m mito_data_agent <command> [options]
```

After `pip install -e .`, these console scripts are also available: `mito-agent`, `mito-web`, `mito-clear`.

| Command | Description |
|---------|-------------|
| `agent` | Run the ReAct LangGraph agent from the terminal |
| `web` | Start the chat web UI (FastAPI + browser) |
| `clear` | Delete generated artifacts under `outputs/` |

Show top-level help:

```bash
python -m mito_data_agent --help
```

### `agent` — run from the CLI

```bash
# Prompt from a file (examples/ has .md templates)
python -m mito_data_agent agent --prompt-file examples/upload_prompt.md

# Inline prompt
python -m mito_data_agent agent --prompt "List my local annotated volumes"

# Print LangGraph node-by-node trace
python -m mito_data_agent agent --prompt-file examples/freeform_upload_prompt.md --trace

# LLM backend / model
python -m mito_data_agent agent --llm-backend openai --model gpt-4.1 --prompt "..."
python -m mito_data_agent agent --llm-backend codex_cli --prompt-file examples/freeform_upload_prompt.md

# Clear outputs first, then run (or clear only with no prompt)
python -m mito_data_agent agent --clear-outputs -y
python -m mito_data_agent agent --clear-outputs -y --prompt-file examples/upload_prompt.md

# Optional rule-based parser fallback if LLM fails (not recommended)
python -m mito_data_agent agent --allow-rule-based-fallback --prompt-file examples/upload_prompt.md
```

| Flag | Purpose |
|------|---------|
| `--prompt TEXT` | User prompt string |
| `--prompt-file PATH` | Read prompt from file |
| `--trace` | Print LangGraph step trace to the terminal |
| `--llm-backend {openai,codex_cli}` | LLM backend (default from config / env) |
| `--model NAME` | OpenAI model name |
| `--allow-rule-based-fallback` | Use rule-based parser if LLM unavailable |
| `--clear-outputs` | Wipe `outputs/` then exit (or continue if a prompt is given) |
| `-y`, `--yes` | Skip confirmation for `--clear-outputs` |

### `web` — chat UI

```bash
python -m mito_data_agent web
# Open http://127.0.0.1:7860

python -m mito_data_agent web --host 0.0.0.0 --port 8080
python -m mito_data_agent web --clear-outputs -y    # fresh outputs before start
python -m mito_data_agent web --trace               # enable trace for all chat runs
python -m mito_data_agent web --no-auto-port        # fail if default port is busy
```

| Flag | Purpose |
|------|---------|
| `--host HOST` | Bind address (default: `127.0.0.1`) |
| `--port PORT` | Port (default: `7860`; auto-increments if busy unless `--no-auto-port`) |
| `--clear-outputs` | Wipe `outputs/` before starting the server |
| `-y`, `--yes` | Skip confirmation for `--clear-outputs` |
| `--trace` | Set `MITO_AGENT_TRACE=1` for streaming step traces in the UI |
| `--no-auto-port` | Do not try the next port when the requested one is in use |

LLM connection (OpenAI / Codex) is configured in the web UI sidebar; settings are stored under `outputs/logs/llm_connection.json`.

### `clear` — reset run artifacts

```bash
python -m mito_data_agent clear          # interactive confirm
python -m mito_data_agent clear -y       # no prompt
```

Removes everything under `outputs/` except subdirectory `.gitkeep` files (`hf_staging/`, `mitoverse_updates/`, `execution_reports/`, `logs/`, `cache/`).

## Web chat UI

A simple OpenClaw-style chat interface is included. Type your prompt in the conversation panel and the agent runs the same LangGraph workflow (dry-run only).

```bash
python -m mito_data_agent web
# Open http://127.0.0.1:7860
```

## Folder structure

```
mito_data_agent/
  README.md
  pyproject.toml            # package config + console scripts
  requirements.txt          # legacy; prefer pip install -e .

  examples/                 # Example user prompts (.md)
  outputs/                  # Generated at runtime (gitignored except .gitkeep)
  tests/

  src/mito_data_agent/      # All application code lives here
    __main__.py             # python -m mito_data_agent <command>
    cli/                    # Command-line entry points (agent, web, clear)
    web/                    # FastAPI server + chat UI static files
    graph.py                # LangGraph workflow
    nodes.py                # Thin node wrappers
    state.py                # Shared graph state
    schemas.py              # Pydantic models
    config.py               # Safety flags and constants
    runner.py               # Shared agent runner (CLI + web)
    llm/                    # LLM client + prompt templates
    prompts/                # System prompts (.md)
    tools/
      parse_prompt_llm.py   # LLM-first parser
      parse_prompt_fallback.py  # Optional fallback only
    utils/                  # Helpers (paths, prompts, io, …)
```

## LangGraph flow

```
User prompt
  ↓
validate_input
  ↓
parse_user_prompt
  ↓
route_intent
  ├── upload_annotation → inspect → extract observations → merge → validate
  │       ├── valid → HF staging → MitoVerse update → pseudo HF → pseudo GitHub → report
  │       └── missing → missing-fields report
  ├── metadata_only_update → merge → validate
  │       ├── valid → MitoVerse update → pseudo GitHub → report
  │       └── missing → missing-fields report
  ├── check_upload_readiness → inspect → extract → merge → validate → readiness report
  └── unsupported_request → unsupported report
```

## Important state objects

| State field | Purpose |
|---|---|
| `parsed_request` | Structured fields extracted from the user prompt |
| `file_inspection` | Low-level file existence and shape checks |
| `volume_observation` | Extracted Resolution, Shape, and # Mito from files |
| `merged_metadata` | Combined prompt + observations before validation |
| `schema_validation` | Whether required MitoVerse columns are satisfied |
| `hf_upload_plan` | Pseudo HF upload dry-run plan |
| `github_push_plan` | Pseudo GitHub push dry-run plan |

## Why `volume_observation` matters

The three file-derived MitoVerse columns should come from actual data when possible:

- **Shape (x,y,z)** — from raw/label TIFF array dimensions (label preferred on conflict)
- **# Mito** — count of unique non-zero labels in the mask file
- **Resolution (nm)** — from a JSON metadata file (`resolution_nm` or `voxel_size_nm`), else from the prompt

File-derived values override prompt values during merge.

## Data directory

Annotated volumes live in **`../mito_data_agent_data`** (sibling to this repo; override with `MITO_AGENT_DATA_DIR` or see `DEFAULT_DATA_DIR` in `config.py`):

- Raw: `vol1_0000.tiff`
- Label: `vol1.tiff`

Example prompts in `examples/` reference these paths.

## LLM setup (required)

### Option A: OpenAI API

```bash
export OPENAI_API_KEY=sk-...
export MITO_AGENT_LLM_MODEL=gpt-4.1   # or gpt-5.5 if available in your environment

pip install -e ".[dev]"
python -m mito_data_agent agent --prompt-file examples/freeform_upload_prompt.md --trace
```

### Option B: Codex CLI

```bash
codex login
export USE_CODEX_CLI=true
export MITO_AGENT_LLM_BACKEND=codex_cli

python -m mito_data_agent agent --prompt-file examples/freeform_upload_prompt.md --trace
```

### Optional fallback (not recommended)

```bash
python -m mito_data_agent agent --allow-rule-based-fallback --prompt-file examples/upload_prompt.md
```

If no LLM is configured and fallback is disabled, the agent fails with:
`No LLM backend available. This MVP requires LLM prompt parsing.`

## Expected outputs

After a successful upload run (written under `outputs/`, not committed to git):

- `outputs/hf_staging/<volume>/metadata.json`
- `outputs/hf_staging/<volume>/manifest.json`
- `outputs/hf_staging/<volume>/README.md`
- `outputs/mitoverse_updates/<volume>_row.json`
- `outputs/mitoverse_updates/<volume>_row.csv`
- `outputs/mitoverse_updates/<volume>_site_update_patch.md`
- `outputs/execution_reports/<run_id>.json`

## External writes (stub tools)

Upload/push tools (`pseudo_upload_hf`, `pseudo_push_github`) are **stub implementations**: they validate inputs and return a plan with `real_write_performed=false`. They do not call Hugging Face or GitHub APIs. When the agent is stable, swap these modules for real implementations (see `ALLOW_REAL_*` flags in `config.py`).
