# mito-data-agent — progress & documentation

`progress/` is the one place for documenting the app — don't split it or
duplicate it elsewhere. Everything here describes **what the codebase is
right now**; treat it as the source of truth for orientation and for
navigating the code.

There is **no work queued**. When you start a significant new body of work,
log it under [`history/`](history/) (which was just reset to zero) and keep
the *module* docs below updated in the same change.

## Don't merge this with `../data/`

`data/` is `MITO_DATA_ROOT` (set in `.env`) — the app's live storage root:
every registered image/label volume, submission upload, and each task's
working label file (`<project name>/<dataset name>/volume_<id>_labels.tif`,
written directly by path, see `backend/annotation/label_paths.py`) lands
there. It is **not** documentation space and must stay exactly what the app
expects — see `backend/volumes/MODULE.md` for why. The dev instance keeps
one real project under `data/webknossos/`; everything else there is
regenerable (e.g. the `embeddings/` SAM cache) or test scratch.

## Start here

**[`PROJECT.md`](PROJECT.md)** — whole-project overview: tech stack, the
three-role model, the data-model hierarchy, the provider-adapter pattern,
end-to-end request flow, and an index into every module doc. Read this first
for orientation.

## Topic docs

Deeper dives by topic, each usable standalone:

| Doc | What's in it |
| --- | --- |
| **[`codemap.md`](codemap.md)** | **"I want to change feature X — where do I go?"** — start here to edit code |
| [`architecture.md`](architecture.md) | How the pieces fit: the service-layer rule, backend apps, data model, a request walkthrough, the `ProcessingJob` dispatcher |
| [`development.md`](development.md) | Run, configure (`.env`), seed dev data, workflow CLIs, remote/HPC access, tests, Annotate hotkeys |
| [`admin.md`](admin.md) | Manager Admin — access rules, what managers can do, the safety model |
| [`api.md`](api.md) | REST API reference, endpoint by endpoint |

## Module docs (mirror the real directory structure)

**Backend** — `backend/<django-app>/MODULE.md`:

| Module | What it owns |
|---|---|
| [`backend/accounts/`](backend/accounts/MODULE.md) | Users, roles, institutions, login/register/token auth |
| [`backend/core/`](backend/core/MODULE.md) | Choices/enums, the lifecycle rollup, permissions, storage, Manager Admin site, dev-data commands |
| [`backend/projects/`](backend/projects/MODULE.md) | Project + Dataset, review gate, delete-with-dependents |
| [`backend/volumes/`](backend/volumes/MODULE.md) | Volume model, HPC scan/pairing, data registration, volume→task splitting |
| [`backend/annotation/`](backend/annotation/MODULE.md) | **The big one**: tasks, submissions, review, slice-streaming/label-editing, EfficientSAM + SAM2 fork-aware tracking, all provider interfaces |
| [`backend/processing/`](backend/processing/MODULE.md) | Async job queue (ingest/predict/etc.), local/SLURM backends |
| [`backend/config/`](backend/config/MODULE.md) | Django settings, URL routing, provider-setting reference |

**Frontend** — `frontend/<src-dir>/MODULE.md`:

| Module | What it owns |
|---|---|
| [`frontend/api/`](frontend/api/MODULE.md) | HTTP client, one module per backend resource; also `AuthContext`, `useAsync`, `types/` |
| [`frontend/routes/`](frontend/routes/MODULE.md) | Role-gated route table, back-navigation |
| [`frontend/pages/`](frontend/pages/MODULE.md) | One file per route: dashboards, project/volume detail, register data, submit/review, the task viewer/editor page |
| [`frontend/components/`](frontend/components/MODULE.md) | Shared UI: tables, cards, delete-with-confirm, forms |
| [`frontend/features/`](frontend/features/MODULE.md) | **The annotation editor** — `AnnotationCanvas` (shared by task View + Annotate via an `editable` prop) and its `annotate/` chrome; `SliceViewer` (volume viewer only); proofreading launcher; lifecycle tabs |

## A note on git state

`git status` shows a large uncommitted diff. Nothing has been committed on
the user's behalf — that's deliberate, for them to review and commit
themselves.

## Keeping this up to date

If you make a change covered by one of the module docs, **update that doc in
the same change** — these are meant to stay accurate, not freeze as a
snapshot. Start a new body of work → add a numbered file to `history/`; but
always update the *module* docs to reflect the new current state.
