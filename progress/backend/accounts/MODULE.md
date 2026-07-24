# `backend/accounts/` — users, roles, institutions, auth

Owns the Django `User` extension (role + institution), the three-role
permission model every other app reads, and the token-auth endpoints the
React SPA uses to log in.

## Files

| File | Purpose |
|---|---|
| `models.py` | `Institution`, `UserProfile` (role + institution, one-to-one with `User`), `AnnotatorProfile` (capacity/quality — annotator-only, no pay fields). |
| `roles.py` | `get_role(user)` and the `is_manager`/`is_annotator`/`is_requester`/`can_register_data` predicates every permission check in the codebase ultimately calls. API-level enforcement wraps these in the DRF permission classes in `core/permissions.py`. |
| `api.py` | `LoginView`, `RegisterView`, `LogoutView`, `MeView`, `AnnotatorListView`. |
| `serializers.py` | `LoginSerializer` (username/password/optional `portal`), `RegisterSerializer`, `CurrentUserSerializer`. |
| `signals.py` | `post_save` on `User` → auto-creates a `UserProfile` (default role `annotator`) so every user always has one. |
| `admin.py` | Registers `Institution`/`UserProfile`/`AnnotatorProfile` on the Manager Admin site (see `core/admin_site.py`). |
| `tests.py` | Role predicate + auth endpoint tests. |

## The role model

Three roles used everywhere (`core.choices.UserRole`): `manager`,
`annotator`, `requester` (plus legacy `client`/`reviewer` values kept for
old rows — `is_requester` treats `client` as `requester`, nothing treats
`reviewer` specially).

`get_role(user)`:
1. Superuser → always `manager`, regardless of `UserProfile.role`. This is
   deliberate — it lets an admin-created superuser drive the whole workflow
   without a matching profile row.
2. Otherwise reads `user.profile.role`.

`is_annotator(user)` returns `True` for **both** `annotator` and `manager` —
"annotator" here means "may view annotator-facing pages," and a manager can
view everything. It does **not** mean "may edit any task" — that's a
separate, per-task check (`annotation.services.can_edit_task`), not a role
predicate.

## Auth flow

Token-based, not session/cookie (`rest_framework.authtoken`). `LoginView`
authenticates via Django's standard `authenticate()`, then
`Token.objects.get_or_create(user=user)` and returns `{token, user}`. The
frontend stores the token in `localStorage` and sends
`Authorization: Token <token>` on every request — see
[`../../frontend/api/MODULE.md`](../../frontend/api/MODULE.md).

### Login portals

`LoginView` accepts an optional `portal` field (`"requester"` or
`"annotator"`) and rejects the login (403) if the account's role doesn't
match the tab the user logged in through — e.g. a manager or annotator
account can't log in through the "Institution" tab. This is purely a UX
guard (prevents a confusing landing page), not a security boundary — the
same account/token works identically once issued. See `_portal_allows()` in
`api.py`.

## `AnnotatorListView`

`GET /api/annotators/`, manager-only. Powers the assignment dropdowns
(`AssignmentPlanEditor` on the frontend). Filters to users whose role is
*exactly* `annotator` (not managers, even though `is_annotator()` would
include them) — you assign tasks to annotators, not to yourself-as-manager.

## Gotchas / things that look like bugs but aren't

- `UserProfile.role` defaults to `annotator` at the model level, but the
  `post_save` signal is what actually creates the row for every new user —
  if you ever bulk-create `User` rows without going through the ORM's normal
  save path (e.g. a raw SQL migration), they won't get a profile and
  `get_role` will return `None` for them until one is created.
- `is_annotator` including managers is intentional (see above) — don't
  "fix" it to be role-exclusive without checking every call site.
