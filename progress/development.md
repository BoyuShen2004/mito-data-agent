# Development

## Run it

```bash
cd /projects/weilab/shenb/mito-data-agent
conda activate mito-data-agent
./dev-setup.sh     # first run, or after pulling dependency/model changes
./dev-launch.sh     # every time after that — frees stale :8000/:5173 first, then starts
```

Then open **http://localhost:5173**.

`./dev-setup.sh` verifies tooling and backend deps, creates `.env` from
`.env.example` on first run (never overwriting an existing one), installs
frontend deps only when they changed, and runs Django checks + migrations.
Safe to re-run any time — it does nothing when everything is already current.

`./dev-launch.sh` skips all of that and just starts **both** servers (a few
instant existence checks first), stopping everything on one **Ctrl+C**. This
is what you run for the normal edit/relaunch loop.

Ordinary code changes (React, CSS, Django views/serializers/services/tests) need
no setup step — save and the dev servers reload. `npm install` re-runs only when
`frontend/package*.json` change or `frontend/node_modules` is missing.

Visiting **http://127.0.0.1:8000/** hits the API server (a small landing page),
not the app — the UI is **http://localhost:5173**.

### First-time environment (only if the conda env doesn't exist yet)

```bash
conda env create -f environment.yml   # Python 3.11 + Node + backend deps
conda activate mito-data-agent
```

Prefer pip? Python ≥ 3.11 and Node ≥ 18, then `pip install -r requirements.txt`.
There is no `setup.sh`.

### Run the two processes by hand (debugging)

```bash
python backend/manage.py runserver          # API on http://127.0.0.1:8000
npm run dev --prefix frontend               # UI on http://localhost:5173
```

## Configuration (`.env`)

`.env` at the repo root (copied from `.env.example`) drives the backend:

- `MITO_DATA_ROOT` — root dir for all volume/label/submission files. The DB
  stores only paths relative to this root, **never** the image data. A relative
  value resolves against the repo root (so `./data` means `<repo>/data`).
- `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` — standard Django.
- `DJANGO_CORS_ORIGINS` — browser origins allowed to call the API.
- `MITO_DEFAULT_Z_STEP` — default frames per task when splitting.

Everything else is in `backend/config/settings.py`.

## Dev data & accounts

Standard accounts (password `demo12345`): `manager` (manager) and `alice`,
`bob`, `carol`, `dave` (annotators). **No data is pre-registered** — register
datasets yourself in the app (as the manager, or sign up a requester).

```bash
cd backend
python manage.py seed_dev            # create the standard accounts (no data)
python manage.py seed_dev --fresh    # clear existing data first, then seed
python manage.py dev_status          # counts of current data
python manage.py clear_dev_data      # delete dev data (prompts; --no-input to skip)
python manage.py clear_dev_data --keep-users
python manage.py reset_dev           # clear + migrate + reseed accounts (one shot)
```

`clear_dev_data` / `reset_dev` always preserve superusers and refuse to run when
`DEBUG=False` unless given `--force`. Both also wipe **everything under
`MITO_DATA_ROOT`** (registered uploads, submission files, and every
project/dataset's in-app working label copy — not just database rows). Automated tests build
their own throwaway data (in a tempdir `MITO_DATA_ROOT` override) and are
independent of these commands. In development the login page shows a
click-to-fill list of these accounts (dev builds only), plus a "Clear all
data & reset" button that calls the same `clear_dev_data` through
`POST /api/dev/reset/`.

Create the Manager Admin superuser with `python manage.py createsuperuser` (see
[admin.md](admin.md) for how manager accounts get admin access).

## Workflow CLIs

```bash
python backend/manage.py split_volume --volume-id 1 --z-step 16
python backend/manage.py assign_tasks --project-id 1
python backend/manage.py progress_report --project-id 1
```

These are thin wrappers over the service layer (same logic as the SPA/admin).

## Tests & build

```bash
cd backend && python manage.py test        # backend (run from backend/)
python backend/manage.py check             # system checks
npm run build --prefix frontend            # frontend typecheck (tsc) + build
```

See [codemap.md](codemap.md#where-the-tests-live) for which tests cover what.

## Providers & processing jobs

Replaceable integrations are chosen by env/settings (see
[codemap.md](codemap.md#one-replaceable-feature--one-folder) for the folders):

```bash
MITO_QC_PROVIDER=basic                 # annotation/quality_control/
MITO_PROOFREADING_PROVIDER=placeholder # annotation/proofreading/
MITO_VISUALIZATION_PROVIDER=placeholder# annotation/visualization/
MITO_PUBLISHING_PROVIDER=placeholder   # annotation/publishing/
MITO_PROCESSING_BACKEND=local          # processing/adapters/{local,slurm}.py
```

Heavy work runs as `ProcessingJob` rows, never inside a request. Run the
dispatcher to execute queued jobs:

```bash
cd backend
python manage.py run_processing_dispatcher --once     # single pass (local backend by default)
python manage.py run_processing_dispatcher            # loop
```

**SLURM** (`MITO_PROCESSING_BACKEND=slurm`) reads all cluster-specific values
from the environment — nothing is hard-coded:

```bash
MITO_SHARED_STORAGE_ROOT=/shared/mito
MITO_SLURM_PARTITION=gpu
MITO_SLURM_ACCOUNT=weilab
MITO_SLURM_SBATCH=sbatch   # + MITO_SLURM_SQUEUE / SACCT / SCANCEL
```

No real cluster is needed for local development or tests (the `local` backend
simulates jobs). The per-job command/script goes in `job.config['command']`.

## Remote / HPC access

The servers bind to localhost by default. Forward the port over SSH:

```bash
ssh -L 5173:localhost:5173 <username>@<server>   # then open http://localhost:5173
```

…or bind to all interfaces and skip auto-opening a browser:

```bash
VITE_HOST=0.0.0.0 DJANGO_HOST=0.0.0.0 NO_BROWSER=1 ./dev-launch.sh
```

Overrides (defaults): `DJANGO_HOST=127.0.0.1`, `DJANGO_PORT=8000`,
`VITE_HOST=127.0.0.1`, `VITE_PORT=5173`, `NO_BROWSER=0`. Docker is not required
and no graphical desktop is assumed.

## Visualization + in-app annotation

The SPA has a built-in **slice viewer** (`frontend/src/features/viewer/`) that
streams PNG slices from the server's slice-IO layer
(`backend/annotation/visualization/slice_io.py`). Volumes are opened as
**memory-maps** and only the current slice (plus prefetched neighbours) is read,
windowed, and PNG-encoded; the client keeps object URLs in a **bounded LRU**
(256, mirroring Cellable's `MAX_SLICE_PIXMAP_CACHE`). This keeps both server RAM
and browser memory flat regardless of volume size.

Providers (defaults now `inapp`):

- `MITO_VISUALIZATION_PROVIDER=inapp` → in-app slice viewer (`/viewer/...`).
- `MITO_PROOFREADING_PROVIDER=inapp` → in-app editor launch (`/editor/tasks/<id>`).

Role gating (enforced in `annotation/services.py`, not just the UI):

- **requester (Institution)** → view only; the launch is downgraded to
  `editable=false` and mutation endpoints return `403`.
- **manager / assigned annotator** → View **and** Annotate entry points.
- requester + annotator read the **same** task labels, so both monitor live
  progress off one source of truth.

## Fork-aware SAM2 tracking on GPU nodes

SAM2 tracking (`backend/annotation/tracking/`) ports the MTS multi-branch
approach. When a mitochondrion **forks**, each 8-connected branch is seeded as
its own temporary track id, all branches are kept in one `TrackGroup`, and after
propagation the group is **auto-merged into one final instance id**
(`annotation.tracking.services.run_branch_tracking`). Branch ids, the final id,
and group membership are persisted in `volume.metadata['tracking_groups']` for
audit / undo / re-run.

Providers (`MITO_TRACKING_PROVIDER`):

- `local` (default) — dependency-free CPU stand-in for dev/CI (no GPU, no torch).
- `sam2` — the real GPU model
  (`annotation/tracking/adapters/sam2.py` + `sam2_bridge.py`, the latter a
  self-contained port of `MTS/mts_mask_editor/core/sam2_wrapper.py`). It is
  heavy and **must run on a GPU compute node**, never inside the web process.

  The model + weights are **vendored into this repo** at `vendor/sam2/` (a
  full copy of facebookresearch/sam2 + downloaded checkpoints — see
  `vendor/README.md` for provenance), not read from any external `MTS`
  checkout — `MITO_SAM2_ROOT`/`_CHECKPOINT`/`_CONFIG` already default to
  that vendored copy in `config/settings.py`, so no `.env` changes are
  needed to point at it. To actually run it:

  ```bash
  # On the GPU node, into the same mito-data-agent conda env:
  pip install torch>=2.5.1 torchvision>=0.20.1   # match your CUDA build, see pytorch.org
  pip install -r requirements-sam2.txt
  export MITO_TRACKING_PROVIDER=sam2
  # MITO_SAM2_ROOT/_CHECKPOINT/_CONFIG only need overriding if you want a
  # different checkpoint (defaults to the smallest/fastest, tiny) or keep
  # the checkout somewhere else — see .env.example.
  ```

On the cluster, dispatch tracking through the existing processing backend
(`MITO_PROCESSING_BACKEND=slurm`) so the GPU work lands on a compute node via
`sbatch` (bind + tunnel like MTS), while the web tier only creates/polls the job.
For local development the `local` provider runs inline and needs no GPU.

## Cellable-ported interactive AI tools (Point Mask / Box Mask / Boundary / Seeds)

`backend/annotation/cellable_port/` (see that app's `MODULE.md` for what's
ported from where). Unlike SAM2 tracking above, this is **CPU-only and
lightweight** — no torch, no GPU required, safe to install in any dev
environment:

```bash
pip install -r requirements-cellable-ai.txt   # onnxruntime, scikit-image, scipy
```

Model weights are **not vendored** into this repo (unlike `vendor/sam2/`) —
`MITO_CELLABLE_MODELS_ROOT` defaults straight to the sibling cellable
checkout's `labelme/models/*.onnx` files (`config/settings.py`), since
they're plain data files already present on the same filesystem, not a code
dependency to pin/version. `MITO_EFFICIENT_SAM_VARIANT` defaults to
**`vits`** ("EfficientSam (accuracy)") — the same weight tier Cellable
itself defaults to, so a click on the same slice should produce close to
the same mask. Set `vitt` (tiny/fast) yourself if you explicitly want to
trade accuracy for speed.

**Two things had to match for masks to actually agree with local Cellable**
(a prior round shipped
`vitt` as a "CPU-friendly" default and fed the encoder a differently-
normalized image, and the user correctly rejected that as not parity):
1. **The weight tier** — `vits`, as above.
2. **The image preprocessing fed to the encoder** —
   `cellable_port/ai/normalize.py`'s `normalize_for_ai` ports Cellable's own
   `normalizeImg` exactly (per-slice, non-zero-pixel 1st/99.5th percentile
   stretch), which is a *different* function from `slice_io.display_range`
   (whole-volume, display-stable, used for the JPEG/PNG streaming
   endpoints) — conflating the two was a real, independent source of mask
   divergence. Observed on a real registered EM volume during verification:
   the exact same point at the exact same weight tier went from "~95% of
   the whole slice" (using `display_range`) to "~0.07% of the slice, a
   tight blob" (using `normalize_for_ai`) — confirming this was the
   dominant bug, not the weight tier alone.

Without the optional dependency installed (or without the model files
present), Point Mask / Box Mask / Boundary degrade to a clear `503`
response (`cellable_port/ai/registry.py`'s `AiUnavailable`) rather than a
crash — Seeds/watershed and every other tool work regardless, since
watershed only needs scipy/scikit-image, not the AI model.

**On a SLURM node, onnxruntime used to flood the terminal** with
`pthread_setaffinity_np failed ... Invalid argument` — harmless (predict
still returned `200`) but noisy: onnxruntime sizes its thread pool from the
node's *physical* core count by default, then tries to pin threads to CPUs
outside a `-c N`-restricted cgroup's affinity mask. Fixed by building
both the encoder and decoder `InferenceSession`s with explicit
`SessionOptions` (`efficient_sam.py`'s `_resolve_thread_count`/
`_session_options`) — reads `SLURM_CPUS_PER_TASK` first, then
`os.sched_getaffinity(0)` (the real, cgroup-aware count), then
`os.cpu_count()`, capped at 8. No `.env`/launcher change needed; if you want
to override the cap for experimentation, set `ORT_NUM_THREADS`/
`OMP_NUM_THREADS` in the environment before starting the server — those are
generic onnxruntime/OpenMP knobs this app doesn't read itself, but they can
still influence the underlying execution provider alongside the explicit
`SessionOptions` above.

**On-disk embedding cache** (`cellable_port/ai/embed_cache.py`, ported idea
from Cellable's `pre_compute_tiff_sam_feature.py`): the encoder's output for
a given (volume, axis, index, model variant) is cached under
`MITO_DATA_ROOT/embeddings/<variant>/volume_<id>/<axis>_<index>_<mtime>.npy`
— a fresh Django process (not just a warm in-process LRU) can reuse it, so
revisiting a slice after restarting the dev server still gets a fast,
decoder-only predict. The image's mtime is baked into the filename
specifically so a re-registered/replaced source image can never be served a
stale embedding by accident. Cleared automatically by `clear_dev_data`
("Reset dev data") along with everything else under the data root — nothing
extra to do.

## Annotate hotkeys

`frontend/src/features/viewer/AnnotationCanvas.tsx` — moved here (and into
`progress/frontend/features/MODULE.md`) from a permanent footer line under
the canvas, deliberately removed to
give the canvas viewport that row's height back. All hotkeys are still
live — this is the map, not a UI change.

| Key | Action |
| --- | --- |
| `V` | Select (eyedropper — pick the clicked instance) — **default tool** |
| `B` | Brush |
| `E` | Erase (circular) |
| `R` | Box Erase |
| `P` | Point Mask |
| `M` | Box Mask |
| `O` | Boundary |
| `T` | Seeds (3D watershed) |
| `Enter` | Commit the current AI proposal (Point/Boundary: re-predicts committed-points-only first, discarding any live cursor tip — see `26`/`27`/`28`) |
| `Escape` | Clear the AI proposal/prompt points (all of Point/Box/Boundary, including an in-progress Box drag) |
| `Ctrl/Cmd+click` (Point/Boundary) | Add this point, then immediately commit |
| Double-click (Point/Boundary) | Commit the current proposal |
| `Alt+click` an existing prompt point (Point/Boundary) | Remove just that point, re-predict |
| Drag an existing prompt point (Point/Boundary) | Move it, re-predict live while dragging + once more on release |
| `Shift+click`/hover (Point/Boundary) | Negative prompt point |
| `F` | Verify the active label |
| `Shift+R` | Revert the active label to its proposed snapshot (only if `can_revert`) |
| `Delete` | Reject (delete) the active label from the whole volume — behind the same confirm dialog the Filters Options button uses |
| `H` | Toggle Hide Verified |
| `S` | Solo the active label |
| `Shift+S` | Show all (clear solo/hidden) |
| `Ctrl/Cmd+Z` / `Ctrl/Cmd+Shift+Z` | Undo / redo |
| `A`/`D` or `←`/`→` | Previous/next z-slice |
| Wheel over the canvas | Change z-slice (throttled ~40ms) |
| `Ctrl/Cmd+wheel` | Zoom |
| Right-click on the canvas | Minimal context menu — mode switches, plus Verify/Solo if over a label |

All hotkeys are disabled while the "Swap 3D ↔ Canvas" view is active, except the label-lifecycle ones
(`F`/`Shift+R`/`Delete`/`H`/`S`/`Shift+S`), which mirror the always-enabled
Filters Options buttons and aren't "annotate edit" in the painting sense —
Undo/Redo *are* blocked even via keyboard in that state, since they mutate
the raster the same way painting does.
