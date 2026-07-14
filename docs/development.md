# Development

## Run it

```bash
cd /projects/weilab/shenb/mito-data-agent
conda activate mito-data-agent
./dev.sh
```

Then open **http://localhost:5173**. `./dev.sh` is the single command you need —
it verifies tooling and backend deps, creates `.env` from `.env.example` on first
run (never overwriting an existing one), installs frontend deps only when they
changed, runs Django checks + migrations, starts **both** servers, and stops
everything on one **Ctrl+C**.

Ordinary code changes (React, CSS, Django views/serializers/services/tests) need
no setup step — save and the dev servers reload. `npm install` re-runs only when
`frontend/package*.json` change or `frontend/node_modules` is missing.

Visiting **http://127.0.0.1:8000/** hits the API server (a small landing page),
not the app — the UI is **http://localhost:5173**.

### First-time environment (only if the conda env doesn't exist yet)

```bash
conda env create -f environment.yml   # Python 3.11 + Node + backend deps
conda activate mito-data-agent
```

Prefer pip? Python ≥ 3.11 and Node ≥ 18, then `pip install -r requirements.txt`.
There is no `setup.sh`.

### Run the two processes by hand (debugging)

```bash
python backend/manage.py runserver          # API on http://127.0.0.1:8000
npm run dev --prefix frontend               # UI on http://localhost:5173
```

## Configuration (`.env`)

`.env` at the repo root (copied from `.env.example`) drives the backend:

- `MITO_DATA_ROOT` — root dir for all volume/label/submission files. The DB
  stores only paths relative to this root, **never** the image data. A relative
  value resolves against the repo root (so `./data` means `<repo>/data`).
- `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` — standard Django.
- `DJANGO_CORS_ORIGINS` — browser origins allowed to call the API.
- `MITO_DEFAULT_Z_STEP` — default frames per task when splitting.

Everything else is in `backend/config/settings.py`.

## Dev data & accounts

Standard accounts (password `demo12345`): `manager` (manager) and `alice`,
`bob`, `carol`, `dave` (annotators). **No data is pre-registered** — register
datasets yourself in the app (as the manager, or sign up a requester).

```bash
cd backend
python manage.py seed_dev            # create the standard accounts (no data)
python manage.py seed_dev --fresh    # clear existing data first, then seed
python manage.py dev_status          # counts of current data
python manage.py clear_dev_data      # delete dev data (prompts; --no-input to skip)
python manage.py clear_dev_data --keep-users
python manage.py reset_dev           # clear + migrate + reseed accounts (one shot)
```

`clear_dev_data` / `reset_dev` always preserve superusers and refuse to run when
`DEBUG=False` unless given `--force`. Automated tests build their own throwaway
data and are independent of these commands. In development the login page shows a
click-to-fill list of these accounts (dev builds only).

Create the Manager Admin superuser with `python manage.py createsuperuser` (see
[admin.md](admin.md) for how manager accounts get admin access).

## Workflow CLIs

```bash
python backend/manage.py split_volume --volume-id 1 --z-step 16
python backend/manage.py assign_tasks --project-id 1
python backend/manage.py progress_report --project-id 1
```

These are thin wrappers over the service layer (same logic as the SPA/admin).

## Tests & build

```bash
cd backend && python manage.py test        # backend (run from backend/)
python backend/manage.py check             # system checks
npm run build --prefix frontend            # frontend typecheck (tsc) + build
```

See [codemap.md](codemap.md#where-the-tests-live) for which tests cover what.

## Remote / HPC access

The servers bind to localhost by default. Forward the port over SSH:

```bash
ssh -L 5173:localhost:5173 <username>@<server>   # then open http://localhost:5173
```

…or bind to all interfaces and skip auto-opening a browser:

```bash
VITE_HOST=0.0.0.0 DJANGO_HOST=0.0.0.0 NO_BROWSER=1 ./dev.sh
```

Overrides (defaults): `DJANGO_HOST=127.0.0.1`, `DJANGO_PORT=8000`,
`VITE_HOST=127.0.0.1`, `VITE_PORT=5173`, `NO_BROWSER=0`. Docker is not required
and no graphical desktop is assumed.
