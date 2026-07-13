# Mito Data Agent

A web-based **mitochondria annotation task-management platform** with three
roles. **Requesters** register datasets (references to `.tif`/`.tiff`/`.nii.gz`
files on HPC storage) and track progress on their projects. **Managers** create
projects, split volumes into frame-based tasks, and manually assign or reassign
work to annotators. **Annotators** work on and submit their assigned tasks. The
system tracks task status, project progress, and annotator workload. Annotation
work is unpaid — there is no payment/wage tracking.

**Architecture.** A **React + Vite + TypeScript** single-page app talks to a
**Django + Django REST Framework** backend over a token-authenticated JSON API.
The two run as separate processes in development (Vite proxies `/api` and
`/media` to Django); `./dev.sh` starts and stops both together. Django admin is
retained for internal debugging only — it is not the user-facing UI.

## Quick start

```bash
cd /projects/weilab/shenb/mito-data-agent
conda activate mito-data-agent
./dev.sh
```

Then open **http://localhost:5173**.

`./dev.sh` is the single command you need. It:

- verifies Python / Node / npm and the backend dependencies,
- creates `.env` from `.env.example` on first run (never overwrites an existing one),
- installs frontend dependencies only when they are missing or have changed,
- runs Django system checks and applies migrations,
- starts **both** the Django API and the React dev server,
- prints the URL to open, and
- stops everything cleanly with a single **Ctrl+C**.

**First startup** may install missing frontend dependencies and take a minute;
**later startups are fast** because unchanged dependencies are skipped. You only
need **one terminal**. Ordinary code changes (React components, CSS, Django
views, serializers, services, tests) do **not** require any setup step — just
save and the dev servers reload. `npm install` runs again only when
`frontend/package.json` / `frontend/package-lock.json` change or
`frontend/node_modules` is missing.

### First-time setup (only if the conda environment does not exist yet)

```bash
conda env create -f environment.yml   # Python 3.11 + Node + backend deps
conda activate mito-data-agent
```

Prefer plain pip? Use Python ≥ 3.11 and Node ≥ 18, then
`pip install -r requirements.txt`. There is **no** separate `setup.sh` to run —
`./dev.sh` handles everything routine.

Optionally load the standard mock dataset for a ready-to-click walkthrough:

```bash
cd backend && python manage.py seed_dev
# creates (password demo12345): manager (manager), alice + bob (annotators),
# lab_requester (requester), a registered demo dataset, tasks, and a submission.
```

See **Developer commands** below for clearing and resetting dev data.

## Remote / HPC use

The dev servers bind to localhost by default. To reach them from your laptop
when the app runs on a remote server, either forward the port over SSH:

```bash
ssh -L 5173:localhost:5173 <username>@<server>
# then open http://localhost:5173 locally
```

...or bind the servers to all interfaces and skip auto-opening a browser:

```bash
VITE_HOST=0.0.0.0 DJANGO_HOST=0.0.0.0 NO_BROWSER=1 ./dev.sh
```

Supported environment overrides (with defaults): `DJANGO_HOST=127.0.0.1`,
`DJANGO_PORT=8000`, `VITE_HOST=127.0.0.1`, `VITE_PORT=5173`, `NO_BROWSER=0`.
Docker is not required and no graphical desktop is assumed — if a browser cannot
be opened, the app still runs.

## Configuration

`.env` (copied from `.env.example` at the repo root) drives the backend:

- `MITO_DATA_ROOT` — root dir for all volume/label/submission files. The DB
  stores only paths relative to this root, **never** the large image data.
- `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` — standard Django.
- `DJANGO_CORS_ORIGINS` — browser origins allowed to call the API.
- `MITO_DEFAULT_Z_STEP` — default frames per task when splitting.

The defaults in `.env.example` work locally as soon as you copy it to `.env`.
Other backend settings live in `backend/config/settings.py`.

## Advanced / manual development

`./dev.sh` is the recommended workflow. For debugging you can still run the two
processes by hand in separate terminals:

```bash
# Terminal 1 — Django API on http://127.0.0.1:8000
python backend/manage.py runserver

# Terminal 2 — React UI on http://localhost:5173  ← open this
npm run dev --prefix frontend
```

Visiting **http://127.0.0.1:8000/** is the API server, not the app — it serves a
small landing page pointing to the UI at **http://localhost:5173**.

## Repository layout

```
backend/          Django + DRF API
  manage.py
  config/         settings, urls, wsgi/asgi
  accounts/       users, roles, institutions, annotator profiles
  projects/       annotation projects
  volumes/        image volumes + frame-based task splitting + data registration
  annotation/     tasks, submissions, review workflow
  core/           shared choices, storage, permissions, utils
frontend/         React + Vite + TypeScript SPA
  src/{api,components,pages,routes,types,hooks,auth}
docs/             REST API reference
```

## Workflow

1. A requester (or manager) opens **Register Data**, enters a **dataset** and
   **volume** name, selects an **HPC directory**, and registers the supported
   `.tif`/`.tiff`/`.nii.gz` files in it as chunks/crops. Optional biomedical
   metadata is collected; resolution/shape/mito counts are derived from files.
   This creates (or attaches to) an annotation project.
2. Manager splits a volume into frame-based tasks. The task type is inferred
   from the volume's **label type**:
   - `none` → `manual_annotation`
   - `prediction` → `prediction_proofreading`
   - `proofread` → `final_review`
   - `partial` → `manual_annotation` (manager may override)
3. Manager assigns tasks manually (per-task annotator dropdown) or via
   rule-based auto-assignment (respects each annotator's `max_active_tasks`).
   Reassignment updates the existing task in place.
4. Annotator logs in, views assigned tasks and their dataset metadata,
   downloads data externally, and uploads a completed label file. Basic QC runs
   on submit.
5. Manager reviews: **approve**, **reject**, or **request revision**.
6. Progress and workload update accordingly. All three roles can view the
   metadata for projects they are authorized to access.

## Service layer

Deterministic business logic lives in `<app>/services.py` (e.g.
`create_project`, `register_volume`, `register_dataset`, `scan_hpc_directory`,
`split_volume_by_frames`, `create_tasks_from_volume`, `assign_tasks_rule_based`,
`assign_task_to_annotator`, `submit_annotation`, `run_basic_qc`,
`review_submission`, `calculate_project_progress`,
`calculate_annotator_workload`). DRF views, admin actions, and management
commands all call these functions rather than reimplementing logic.

## Management commands

Workflow helpers:

```bash
python backend/manage.py split_volume --volume-id 1 --z-step 16
python backend/manage.py assign_tasks --project-id 1
python backend/manage.py progress_report --project-id 1
```

Developer data management (run from `backend/`, DEBUG-guarded):

```bash
python manage.py dev_status            # show counts of current data
python manage.py seed_dev              # load the standard mock dataset
python manage.py seed_dev --fresh      # clear first, then seed
python manage.py clear_dev_data        # delete dev data (prompts; --no-input to skip)
python manage.py clear_dev_data --files --keep-users
python manage.py reset_dev             # clear + migrate + reseed (one shot)
```

`clear_dev_data` / `reset_dev` always preserve superusers and refuse to run when
`DEBUG=False` unless given `--force`. `--files` also removes the mock TIFF
volumes written under `MITO_DATA_ROOT/dev_mock/`.

## REST API (selected)

| Method | Path | Purpose |
| ------ | ---- | ------- |
| POST | `/api/auth/login/` | obtain token (`portal` validates the login tab) |
| POST | `/api/auth/register/` | public signup (annotator / requester) |
| GET  | `/api/auth/me/` | current user |
| POST | `/api/hpc/scan/` | list supported files in an HPC directory |
| POST | `/api/register-data/` | shared data registration (requester + manager) |
| GET/POST | `/api/projects/` | list / create projects |
| GET | `/api/projects/<id>/summary/` | progress (+ workload for managers) |
| GET/POST | `/api/projects/<id>/volumes/` | list / register volumes |
| POST | `/api/volumes/<id>/split/` | frame-based task splitting |
| POST | `/api/projects/<id>/assign-tasks/` | rule-based assignment |
| POST | `/api/tasks/<id>/assign/` | manual (re)assignment (manager) |
| GET | `/api/my-tasks/` | annotator's assigned tasks |
| POST | `/api/tasks/<id>/submit/` | upload completed label |
| POST | `/api/submissions/<id>/review/` | approve / reject / request revision |

See `docs/api.md` for the full endpoint list.

## Tests

```bash
cd backend && python manage.py test    # backend (test discovery needs backend/ as cwd)
npm run build --prefix frontend        # typecheck + production build
```

## Not yet implemented (out of scope for the MVP)

Online annotation editor / image viewer, nnU-Net / PyTorch-Connectomics
integration, Slurm jobs, advanced QC, and Hugging Face / MitoVerse publishing.
Payments, wages, and billing are intentionally excluded — annotation work is
unpaid. Production deployment (serving a built
frontend from a single server) is future work — development intentionally keeps
Vite and Django as separate processes.
