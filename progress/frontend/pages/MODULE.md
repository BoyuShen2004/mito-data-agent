# `frontend/src/pages/` — one file per route

Each page is a route target from `../routes/AppRoutes.tsx`. Pages fetch
their own data via `useAsync` + the `../api/` modules — there's no
shared page-level data-loading abstraction beyond that hook.

## Dashboards (role home pages)

- **`ManagerDashboard.tsx`** — lists projects + submissions awaiting
  review (`listSubmissions("submitted")`), a total-volumes count, and a
  pending-review count. Links out to `/projects`, submission review, etc.
- **`RequesterDashboard.tsx`** — the requester's own projects, filterable
  by lifecycle bucket via `LifecycleTabs` (`../features/MODULE.md`) and
  `getLifecycleCounts` (`../features/lifecycle/api.ts`).
- **`AnnotatorDashboard.tsx`** — active tasks (`listMyTasks`) and
  completed ones (`listMyCompletedTasks`), each rendered via `TaskTable`
  (`../components/MODULE.md`). The page itself is thin — all the
  Annotate/View routing logic lives in `TaskTable`.

## Project / dataset / volume management

- **`ProjectListPage.tsx`** — manager-only project list + "New project"
  link.
- **`NewProjectPage.tsx`** — step 1 of starting new work: create the
  `Project` (title, annotation target/type, workflow type, deadline).
  Deliberately separate from data registration — see the file's own
  docstring: "data is registered *into* a project," so the project is
  described on its own terms first, then step 2 (register data) follows.
- **`RegisterDataPage.tsx`** (780 lines — the largest page) — step 2:
  scan an HPC directory (`scanDataSources`), review/adjust the detected
  image/mask pairs, then `registerData`. Handles the manifest/heuristic
  pairing UX described in `backend/volumes/MODULE.md`.
- **`ProjectDetailPage.tsx`** — a project's datasets (`DatasetsCard`) and
  volumes, manager review toggle, delete-with-dependents
  (`projectDependents`/`deleteProjectForce`), inline editing
  (`ProjectEditForm`), and `AssignmentPlanEditor` for bulk task
  assignment.
- **`VolumeDetailPage.tsx`** — one volume's metadata, its tasks
  (`listProjectTasks` filtered), splitting into tasks (`splitVolume`),
  editing (`updateVolume`/`editVolume`), delete-with-dependents.

## Task lifecycle

- **`TaskDetailPage.tsx`** — a task's full metadata table (project,
  dataset, volume, frame range, shape, voxel size, priority, difficulty,
  paths, deadline, instructions), `MetadataCard` for the dataset's
  biomedical metadata, `ProofreadingLaunch` (only for the owner/manager),
  and a "Submit completed label" link when the task is in an editable
  status and belongs to the viewer (`mine = t.assigned_to === user?.id`,
  `canSubmit = mine && status in [assigned, in_progress,
  revision_requested]`).
- **`SubmitTaskPage.tsx`** — upload a label file for a task
  (`FileUpload` + `submitTask`).
- **`ReviewSubmissionPage.tsx`** — manager approve/reject/request-revision
  on a submission, with a comments field. When `submission.source ===
  "inapp"` (no uploaded file to show), renders an "Open annotation editor"
  link (`/editor/tasks/<task_id>`) instead of the label-file row, so the
  manager can actually inspect the painted labels before deciding —
  approving one promotes the working copy to the volume's official label
  (`backend/annotation/services.approve_submission`).

## Auth

- **`LoginPage.tsx`** — two login tabs (requester vs annotator, see
  `LoginPortal` in `api/auth.ts`); in dev builds only
  (`import.meta.env.DEV`) shows the standard seeded dev accounts
  (`manager`/`alice`/... , password `demo12345`) and a "Reset dev data"
  button (`resetDevData`) — both stripped from production builds.
- **`RegisterPage.tsx`** — self-service signup, role choice limited to
  `annotator`/`requester` (no public manager signup).

## `ViewerPage.tsx` — read this one carefully if touching the editor

Both routes it backs (`/viewer/*`, `/editor/*`) use `RequireAuth fullBleed`
(`../routes/MODULE.md`) — **global navbar stays**, but the centered
`.container` is skipped. Each component builds an `.editor-shell` that fills
`.full-bleed-main` under the navbar (flex column, `min-height: 0`) with a
slim `.editor-topbar` and an `.editor-body` the viewer/canvas fills.

**Navbar owns leaving** (brand / left nav → home, ← Back → task or volume).
**Topbar owns task work only** — do not put Done / Home / Task details here
(that was tried and felt redundant; cleaned up).

Exports two page components:
- **`VolumeViewerPage`** — always read-only (`SliceViewer`); topbar is
  title only.
- **`TaskViewerPage({editable})`** — computes
  `mayEdit = isManager || task.assigned_to === user?.id`. When
  `editable && mayEdit`, renders `AnnotationCanvas`; otherwise
  `SliceViewer`. Topbar actions:
  - **Annotate** / **View only** — mode switch to the other route
  - **Submit for review** — when `editable && mayEdit` and status ∈
    `SUBMITTABLE_STATUSES` (assigned/in_progress/revision_requested):
    calls `submitInappTask`, then `navigate(homePathForRole)` so finishing
    work lands on the dashboard instead of needing a separate Done button.
    This is the *only* in-app formal submit path.

## Gotchas

- Ownership/edit checks are computed **per page**, not centrally — e.g.
  `TaskDetailPage`'s `canSubmit` and `ViewerPage`'s `mayEdit` are separate
  pieces of logic that both need to agree with the backend's
  `can_edit_task`/`can_view_task` (`backend/annotation/MODULE.md`). If you
  change who can edit a task on the backend, grep the frontend for
  `assigned_to === user?.id` and `isManager` to find every place that
  logic is duplicated.
- `RegisterDataPage.tsx` is the single largest page (780 lines) — if
  you're adding a new data-source format or pairing heuristic, expect to
  touch both this file and `backend/volumes/services.py`'s pairing logic
  together.
- Do not reintroduce Done · My Tasks / Task details / navbar Home next to
  Submit — leave stays in the navbar; Submit is the finish-work action.
