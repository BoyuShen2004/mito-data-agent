# REST API reference

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
| POST | `/hpc/scan/` | `{hpc_directory}` → supported `.tif`/`.tiff`/`.nii.gz` files in the directory |
| POST | `/register-data/` | `{dataset, volume, hpc_directory, files?, metadata?, project?, annotation_type?}`. Registers HPC file references as chunks/crops under a dataset (project) + source volume. `dataset` and `volume` are required; only `.tif`/`.tiff`/`.nii.gz` files are accepted. Creates a new project unless `project` is given (must be owned by a requester or any project for a manager). |

`metadata` is optional biomedical detail (organism, tissue, cell_type,
imaging_modality, imaging_instrument, experimental_condition, sample_condition,
dataset_source, publication, description, notes). Resolution, shape, and
mitochondria counts are derived from the files, never entered here.

## Projects (manager: all; requester: own)

| Method | Path | Notes |
| ------ | ---- | ----- |
| GET | `/projects/` | list (manager: all; requester: own) |
| POST | `/projects/` | `{title, dataset?, description?, metadata?, annotation_type?, deadline?}` |
| GET | `/projects/<id>/` | retrieve (owner requester or manager) |
| PATCH | `/projects/<id>/` | partial update, incl. `metadata` (owner requester or manager) |
| DELETE | `/projects/<id>/` | delete |
| GET | `/projects/<id>/summary/` | progress (+ annotator workload for managers) |

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
| POST | `/projects/<project_id>/assign-tasks/` | manager | rule-based auto-assignment |
| POST | `/tasks/<id>/assign/` | manager | manual (re)assign: `{annotator_id}` (null unassigns; updates the task in place) |
| GET | `/tasks/<id>/` | auth | manager: any; annotator: own. Includes dataset + project metadata |
| PATCH | `/tasks/<id>/` | auth | manager: any field; annotator: start own task |
| GET | `/my-tasks/` | annotator | active/assigned tasks |
| GET | `/my-completed-tasks/` | annotator | submitted/approved/rejected |

## Submissions

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| POST | `/tasks/<id>/submit/` | annotator | multipart: `label_file`, `notes?` |
| GET | `/submissions/` | auth | manager: all; annotator: own; `?task_status=` |
| GET | `/submissions/<id>/` | auth | retrieve |
| POST | `/submissions/<id>/review/` | manager | `{decision, comments?}` where decision ∈ approved/rejected/revision_requested |
