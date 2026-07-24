# Mito Data Agent

A web-based **mitochondria annotation task-management platform** with three
roles:

- **Requesters** register datasets (references to `.tif`/`.tiff`/`.nii.gz` files
  on HPC storage) and track progress on their projects.
- **Managers** approve datasets, split volumes into tasks, and assign work to
  annotators.
- **Annotators** work on and submit their assigned tasks.

The system tracks task status, project progress, and annotator workload.
Annotation work is unpaid — there is no payment/wage tracking.

**Two front doors, one backend.** A **React + Vite + TypeScript** SPA serves
**requesters** and **annotators**; **managers** run their full daily workflow in
the **Manager Admin** (Django Admin at `/admin/`). Both talk to the same
**Django + Django REST Framework** backend and share one service layer. In
development, Vite (`:5173`) and Django (`:8000`) run as separate processes.

## Quick start

```bash
cd /projects/weilab/shenb/mito-data-agent
conda activate mito-data-agent
./dev-setup.sh                 # first run, or after pulling dep/model changes
./dev-launch.sh                # starts both servers; Ctrl+C stops both
```

`dev-launch.sh` skips all of `dev-setup.sh`'s checks, so it's the fast one
to use for the normal "stop, edit code, relaunch" loop — only re-run
`dev-setup.sh` when dependencies or migrations change.

Open **http://localhost:5173**. Then create the standard dev accounts:

```bash
cd backend && python manage.py seed_dev
# password demo12345 · manager (manager) + alice, bob, carol, dave (annotators)
```

First-time environment setup, `.env` configuration, remote/HPC access, dev-data
commands, and tests are all in
**[progress/development.md](progress/development.md)**.

## Documentation

Architecture info and progress (how much has been done) both live in one
place: **[`progress/`](progress/)** — start at
[`progress/README.md`](progress/README.md) or
[`progress/PROJECT.md`](progress/PROJECT.md). Quick links:

| Doc | What's in it |
| --- | --- |
| **[progress/codemap.md](progress/codemap.md)** | **"I want to change feature X — where do I go?"** (start here to edit code) |
| [progress/architecture.md](progress/architecture.md) | How the pieces fit; the service-layer rule; data model |
| [progress/development.md](progress/development.md) | Run, configure, seed data, remote/HPC, tests |
| [progress/admin.md](progress/admin.md) | Manager Admin — access, actions, safety model |
| [progress/api.md](progress/api.md) | REST API reference |
| [progress/history/](progress/history/) | Session log — what changed, why, and lessons learned |

## Repository layout

```
backend/          Django + DRF API
  config/         settings, urls, wsgi/asgi
  accounts/       users, roles, institutions, annotator profiles, auth
  projects/       projects, manager-approval gate, progress
  volumes/        HPC data registration, volumes, image/mask pairing, splitting
  annotation/     tasks, submissions, review, assignment, QC
  core/           shared enums, permissions, storage, dev data, Manager Admin site
  templates/admin/  Manager Admin dashboard + intermediate action forms
frontend/         React + Vite + TypeScript SPA
  src/{pages,components,routes,api,types,hooks,auth}
  src/features/   viewer/ (AnnotationCanvas — task View + Annotate; SliceViewer
                  — volume viewer), lifecycle/, proofreading/
progress/         architecture, code map, development, admin, api docs +
                  per-module docs + history/ session log (all app docs live here)
vendor/           vendored third-party deps (sam2/ — see vendor/README.md)
```

The golden rule: **business logic lives in `backend/<app>/services.py`**; views,
admin, CLI, and React pages are thin wrappers around it. The full feature → file
map is in [progress/codemap.md](progress/codemap.md).

## Workflow

1. A requester (or manager) opens **Register Data**, names a **dataset** and
   **volume**, picks an **HPC directory**, and registers its
   `.tif`/`.tiff`/`.nii.gz` files. Image + mask pairs are auto-detected (e.g.
   `x_image.tif` / `x_mask.tif`); you can also pair manually or register images
   alone. Optional biomedical metadata is collected; resolution/shape/mito counts
   are derived from the files.
2. A **manager approves** requester-registered data — until then its volumes
   can't be split or assigned. Manager-registered data is approved on creation.
3. The manager **assigns** work: **auto-assign** gives each annotator whole
   volumes balanced evenly (respecting `max_active_tasks`); **manual** assignment
   reassigns individual tasks; a manager may also **split** a volume into
   frame-based tasks.
4. An annotator views assigned tasks + metadata, then either annotates **in the
   browser** (the built-in editor: brush/polygon/EfficientSAM tools plus
   fork-aware SAM2 tracking) or annotates externally and uploads a label file.
   Basic QC runs on submit either way.
5. The manager **reviews**: approve, reject, or request revision.
6. Progress and workload update accordingly.

Managers do steps 2–5 in the [Manager Admin](progress/admin.md); requesters and
annotators use the React SPA.

## Tests & build

```bash
cd backend && python manage.py test        # backend tests (run from backend/)
python backend/manage.py check             # system checks
npm run build --prefix frontend            # frontend typecheck + build
```

## Workflow types & lifecycle

Each dataset (`Project`) has a **workflow type** — `annotation`, `proofreading`,
or `segmentation` — sharing one registration → volume → task → submission →
review pipeline. Records roll up into three lifecycle views, **New / To
Proofread / Done**, defined once in `backend/core/lifecycle.py` and surfaced in
the API (`?lifecycle=`, `/api/projects/lifecycle-counts/`), the Manager Admin
(filter + dashboard), and the Institution dashboard (tabs).

The internal `requester` role is shown as **Institution** in the UI
(display-label mapping in `backend/core/labels.py` / `frontend/src/labels.ts`);
no database values were renamed.

Replaceable integrations live behind provider folders — proofreading, quality
control, visualization, publishing (`backend/annotation/*/`) and processing/HPC
(`backend/processing/`, with `local` and `slurm` backends and a
`run_processing_dispatcher` command). See
[progress/codemap.md](progress/codemap.md#one-replaceable-feature--one-folder).

## Out of scope (not in the MVP)

Provider **boundaries** exist, but these integrations are intentionally
placeholders/stubs: model inference (nnU-Net / PyTorch-Connectomics),
connected-component scientific QA, Neuroglancer precomputed conversion, mesh
generation, and Hugging Face / MitoVerse publishing. The SLURM backend is
implemented but has not been exercised against a real cluster. Also out of
scope: payments/wages/billing (annotation work is unpaid). Single-server
production deployment is future work — development keeps Vite and Django as
separate processes.
