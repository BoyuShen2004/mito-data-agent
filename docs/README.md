# Documentation

Start here to find the right doc for what you're doing.

| If you want to… | Read |
| --- | --- |
| **Find where to change a feature** | [codemap.md](codemap.md) — feature → files lookup |
| Understand how the system fits together | [architecture.md](architecture.md) |
| Run, configure, seed, or test the app | [development.md](development.md) |
| Use / extend the manager's Django Admin | [admin.md](admin.md) |
| Call or extend the REST API | [api.md](api.md) |
| Get the product overview & quick start | [../README.md](../README.md) |

## The one-minute model

- **Two front doors, one backend.** The React SPA serves **requesters** and
  **annotators**; the **Manager Admin** (Django Admin) serves **managers**. Both
  call the same models and the same service layer.
- **Business logic lives in `backend/<app>/services.py`.** Views, admin, CLI,
  and pages are thin wrappers. Change the service to change behaviour; change the
  wrapper to change how it's exposed.
- **Apps:** `accounts` (users/roles), `projects` (projects/approval/progress),
  `volumes` (data registration/volumes/splitting), `annotation`
  (tasks/submissions/review/assignment), `core` (shared enums, permissions,
  storage, the Manager Admin site).
