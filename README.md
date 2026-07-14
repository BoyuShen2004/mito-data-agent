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
development, Vite (`:5173`) and Django (`:8000`) run as separate processes that
`./dev.sh` starts and stops together.

## Quick start

```bash
cd /projects/weilab/shenb/mito-data-agent
conda activate mito-data-agent
./dev.sh                       # starts both servers; Ctrl+C stops both
```

Open **http://localhost:5173**. Then create the standard dev accounts:

```bash
cd backend && python manage.py seed_dev
# password demo12345 · manager (manager) + alice, bob, carol, dave (annotators)
```

First-time environment setup, `.env` configuration, remote/HPC access, dev-data
commands, and tests are all in **[docs/development.md](docs/development.md)**.

## Documentation

| Doc | What's in it |
| --- | --- |
| **[docs/codemap.md](docs/codemap.md)** | **"I want to change feature X — where do I go?"** (start here to edit code) |
| [docs/architecture.md](docs/architecture.md) | How the pieces fit; the service-layer rule; data model |
| [docs/development.md](docs/development.md) | Run, configure, seed data, remote/HPC, tests |
| [docs/admin.md](docs/admin.md) | Manager Admin — access, actions, safety model |
| [docs/api.md](docs/api.md) | REST API reference |

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
docs/             architecture, code map, development, admin, api
```

The golden rule: **business logic lives in `backend/<app>/services.py`**; views,
admin, CLI, and React pages are thin wrappers around it. The full feature → file
map is in [docs/codemap.md](docs/codemap.md).

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
4. An annotator views assigned tasks + metadata, annotates externally, and
   uploads a label file (basic QC runs on submit).
5. The manager **reviews**: approve, reject, or request revision.
6. Progress and workload update accordingly.

Managers do steps 2–5 in the [Manager Admin](docs/admin.md); requesters and
annotators use the React SPA.

## Tests & build

```bash
cd backend && python manage.py test        # backend tests (run from backend/)
python backend/manage.py check             # system checks
npm run build --prefix frontend            # frontend typecheck + build
```

## Out of scope (not in the MVP)

In-browser image annotation, nnU-Net / PyTorch-Connectomics, Slurm, advanced QC,
Hugging Face / MitoVerse publishing, and payments/wages/billing (annotation work
is unpaid). Single-server production deployment is future work — development
keeps Vite and Django as separate processes.
