# Mito Data Agent

A **supervisor-based multi-agent LangGraph** system for prompt-driven MitoVerse
dataset metadata recording and upload preparation.

## What it is

You describe your annotated mitochondria volume(s) in a free-form prompt. An
**LLM parses** the prompt, an **LLM supervisor** routes the work step by step, and
a set of specialized agents inspect the files, reconcile metadata against what the
files actually contain, record everything to a queryable store, and prepare
dry-run artifacts for Hugging Face / MitoVerse.

It is **fully agentic**: both prompt understanding and routing are LLM-driven —
there is no rule-based fallback in the product.

> **All external writes are pseudo / dry-run.** No real Hugging Face upload or
> GitHub push happens (`real_write_performed=False`). Local writes are limited to
> `outputs/` and per-volume metadata sidecars in your data directory.

## Architecture

```
START
  ↓
supervisor_agent  ← ─────────────────────────┐
  ↓ (LLM decides the next agent each turn)    │
  ├── input_parser_agent  ────────────────────┤
  ├── dataset_inspector_agent  ───────────────┤
  ├── observation_agent  ─────────────────────┤
  ├── metadata_agent  ────────────────────────┤
  ├── validation_agent  ──────────────────────┤
  ├── metadata_record_agent  ─────────────────┤
  ├── staging_agent  ─────────────────────────┤
  ├── upload_planning_agent  ─────────────────┤
  ├── website_update_agent  ──────────────────┤
  ├── inventory_agent  ───────────────────────┤
  ├── catalog_agent  ─────────────────────────┤
  ├── storage_info_agent  ────────────────────┤
  ├── report_agent  ──────────────────────────┘
  └── finish → END
```

- **`START` → `supervisor_agent`** is the only entry point. Every agent is
  dispatched by the supervisor and returns to it, so all work flows through one
  uniform loop.
- **Supervisor = LLM** (`agents/supervisor_llm.py`). Each turn it gets the user
  request, the agent catalog, and a progress snapshot, and returns
  `{next_agent, reason, confidence}`. On an LLM outage/timeout a safety net keeps
  the run from crashing (retries, then advances by data dependency).
- **Agents are thin flow.** All output *formatting* lives in tools
  (`tools/reporting.py`), not in the agent modules.
- **Trace channels.** Every worker appends to `agent_trace`; every routing
  decision appends to `supervisor_decisions`.

### Design conventions

- Agent modules (`agents/`) contain **flow only** — no hardcoded output formats.
- Anything that formats, parses, reads files, or renders lives in **`tools/`**
  (e.g. `tools/reporting.py` owns the report text, JSON, CLI summary).
- All paths are config/helper-driven (`config.DEFAULT_DATA_DIR`,
  `utils/paths.py`); no machine-specific absolute paths.

## What the agent does

- **Parses free-form prompts** into structured metadata (LLM), including
  **multiple datasets in one prompt** (each recorded separately).
- **File info wins over the prompt.** When the prompt and the actual TIFF disagree
  on shape / # Mito / resolution, the file value is used and the conflict is
  logged.
- **Records metadata** to a persistent, queryable ledger
  (`outputs/metadata_store/records.json`) **and** a sidecar next to the data
  (`<data_dir>/<volume>.metadata.json`).
- **Answers "where do you keep things?"** and **"what have I recorded?"**
- **Prepares dry-run artifacts**: HF staging, MitoVerse update rows, pseudo
  upload/push plans.
- **Looks up** whether a volume already exists in the public MitoVerse catalog.

## Install

```bash
cd mito_data_agent
pip install -e ".[dev]"
```

## LLM setup (required)

The agent needs an LLM backend for parsing and routing.

**OpenAI (recommended — fast, reliable):**
```bash
export OPENAI_API_KEY=sk-...
export MITO_AGENT_LLM_BACKEND=openai
export MITO_AGENT_LLM_MODEL=gpt-4.1
```

**Codex CLI (local, no API key):**
```bash
codex login
export MITO_AGENT_LLM_BACKEND=codex_cli
```
> Note: Codex makes one CLI call per routing step, so multi-step runs are slow;
> OpenAI is much faster.

## CLI

Everything runs through `python -m mito_data_agent <command>`.

| Command | Description |
|---------|-------------|
| `run` | Run the multi-agent workflow on a prompt |
| `records` | Query the recorded-metadata store |
| `reconcile` | Rename stored records/sidecars to match on-disk data files |
| `web` | Serve the web UI |
| `clear` | Delete generated artifacts under `outputs/` |

### `run`

```bash
# Inline prompt, with the supervisor/agent trace
python -m mito_data_agent run --prompt "Record metadata for vol1 ..." --trace

# From a file
python -m mito_data_agent run --prompt-file prompts/examples/upload_prompt.md
```

| Flag | Purpose |
|------|---------|
| `--prompt TEXT` / `--prompt-file PATH` | The user request |
| `--trace` | Print the supervisor/agent trace |
| `--llm-backend {openai,codex_cli}` / `--model NAME` | Override the LLM backend/model |
| `--clear-outputs` / `-y` | Wipe `outputs/` first |

The CLI summary lists **every** recorded dataset (not just the first), and each
run writes `outputs/execution_reports/<run_id>.json`.

### `records` — query the metadata store

```bash
python -m mito_data_agent records                  # list all recorded volumes
python -m mito_data_agent records --volume vol1     # one record (+ version history)
python -m mito_data_agent records --organism Human  # filter by a metadata field
python -m mito_data_agent records --json            # raw JSON
```

Programmatic access:
```python
from mito_data_agent.tools.metadata_store import get_record, query_records
get_record("vol1")
query_records(organism="Human", modality="FIB-SEM")
```

### `web` — browser UI

```bash
python -m mito_data_agent web                 # http://127.0.0.1:7860
python -m mito_data_agent web --port 8000     # pick a port (auto-falls-back if busy)
```

A single-page UI (FastAPI backend, no build step). A left **chats sidebar** keeps
your **previous conversations** (persisted under `outputs/chats/`, newest first) —
click one to reopen it, use **＋ New chat** to start fresh, or hover to delete.
Two views:

- **Run** — a ChatGPT-style prompt composer with one-click example prompts. While
  the workflow runs, a **live trace streams in** step-by-step (supervisor routing →
  agent → component sub-steps) so you can watch the run progress; when it finishes
  the answer is rendered: a status strip (run id / intent / validation),
  **recorded-dataset cards** (with `file`-vs-`prompt` source tags), dry-run
  artifacts, warnings, **conflicts auto-resolved in favour of the file**, the full
  execution report, and the complete trace (toggle the header **Agent trace**
  switch to keep it visible after the run). `⌘/Ctrl+Enter` runs the prompt.
- **Records** — a searchable table over the metadata ledger.

The gear icon opens **LLM settings** (backend / model / OpenAI key / Codex path),
persisted to `outputs/logs/` so the UI works without env vars. Every run is
dry-run — nothing is uploaded or pushed.

### `reconcile` — make stored names match the data files

```bash
python -m mito_data_agent reconcile --dry-run   # preview
python -m mito_data_agent reconcile             # apply
```

Renames any recorded volume + its `<name>.metadata.json` to the actual on-disk
file stem (e.g. `MitoHardLiver` → `jrc_mus-liver_recon-1_test0`) when the data
files can be located (via file paths or a `provenance`/name hint), backfilling
the raw/label paths and removing the stale sidecar. The `dataset` name and
version history are preserved. This is the batch/repair counterpart to the
silent per-run naming resolution done during `run`.

### `clear`

```bash
python -m mito_data_agent clear -y   # wipe outputs/ (keeps folder structure)
```

Clears run artifacts and the recorded-metadata ledger. **Chat history
(`outputs/chats/`) is preserved** — it is not part of the cleared set.

## Project layout

```
mito_data_agent/
  pyproject.toml
  prompts/
    system/parse_user_request.md     # LLM system prompt (parsing)
    examples/*.md                    # example user prompts
  outputs/                           # generated at runtime (gitignored)
    execution_reports/  metadata_store/  hf_staging/  mitoverse_updates/  logs/  cache/
  src/mito_data_agent/
    __main__.py                      # python -m mito_data_agent <command>
    cli/                             # run, records, web, clear
    web/                             # FastAPI backend + single-page UI (static/index.html)
    agents/                          # the multi-agent workflow (FLOW only)
      supervisor_llm.py              #   LLM router
      supervisor_agent.py            #   supervisor node + safety net
      *_agent.py                     #   worker agents (wrap tools)
      graph.py / state.py / registry.py
    tools/                           # all real work + formatting
      reporting.py                   #   report text / JSON / CLI summary
      metadata_store.py              #   persistent ledger + data-dir sidecars
      reconcile_metadata.py          #   file-wins-over-prompt reconciliation
      parse_prompt*.py, inspect_files.py, merge_metadata.py, validate_metadata.py,
      generate_*.py, pseudo_*.py, *_mitoverse_*.py, list_local_data.py
    llm/                             # LLM client + prompt templates + settings
    tasks/                           # intent taxonomy for the parser
    schemas.py, config.py, utils/
```

## Metadata recording

Every run that produces metadata records it in two places:

1. **Ledger** — `outputs/metadata_store/records.json` (accumulates across runs,
   keeps a version history per volume; query with `records`).
2. **Sidecar** — `<data_dir>/<volume>.metadata.json` next to the raw/label TIFFs
   (`data_dir` = `config.DEFAULT_DATA_DIR`, default `../mito_data_agent_data`,
   override with `MITO_AGENT_DATA_DIR`).

Multiple datasets in one prompt are all recorded. File-derived values override
conflicting prompt values (with a warning).

## Expected outputs

- `outputs/metadata_store/records.json` — the queryable ledger
- `<data_dir>/<volume>.metadata.json` — per-volume sidecars
- `outputs/execution_reports/<run_id>.json` — full run record (trace + report)
- `outputs/hf_staging/<volume>/…`, `outputs/mitoverse_updates/<volume>_row.{json,csv}` — dry-run artifacts

## Dry-run only

The HF/GitHub tools (`tools/pseudo_upload_hf.py`, `tools/pseudo_push_github.py`)
validate inputs and return a plan with `real_write_performed=false`. They do not
call any external API. Swap them for real implementations when ready (see
`ALLOW_REAL_*` flags in `config.py`).
