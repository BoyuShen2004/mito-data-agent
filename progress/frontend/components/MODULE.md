# `frontend/src/components/` — shared UI pieces

Presentational/reusable components used across multiple pages. No routing
or page-level data-orchestration logic lives here — that's `../pages/`.

## Layout shell

- **`Layout.tsx`** — wraps every authenticated page: `Navbar` + either
  `.container` (default) or `.full-bleed-main` when `fullBleed` (viewer/
  editor). Back lives in the navbar, not next to page content.
- **`Navbar.tsx`** — global top bar on **all** authenticated pages,
  including View/Annotate. This is the **only** place for leave/home:
  - **Brand** + left nav home link → `homePathForRole`
  - **← Back** (when `backFallbackFor` is non-null) → history or
    hierarchical parent
  - username/role + logout
  Do not re-add a right-side Home button or page-level Done · My Tasks —
  those duplicated the left nav.
- **`BackButton.tsx`** — not a naive `navigate(-1)`. Checks
  `window.history.state.idx` to detect whether there's actually an in-app
  history entry to pop (`idx > 0`); if this is a fresh load/deep link
  (`idx === 0`), it navigates to the `fallback` prop (from
  `backFallbackFor`) instead of leaving the app or going to an external
  referrer.

## Status/data display

- **`StatusBadge.tsx`** — one component handling **four different status
  vocabularies** (task status, QC status, project status, label type) via
  a single flat `COLORS` lookup keyed by the raw string value — relies on
  those vocabularies not colliding on the same string with different
  intended colors (they currently don't, but check `COLORS` before adding
  a new status enum with an overlapping value name).
- **`MetadataCard.tsx`** — renders a dataset's free-form biomedical
  `metadata` JSON (`DatasetMetadata`) with human-readable labels for known
  keys (organism, tissue, imaging modality, ...) and safe rendering of
  values that are arrays/objects rather than strings (e.g. nnU-Net's
  `label_classes` map) — `formatValue` explicitly avoids `"[object
  Object]"`.
- **`ProjectSummaryCard.tsx`** — four stat tiles (volumes, total tasks,
  approved, percent complete) from `ProjectProgress`
  (`projects.services.calculate_project_progress`'s shape).
- **`DatasetsCard.tsx`** — a project's datasets, each showing its own
  volumes (matched by `volume.dataset === dataset.id` — volumes registered
  before the `Dataset` model existed have no match and are simply not
  shown here), with inline edit/delete per dataset.
- **`TaskTable.tsx`** — the task list used by both `AnnotatorDashboard` and
  (with `showProject`) `VolumeDetailPage`'s per-volume task list. Columns
  end with **Details** then **Open** (rightmost). Open stacks **View** over
  **Annotate** for managers / the assigned annotator; requesters and
  non-assignees get View only. `canEdit = isManager || t.assigned_to ===
  user?.id` has **no task-status gate**.

## Forms

- **`FileUpload.tsx`** — thin wrapper around `<input type="file">` showing
  the selected filename; `onChange(file: File | null)`.
- **`ProjectEditForm.tsx`** — inline project field editing (used by
  `ProjectDetailPage`), not read in full detail for this doc — check the
  file directly if editing project fields.
- **`AssignmentPlanEditor.tsx`** (365 lines) — the manager's bulk-assign
  UI: preview a plan (`previewAssignPlan`), edit each row's proposed
  annotator/priority/difficulty/deadline/instructions inline (`DraftRow`
  state, `LevelSelect` for the 1–5 priority/difficulty dropdowns — handles
  an out-of-range stored value gracefully by showing it as an extra option
  rather than silently coercing it), then `applyAssignPlan`. Talks to
  `../api/tasks.ts`.

## Destructive actions

- **`DeleteButton.tsx`** — the shared "ask what would be destroyed, then
  confirm" pattern used everywhere a project/dataset/volume can be
  deleted, mirroring the backend's `DeleteBlocked` mechanism
  (`backend/projects/MODULE.md`). Flow: fetch `dependents()` → native
  `confirm()` describing what else would go → call `onDelete(false)` → on
  a 409 (`ApiError.status === 409`), show a second, more severe confirm
  ("Delete anyway (destroys work)") that calls `onDelete(true)` (force).
  **This is the frontend half of the data-safety-conscious delete
  pattern** — if you add a new deletable resource, reuse this component
  rather than writing a bespoke confirm/delete flow.

## Gotchas

- Role/assignment "can this user edit this task" logic is duplicated
  across `TaskTable`, `ViewerPage.tsx`, and `TaskDetailPage.tsx` (three
  separate `isManager || assigned_to === user?.id` expressions, none of
  them status-gated). If the backend's `can_edit_task` rule ever changes,
  grep the frontend for `assigned_to === user?.id` to find all three and
  keep them in agreement.
- `StatusBadge`'s `COLORS` map is flat across four unrelated enums — adding
  a new status value to any of them means checking this file too, and
  checking it doesn't already use that string for a different color
  elsewhere.
