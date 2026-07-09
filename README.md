# Mito Data Agent

A web-based **mitochondria annotation task-management platform**. Managers
create annotation projects, register image volumes, split them into
frame-based tasks, assign work to annotators, and review submitted labels.
The system tracks task status, project progress, annotator workload, and
estimated payment.

The app is a **React + Vite + TypeScript** single-page frontend talking to a
**Django + Django REST Framework** backend over a token-authenticated JSON API.
Django admin is retained for internal debugging only — it is not the
user-facing UI.

```
mito_data_agent/
├── backend/          Django + DRF API
│   ├── manage.py
│   ├── config/       settings, urls, wsgi/asgi
│   ├── accounts/     users, roles, institutions, annotator profiles
│   ├── projects/     annotation projects
│   ├── volumes/      image volumes + frame-based task splitting
│   ├── annotation/   tasks, submissions, review workflow
│   ├── payments/     estimated payment records
│   ├── agents/       AgentPlan placeholder (future LangGraph)
│   └── core/         shared choices, storage, services, permissions
├── frontend/         React + Vite + TypeScript SPA
│   └── src/{api,components,pages,routes,types,hooks,auth}
└── docs/
```

## Two servers (read this first)

This app runs as **two processes** during development:

| Process | URL | What it is |
| ------- | --- | ---------- |
| **Frontend** (React/Vite) | **http://localhost:5173** | 👈 **Open this** — the actual app |
| **Backend** (Django/DRF)  | http://127.0.0.1:8000 | JSON API + `/admin/` only |

> Opening **http://127.0.0.1:8000/** in a browser is **not** the app — it's the
> API server. It shows a small landing page pointing you to the UI. The user
> interface lives at **http://localhost:5173**. You need **both** servers
> running: the frontend calls the backend's API.

## Quick start

All commands below are run from the **repo root**
(`/projects/weilab/shenb/mito_data_agent`) — you do **not** need to `cd backend`.

Prerequisite: [conda](https://docs.conda.io/en/latest/miniconda.html)
(Miniconda/Anaconda). The environment provides Python 3.11, Node, and all
backend dependencies.

```bash
# 1. Create & activate the conda environment (Python 3.11 + Node + backend deps)
conda env create -f environment.yml
conda activate mito-data-agent

# 2. Configure (env file lives at the repo root)
cp .env.example .env                        # then edit MITO_DATA_ROOT

# 3. Backend: migrate + create a manager login
python backend/manage.py migrate
python backend/manage.py createsuperuser     # a superuser is treated as a manager

# 4. Frontend: install JS dependencies
npm install --prefix frontend
```

> To update the environment later after dependencies change:
> `conda env update -f environment.yml --prune`.
>
> **Prefer plain pip / venv instead of conda?** Use Python ≥ 3.11 and Node ≥ 18,
> then replace step 1 with `pip install -r requirements.txt`.

Then start **both** servers (use two terminals, or add `&` to the first):

```bash
# Terminal 1 — backend API on http://127.0.0.1:8000
python backend/manage.py runserver

# Terminal 2 — frontend UI on http://localhost:5173   ← open this in your browser
npm run dev --prefix frontend
```

Optionally seed a demo project/user/volume for a ready-to-click walkthrough:

```bash
python backend/manage.py shell < backend/scripts/seed_demo.py
# creates: manager/demo12345 (manager) and alice/demo12345 (annotator)
```

### Configuration

`.env` (copied from `.env.example` at the repo root) drives the backend:

- `MITO_DATA_ROOT` — root dir for all volume/label/submission files (DB stores
  only paths relative to this, **never** the large image data itself).
- `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` — standard Django.
- `MITO_DEFAULT_Z_STEP` — default frames per task when splitting.

Other settings live in `backend/config/settings.py`
(`MITO_ALLOWED_LABEL_EXTENSIONS`, `CORS_ALLOWED_ORIGINS` — defaults to `:5173`).

The Vite dev server proxies `/api` and `/media` to the backend
(`http://127.0.0.1:8000` by default; override with `VITE_BACKEND_URL`).
`npm run build --prefix frontend` typechecks and produces a production bundle.

## MVP workflow

1. Manager creates a project.
2. Manager registers/uploads an image volume, recording its **label type**
   (`none` / `prediction` / `proofread` / `partial`).
3. Manager splits the volume into frame-based tasks. The task type is inferred
   from the label type:
   - `none` → `manual_annotation`
   - `prediction` → `prediction_proofreading`
   - `proofread` → `final_review`
   - `partial` → `manual_annotation` (manager may override)
4. Manager assigns tasks manually or via rule-based auto-assignment (respects
   each annotator's `max_active_tasks`).
5. Annotator logs in, views assigned tasks, downloads data externally, and
   uploads a completed label file. Basic QC runs on submit.
6. Manager reviews: **approve** (creates/updates a payment record), **reject**,
   or **request revision**.
7. Progress, workload, and estimated payment update accordingly.

## Service layer

Deterministic business logic lives in `<app>/services.py` (e.g.
`create_project`, `register_volume`, `split_volume_by_frames`,
`create_tasks_from_volume`, `assign_tasks_rule_based`, `submit_annotation`,
`run_basic_qc`, `review_submission`, `calculate_project_progress`,
`calculate_annotator_workload`, `calculate_payment_summary`). DRF views, admin
actions, management commands, and future LangGraph tools all call these same
functions rather than reimplementing logic.

## Management commands

```bash
python backend/manage.py split_volume --volume-id 1 --z-step 16
python backend/manage.py assign_tasks --project-id 1
python backend/manage.py progress_report --project-id 1
```

## REST API (selected)

| Method | Path | Purpose |
| ------ | ---- | ------- |
| POST | `/api/auth/login/` | obtain token |
| GET  | `/api/auth/me/` | current user |
| GET/POST | `/api/projects/` | list / create projects |
| GET | `/api/projects/<id>/summary/` | progress + workload + payment |
| GET/POST | `/api/projects/<id>/volumes/` | list / register volumes |
| POST | `/api/volumes/<id>/split/` | frame-based task splitting |
| POST | `/api/projects/<id>/assign-tasks/` | rule-based assignment |
| GET | `/api/my-tasks/` | annotator's assigned tasks |
| POST | `/api/tasks/<id>/submit/` | upload completed label |
| POST | `/api/submissions/<id>/review/` | approve / reject / request revision |
| GET | `/api/payments/`, `/api/my-payments/` | payment records |

See `docs/api.md` for the full endpoint list.

## Tests

```bash
# From the repo root (Django's test discovery needs the app labels here
# because the apps live under backend/):
python backend/manage.py test accounts projects volumes annotation payments agents

# ...or simply run from the backend/ directory:
cd backend && python manage.py test
```

## Not yet implemented (deliberately out of scope)

Online annotation editor / image viewer, nnU-Net / PyTorch-Connectomics
integration, Slurm jobs, advanced QC, real payment processing, client billing,
Hugging Face / MitoVerse publishing, and the full LangGraph multi-agent system.
The `agents` app ships only an `AgentPlan` placeholder model + endpoints.
