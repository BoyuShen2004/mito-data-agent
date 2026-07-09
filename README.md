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

## Data storage

Large image data is **never** stored in the database. Set `MITO_DATA_ROOT` to a
directory on your HPC/lab machine; the DB stores only paths (relative to that
root) for image volumes, optional initial labels, submitted labels, and future
chunks/predictions/exports.

## Backend — setup & run

```bash
cd backend
pip install -r requirements.txt          # Django, DRF, corsheaders, numpy, tifffile
cp .env.example .env                      # then edit MITO_DATA_ROOT etc.
python manage.py migrate
python manage.py createsuperuser          # a superuser is treated as a manager
python manage.py runserver                # http://127.0.0.1:8000
```

Seed a demo project/user/volume for manual testing:

```bash
python manage.py shell < scripts/seed_demo.py
# creates: manager/demo12345 (manager) and alice/demo12345 (annotator)
```

### Key settings (`config/settings.py`)

- `MITO_DATA_ROOT` — root for all volume/label/submission files.
- `MITO_ALLOWED_LABEL_EXTENSIONS` — allowed uploaded-label extensions (QC).
- `MITO_DEFAULT_Z_STEP` — default frames per task when splitting.
- `CORS_ALLOWED_ORIGINS` — defaults to the Vite dev server (`:5173`).

## Frontend — setup & run

```bash
cd frontend
npm install
npm run dev                               # http://localhost:5173
```

The dev server proxies `/api` and `/media` to the Django backend
(`http://127.0.0.1:8000` by default; override with `VITE_BACKEND_URL`).
`npm run build` typechecks and produces a production bundle in `dist/`.

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
python manage.py split_volume --volume-id 1 --z-step 16
python manage.py assign_tasks --project-id 1
python manage.py progress_report --project-id 1
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
cd backend && python manage.py test
```

## Not yet implemented (deliberately out of scope)

Online annotation editor / image viewer, nnU-Net / PyTorch-Connectomics
integration, Slurm jobs, advanced QC, real payment processing, client billing,
Hugging Face / MitoVerse publishing, and the full LangGraph multi-agent system.
The `agents` app ships only an `AgentPlan` placeholder model + endpoints.
