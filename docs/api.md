# REST API reference

> Part of the [docs](README.md). To add or change an endpoint, see
> [codemap.md](codemap.md#common-recipes-end-to-end); the view/serializer files
> per feature are listed there.

Base URL: `/api`. All endpoints except login/register require a token header:

```
Authorization: Token <token>
```

Obtain a token from `POST /api/auth/login/` or `POST /api/auth/register/`.

Roles: **requester** (registers datasets, views own projects), **annotator**
(works on assigned tasks), **manager** (manages projects, annotators, and
manual task assignment; superusers are treated as managers). Annotation work is
unpaid — there are no payment endpoints.

## Auth

| Method | Path | Access | Body |
| ------ | ---- | ------ | ---- |
| POST | `/auth/login/` | public | `{username, password, portal?}` → `{token, user}`; `portal` ∈ `requester`/`annotator` validates the login tab |
| POST | `/auth/register/` | public | `{username, password, email?, role, institution_name?}` where `role` ∈ `annotator`/`requester` (no public manager signup) → `{token, user}` |
| POST | `/auth/logout/` | auth | — (invalidates token) |
| GET  | `/auth/me/` | auth | → current user |
| GET  | `/annotators/` | manager | list annotators for assignment dropdowns |

## Data registration (requester + manager, shared endpoint)

| Method | Path | Notes |
| ------ | ---- | ----- |
| POST | `/hpc/scan/` | `{hpc_directory}` → `{directory, files[], pairs[], unpaired[]}`. `pairs` are auto-detected `{image, mask, base}` image+mask matches; `unpaired` are the leftover file names. |
| POST | `/register-data/` | `{dataset, volume, hpc_directory, pairs?, files?, label_type?, metadata?, project?, annotation_type?}`. Registers HPC file references as chunks/crops under a dataset (project) + source volume. `dataset` and `volume` are required; only `.tif`/`.tiff`/`.nii.gz` files are accepted. Creates a new project unless `project` is given (must be owned by a requester or any project for a manager). |

Image/mask pairing is flexible:

* `pairs`: explicit `[{image, mask?, chunk_id?}, …]` — pick specific image+mask
  pairs out of a folder that also holds unrelated volumes. A `mask` is stored as
  the volume's label (typed by `label_type`, default `prediction`).
* `files`: image-only `[{path|name, chunk_id?}, …]` (no masks).
* neither: the directory is auto-scanned and **all detected image+mask pairs
  plus any unpaired images** are registered.

`metadata` is optional biomedical detail (organism, tissue, cell_type,
imaging_modality, imaging_instrument, experimental_condition, sample_condition,
dataset_source, publication, description, notes). Resolution, shape, and
mitochondria counts are derived from the files, never entered here.

## Projects (manager: all; requester: own)

| Method | Path | Notes |
| ------ | ---- | ----- |
| GET | `/projects/` | list (manager: all; requester/Institution: own). `?lifecycle=new\|to_proofread\|done` filters by lifecycle bucket |
| POST | `/projects/` | `{title, dataset?, description?, metadata?, annotation_type?, workflow_type?, deadline?}` (`workflow_type` ∈ annotation/proofreading/segmentation; defaults from `annotation_type`) |
| GET | `/projects/lifecycle-counts/` | `{new, to_proofread, done}` counts over the caller's visible projects |
| GET | `/projects/<id>/` | retrieve (owner Institution or manager). Response includes `workflow_type` and computed `lifecycle` |
| PATCH | `/projects/<id>/` | partial update, incl. `metadata` (owner Institution or manager) |
| DELETE | `/projects/<id>/` | delete |
| GET | `/projects/<id>/summary/` | progress (+ annotator workload for managers) |
| POST | `/projects/<id>/review/` | manager only: `{reviewed?}` (default `true`) — approve Institution-registered data so it can be split/assigned |

## Volumes (manager: any; requester: own project)

| Method | Path | Notes |
| ------ | ---- | ----- |
| GET | `/projects/<project_id>/volumes/` | list |
| POST | `/projects/<project_id>/volumes/` | multipart: `name`, `source_volume`, `chunk_id`, `image_path` or `image_file`, `label_path`/`label_file`, `label_type`, `file_format`, `voxel_size_*` |
| GET | `/volumes/<id>/` | retrieve |
| PATCH | `/volumes/<id>/` | edit metadata / label_type / shape (owner requester or manager) |
| POST | `/volumes/<id>/split/` | manager | `{z_step?, task_type?, priority?, instructions?}` |

## Tasks

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/projects/<project_id>/tasks/` | manager | `?status=` filter |
| POST | `/projects/<project_id>/assign-tasks/` | manager | auto-assign: one whole-volume task per volume, distributed evenly across active annotators. Requires a reviewed project (`400` with `reviewed:false` otherwise). |
| POST | `/tasks/<id>/assign/` | manager | manual (re)assign: `{annotator_id}` (null unassigns; updates the task in place) |
| GET | `/tasks/<id>/` | auth | manager: any; annotator: own. Includes dataset + project metadata |
| PATCH | `/tasks/<id>/` | auth | manager: any field; annotator: start own task |
| GET | `/my-tasks/` | annotator | active/assigned tasks |
| GET | `/my-completed-tasks/` | annotator | submitted/approved/rejected |
| GET | `/tasks/<id>/proofreading/` | manager or assignee | launch info from the proofreading provider: `{mode, url, editable, download_available, message, provider, download{...}}`. `mode` ∈ edit/view/download/unavailable |
| GET | `/tasks/<id>/visualization/` | manager or assignee | `{available, url, provider, image_path, label_path, region?}` |

## Processing jobs (manager: all; Institution: own projects)

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/processing-jobs/` | auth | list; manager sees all, Institution sees jobs on own projects. `?status=` / `?job_type=` filters |
| GET | `/processing-jobs/<id>/` | auth | retrieve |
| POST | `/processing-jobs/<id>/retry/` | manager | requeue a terminal (failed/cancelled/succeeded) job |
| POST | `/processing-jobs/<id>/cancel/` | manager | cancel a job (best effort via its backend) |

Jobs are **created by the service layer** (not a public POST) and executed by the
`run_processing_dispatcher` management command.

## Submissions

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| POST | `/tasks/<id>/submit/` | annotator | multipart: `label_file`, `notes?` |
| GET | `/submissions/` | auth | manager: all; annotator: own; `?task_status=` |
| GET | `/submissions/<id>/` | auth | retrieve |
| POST | `/submissions/<id>/review/` | manager | `{decision, comments?}` where decision ∈ approved/rejected/revision_requested |
