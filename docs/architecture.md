# Architecture

## The big picture

Mito Data Agent has **one backend** and **two front doors**:

```
                 ┌──────────────────────────────┐
 Requesters ───▶ │  React SPA (Vite, :5173)      │ ─┐
 Annotators ───▶ │  frontend/src/*              │  │  token-auth JSON
                 └──────────────────────────────┘  │  over /api/*
                                                    ▼
                 ┌──────────────────────────────────────────────┐
 Managers ─────▶ │  Django + DRF backend (:8000)                 │
 Superusers ──▶  │    api.py  →  serializers.py  →  services.py  │ ─▶ models ─▶ DB
   (Manager      │    admin.py (Manager Admin) ─────┘            │
    Admin)       └──────────────────────────────────────────────┘
```

- **React SPA** (`frontend/`) serves **requesters** and **annotators**. It talks
  to the backend only through the REST API.
- **Manager Admin** (Django Admin at `/admin/`) is the **managers'** operational
  interface. See [admin.md](admin.md).
- Both front doors call the **same models and the same service layer**, so
  behaviour stays consistent no matter who triggers it.

## The golden rule: logic lives in `services.py`

Every app keeps its business logic in `<app>/services.py` as plain, deterministic
functions. Everything else is thin:

| Layer | File | Responsibility |
| --- | --- | --- |
| Service | `<app>/services.py` | **All business logic.** Takes plain args, returns models/dicts. |
| REST view | `<app>/api.py` | Auth/permission check, parse request, call a service, return JSON. |
| Serializer | `<app>/serializers.py` | Validate input / shape output. |
| Admin | `<app>/admin.py` | Manager screens + bulk actions that call services. |
| CLI | `<app>/management/commands/*` | Command-line wrappers that call services. |

**Practical consequence:** to change *what the system does*, edit the service.
To change *how it's exposed*, edit the view, admin, serializer, or page. This is
why the same operation (e.g. assignment) behaves identically from the SPA, the
admin, and a management command.

## Backend apps

| App | Owns | Notable files |
| --- | --- | --- |
| `accounts` | Users, roles, institutions, annotator capacity, auth/registration/login | `models.py`, `roles.py`, `serializers.py`, `api.py`, `signals.py` |
| `projects` | `Project`, approval gate, progress | `models.py`, `services.py`, `api.py`, `admin.py` |
| `volumes` | `Volume`, HPC data registration, scanning, image/mask pairing, splitting | `services.py`, `api.py`, `models.py` |
| `annotation` | `AnnotationTask`, `AnnotationSubmission`, `ReviewRecord`, assignment, QC, review | `services.py`, `api.py`, `admin.py`, `models.py` |
| `core` | Shared enums, permissions, storage, utils, dev-data commands, **Manager Admin site** | `choices.py`, `permissions.py`, `storage.py`, `admin_site.py`, `admin_common.py` |

## Data model

```
Institution ─┬─< Project ─┬─< Volume ─┬─< AnnotationTask ─< AnnotationSubmission ─< ReviewRecord
             │            │           │        │                    │                    │
             └─< UserProfile          └────────┘ (task also FKs Project)                 │
User ─1:1─ UserProfile (role, institution)      assigned_to → User        annotator → User, reviewer → User
User ─1:1─ AnnotatorProfile (is_active_annotator, max_active_tasks, quality_score)
```

- A **dataset** is a `Project`; a **volume/chunk/crop** is a `Volume`
  (`source_volume` groups chunks). A `Volume` holds **references** to HPC files
  (`image_path` / `label_path`), never the pixel data.
- A `Project` starts **unreviewed** when a requester registers it; a manager must
  approve it (`manager_reviewed`) before its volumes can be split or assigned.
- An `AnnotationTask` covers a z/y/x range of a volume; the default auto-assign
  path makes **one whole-volume task per volume**.
- Enums (roles, statuses, types) live in `core/choices.py` and are mirrored on
  the frontend in `frontend/src/types/index.ts`.

## Request lifecycle (SPA example: submitting a label)

1. `frontend/src/pages/SubmitTaskPage.tsx` calls `submitTask()` in
   `frontend/src/api/submissions.ts`.
2. `frontend/src/api/client.ts` sends the request with the auth token to
   `POST /api/tasks/<id>/submit/`.
3. `config/urls.py` routes to `SubmitTaskView` in `annotation/api.py`.
4. The view checks the permission, validates with `SubmitTaskSerializer`, and
   calls `submit_annotation()` in `annotation/services.py`.
5. The service creates the `AnnotationSubmission`, runs `run_basic_qc()`, and
   flips the task status — the same service the Manager Admin would use.

## Storage & configuration

- Files live under `MITO_DATA_ROOT` (see `.env`); the DB stores only relative
  paths. Path resolution is in `core/storage.py` and `volumes/services.py`.
- Runtime settings are in `config/settings.py`, driven by `.env`
  (see [development.md](development.md)).
