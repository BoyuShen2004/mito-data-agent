# REST API reference

Base URL: `/api`. All endpoints except login require a token header:

```
Authorization: Token <token>
```

Obtain a token from `POST /api/auth/login/`. Managers (or superusers) may call
manager-only endpoints; annotators may call annotator-only endpoints.

## Auth

| Method | Path | Access | Body |
| ------ | ---- | ------ | ---- |
| POST | `/auth/login/` | public | `{username, password}` → `{token, user}` |
| POST | `/auth/logout/` | auth | — (invalidates token) |
| GET  | `/auth/me/` | auth | → current user |

## Projects (manager)

| Method | Path | Notes |
| ------ | ---- | ----- |
| GET | `/projects/` | list |
| POST | `/projects/` | `{title, description?, annotation_type?, deadline?}` |
| GET | `/projects/<id>/` | retrieve |
| PATCH | `/projects/<id>/` | partial update |
| DELETE | `/projects/<id>/` | delete |
| GET | `/projects/<id>/summary/` | progress + workload + payment totals |
| GET | `/projects/<id>/payment-summary/` | payment totals + by-annotator |

## Volumes (manager)

| Method | Path | Notes |
| ------ | ---- | ----- |
| GET | `/projects/<project_id>/volumes/` | list |
| POST | `/projects/<project_id>/volumes/` | multipart: `name`, `image_path` or `image_file`, `label_path`/`label_file`, `label_type`, `file_format`, `voxel_size_*` |
| GET | `/volumes/<id>/` | retrieve |
| PATCH | `/volumes/<id>/` | edit metadata / label_type / shape |
| POST | `/volumes/<id>/split/` | `{z_step?, payment_amount?, task_type?, priority?, instructions?}` |

## Tasks

| Method | Path | Access | Notes |
| ------ | ---- | ------ | ----- |
| GET | `/projects/<project_id>/tasks/` | manager | `?status=` filter |
| POST | `/projects/<project_id>/assign-tasks/` | manager | rule-based assignment |
| GET | `/tasks/<id>/` | auth | manager: any; annotator: own |
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

## Payments

| Method | Path | Access |
| ------ | ---- | ------ |
| GET | `/payments/` | manager |
| GET | `/my-payments/` | annotator |

## Agent plans (placeholder — future LangGraph)

| Method | Path | Access |
| ------ | ---- | ------ |
| GET/POST | `/projects/<project_id>/agent-plans/` | manager |
| GET | `/agent-plans/<id>/` | manager |
| POST | `/agent-plans/<id>/approve/` | manager |
| POST | `/agent-plans/<id>/reject/` | manager |
