# Code map — "I want to change X, where do I go?"

This is the quick lookup for **which files own which feature**. Paths are
relative to the repo root. Read [architecture.md](architecture.md) first if you
haven't — the one thing to remember is that **business logic lives in
`<app>/services.py`**, and views/admin/pages are thin wrappers around it.

If you only remember one table, remember this one:

| I want to change… | Go to |
| --- | --- |
| **What the system does** (rules, calculations, workflow) | `backend/<app>/services.py` |
| **How the REST API exposes it** | `backend/<app>/api.py` + `serializers.py`, route in `backend/config/urls.py` |
| **How the Manager Admin exposes it** | `backend/<app>/admin.py` (+ `backend/templates/admin/...`) |
| **A database field** | `backend/<app>/models.py` → `makemigrations` → update serializer/admin/frontend type |
| **A React screen** | `frontend/src/pages/*` (+ route in `frontend/src/routes/AppRoutes.tsx`) |
| **Shared enums / statuses / roles** | `backend/core/choices.py` (mirror in `frontend/src/types/index.ts`) |

---

## Backend — by feature

### Accounts, roles, auth
| Feature | File(s) |
| --- | --- |
| Roles list (manager/annotator/requester/…) | `backend/core/choices.py` (`UserRole`) |
| Role helpers (`is_manager`, `is_requester`, `can_register_data`) | `backend/accounts/roles.py` |
| DRF permission classes (`IsManager`, `CanRegisterData`, …) | `backend/core/permissions.py` |
| User / profile fields, annotator capacity | `backend/accounts/models.py` (`UserProfile`, `AnnotatorProfile`, `Institution`) |
| Public registration rules (annotator/requester only) | `backend/accounts/serializers.py` (`RegisterSerializer`) |
| Login + login-portal validation | `backend/accounts/serializers.py` (`LoginSerializer`), `backend/accounts/api.py` |
| Auto-create a profile on signup | `backend/accounts/signals.py` |
| Auth/registration/annotator-list endpoints | `backend/accounts/api.py` |

### Projects, approval, progress
| Feature | File(s) |
| --- | --- |
| Project fields (dataset, metadata, review state, status, deadline) | `backend/projects/models.py` |
| Create a project / project defaults | `backend/projects/services.py` (`create_project`) |
| Manager approval (review gate) | `backend/projects/services.py` (`mark_project_reviewed`) |
| Progress calculation (%, counts) | `backend/projects/services.py` (`calculate_project_progress`) |
| Project REST endpoints + `review`/`summary` actions | `backend/projects/api.py`, `backend/projects/serializers.py` |

### Data registration & volumes
| Feature | File(s) |
| --- | --- |
| Supported data extensions (`.tif/.tiff/.nii.gz`) | `backend/volumes/services.py` (`SUPPORTED_DATA_EXTENSIONS`) |
| Register a dataset (dataset/volume/pairs/metadata) | `backend/volumes/services.py` (`register_dataset`) |
| Scan an HPC directory / validate the path | `backend/volumes/services.py` (`scan_hpc_directory`, `resolve_hpc_directory`) |
| Image + mask auto-pairing rules | `backend/volumes/services.py` (`detect_volume_pairs`, `MASK_TOKENS`/`IMAGE_TOKENS`) |
| Volume fields (paths, label type, shape, format) | `backend/volumes/models.py` |
| Derive image shape from a file | `backend/core/utils.py` (`inspect_volume_shape`, `read_tiff_shape_fast`) |
| Registration/scan REST endpoints | `backend/volumes/api.py`, `backend/volumes/serializers.py` |

### Tasks, assignment, submissions, review
| Feature | File(s) |
| --- | --- |
| Task / submission / review fields & statuses | `backend/annotation/models.py` + `backend/core/choices.py` (`TaskStatus`, `TaskType`, `ReviewDecision`) |
| Split a volume into frame tasks / z-step / task-type inference | `backend/volumes/services.py` (`create_tasks_from_volume`, `split_volume_by_frames`, `infer_task_type`; map in `core/choices.py`) |
| Whole-volume task creation | `backend/annotation/services.py` (`create_whole_volume_task`, `ensure_volume_tasks`) |
| **Auto-assign** (even distribution, capacity) | `backend/annotation/services.py` (`auto_assign_project`, `assign_tasks_rule_based`) |
| **Manual** assign / reassign / unassign | `backend/annotation/services.py` (`assign_task_to_annotator`), `backend/annotation/api.py` |
| Submission + basic QC (allowed label extensions) | `backend/annotation/services.py` (`submit_annotation`, `run_basic_qc`); `MITO_ALLOWED_LABEL_EXTENSIONS` in `config/settings.py` |
| Review decisions (approve/reject/revision) | `backend/annotation/services.py` (`review_submission` + helpers) |
| Annotator workload metrics | `backend/annotation/services.py` (`calculate_annotator_workload`) |
| Task/submission/review REST endpoints | `backend/annotation/api.py`, `backend/annotation/serializers.py` |

### Manager Admin (the managers' portal)
| Feature | File(s) |
| --- | --- |
| Admin identity, access rule, dashboard metrics | `backend/core/admin_site.py` |
| Installing the custom admin site | `backend/core/admin_apps.py` (+ `INSTALLED_APPS` in `config/settings.py`) |
| Admin permission mixin + link helpers | `backend/core/admin_common.py` |
| A specific model's admin screen / bulk actions | `backend/<app>/admin.py` |
| Intermediate action forms (assign / review-with-comment) | `backend/templates/admin/annotation/*.html` + the action in `backend/annotation/admin.py` |
| Dashboard layout | `backend/templates/admin/manager_index.html` |

### Plumbing
| Feature | File(s) |
| --- | --- |
| Backend URL routes | `backend/config/urls.py` |
| Settings / env vars / installed apps | `backend/config/settings.py` (+ `.env`, `.env.example`) |
| File storage location & path handling | `backend/core/storage.py` |
| API landing page at `:8000/` | `backend/config/views.py` |

---

## Frontend — by feature

| Feature | File(s) |
| --- | --- |
| Add / change a page | `frontend/src/pages/*` |
| Route table & role-based redirects | `frontend/src/routes/AppRoutes.tsx` (`effectiveRole`, `homePathForRole`) |
| Top navigation (per role) | `frontend/src/components/Navbar.tsx` |
| Auth state, login/register/logout, `isManager`/`isRequester` | `frontend/src/auth/AuthContext.tsx` + `frontend/src/api/auth.ts` |
| Talking to the backend (fetch wrapper, token) | `frontend/src/api/client.ts` |
| Per-resource API calls | `frontend/src/api/{projects,volumes,tasks,submissions,registerData}.ts` |
| TypeScript types mirroring the backend | `frontend/src/types/*` |
| Login tabs (requester/annotator portals) | `frontend/src/pages/LoginPage.tsx` |
| Public sign-up | `frontend/src/pages/RegisterPage.tsx` |
| Register Data (dataset/volume/dir scan/pairs/metadata) | `frontend/src/pages/RegisterDataPage.tsx` + `frontend/src/api/registerData.ts` |
| Requester dashboard | `frontend/src/pages/RequesterDashboard.tsx` |
| Annotator dashboard / my tasks | `frontend/src/pages/AnnotatorDashboard.tsx` + `frontend/src/components/TaskTable.tsx` |
| Manager views in the SPA (project detail, assignment table, metadata) | `frontend/src/pages/{ManagerDashboard,ProjectDetailPage}.tsx`, `frontend/src/components/{TaskAssignmentTable,MetadataCard}.tsx` |
| Task detail / submit a label | `frontend/src/pages/{TaskDetailPage,SubmitTaskPage}.tsx`, `frontend/src/components/FileUpload.tsx` |
| Review a submission (SPA) | `frontend/src/pages/ReviewSubmissionPage.tsx` |
| Volume detail / manual split UI | `frontend/src/pages/VolumeDetailPage.tsx` |
| Status pills / colors | `frontend/src/components/StatusBadge.tsx` |
| Global styling / theme | `frontend/src/styles.css` |
| Dev-only login helper (seed accounts) | `frontend/src/pages/LoginPage.tsx` (`import.meta.env.DEV` block) |

---

## Command-line

| Feature | File(s) |
| --- | --- |
| Dev accounts seed/clear/reset/status | `backend/core/dev_data.py` + `backend/core/management/commands/{seed_dev,clear_dev_data,reset_dev,dev_status}.py` |
| Split a volume (CLI) | `backend/volumes/management/commands/split_volume.py` |
| Rule-based assignment (CLI) | `backend/annotation/management/commands/assign_tasks.py` |
| Project progress report (CLI) | `backend/projects/management/commands/progress_report.py` |

---

## Common recipes (end-to-end)

**Add a database field** → edit `backend/<app>/models.py` → `python manage.py
makemigrations && migrate` → expose it in `serializers.py` (API) and/or
`admin.py` (admin) → add it to `frontend/src/types/*` and the page/component that
shows it.

**Add a REST endpoint** → put the logic in `services.py` → add a
`serializers.py` shape → add the view in `api.py` → wire the route in
`config/urls.py` → add a caller in `frontend/src/api/*.ts` → use it from a page.

**Add a Manager Admin action** → put the logic in `services.py` → add an
`@admin.action` in `backend/<app>/admin.py` (add a template under
`backend/templates/admin/...` if it needs an intermediate form) → cover it in
`backend/core/test_admin.py`.

**Add a React page** → create `frontend/src/pages/MyPage.tsx` → register the
route in `frontend/src/routes/AppRoutes.tsx` → add a nav link in
`frontend/src/components/Navbar.tsx` → add API calls in `frontend/src/api/*.ts`.

**Change a role/permission** → `core/choices.py` (the role) → `accounts/roles.py`
(helper) → `core/permissions.py` (DRF) and/or `core/admin_common.py` (admin) →
`frontend/src/auth/AuthContext.tsx` + `AppRoutes.tsx` (frontend gating).

## Where the tests live

| Scope | File |
| --- | --- |
| Services & workflow (assignment, QC, review, progress) | `backend/annotation/tests.py`, `backend/volumes/tests.py` |
| REST API flows | `backend/annotation/test_api_flows.py`, `backend/accounts/tests.py` |
| Manager Admin (access, actions, audit) | `backend/core/test_admin.py` |
| Dev-data commands | `backend/core/tests.py` |
| Frontend | type-checked by `npm run build --prefix frontend` (`tsc`) |
