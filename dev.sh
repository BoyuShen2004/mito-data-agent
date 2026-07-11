#!/usr/bin/env bash
#
# dev.sh — the single command to run Mito Data Agent for local development.
#
#   conda activate mito-data-agent
#   ./dev.sh
#
# It verifies the environment, creates a local .env on first run, installs
# dependencies only when they are missing or have changed, applies Django
# migrations, then starts BOTH the Django API and the React/Vite dev server.
# One Ctrl+C stops everything.
#
# Host/port are configurable for remote/HPC use, e.g.:
#   VITE_HOST=0.0.0.0 DJANGO_HOST=0.0.0.0 NO_BROWSER=1 ./dev.sh
#
set -euo pipefail

# --- Locate the repo root (works no matter where dev.sh is invoked from) ---
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

CONDA_ENV_NAME="mito-data-agent"
CACHE_DIR="$REPO_ROOT/.dev-cache"
FRONTEND_DEPS_MARKER="$CACHE_DIR/frontend-deps.sha256"

# --- Configurable hosts/ports (sensible local defaults) --------------------
DJANGO_HOST="${DJANGO_HOST:-127.0.0.1}"
DJANGO_PORT="${DJANGO_PORT:-8000}"
VITE_HOST="${VITE_HOST:-127.0.0.1}"
VITE_PORT="${VITE_PORT:-5173}"
NO_BROWSER="${NO_BROWSER:-0}"

# --- Pretty output ---------------------------------------------------------
if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
  YELLOW=$'\033[33m'; BLUE=$'\033[34m'; RESET=$'\033[0m'
else
  BOLD=""; DIM=""; RED=""; GREEN=""; YELLOW=""; BLUE=""; RESET=""
fi
info()  { printf '%s\n' "${BLUE}==>${RESET} $*"; }
ok()    { printf '%s\n' "${GREEN}  ✓${RESET} $*"; }
warn()  { printf '%s\n' "${YELLOW}  !${RESET} $*" >&2; }
die()   { printf '%s\n' "${RED}error:${RESET} $*" >&2; exit 1; }

# --- 1. Required tools -----------------------------------------------------
info "Checking required tools"
command -v python >/dev/null 2>&1 || die "python not found. Activate the '${CONDA_ENV_NAME}' conda environment first."
command -v node   >/dev/null 2>&1 || die "node not found. Activate the '${CONDA_ENV_NAME}' conda environment (it provides Node), or install Node >= 18."
command -v npm    >/dev/null 2>&1 || die "npm not found. Activate the '${CONDA_ENV_NAME}' conda environment, or install Node >= 18."
ok "python $(python --version 2>&1 | awk '{print $2}'), node $(node --version), npm $(npm --version)"

# --- 2. Conda environment sanity check -------------------------------------
# We do not create or modify the environment automatically; we only nudge the
# developer if the expected one is not active, then verify the deps directly.
if [[ "${CONDA_DEFAULT_ENV:-}" != "$CONDA_ENV_NAME" ]]; then
  warn "conda env '${CONDA_ENV_NAME}' is not active (current: '${CONDA_DEFAULT_ENV:-none}')."
  warn "Recommended: conda activate ${CONDA_ENV_NAME}"
fi

# --- 3. Backend dependencies (verify, never silently install) --------------
info "Checking backend Python dependencies"
if ! python - <<'PY' 2>/dev/null
import django, rest_framework, corsheaders, dotenv, numpy, tifffile  # noqa: F401
PY
then
  die "$(cat <<EOF
backend dependencies are missing (Django / DRF / numpy / tifffile / ...).
Install them into the conda environment:

    conda env create -f environment.yml   # first time
    conda env update -f environment.yml --prune   # or, to update

...then re-run ./dev.sh
EOF
)"
fi
ok "Django $(python -c 'import django; print(django.get_version())') and REST framework available"

# --- 4. Local configuration (.env) -----------------------------------------
if [[ ! -f "$REPO_ROOT/.env" ]]; then
  info "Creating .env from .env.example (first run)"
  cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
  ok ".env created — review MITO_DATA_ROOT in it before registering real data"
else
  ok ".env present (left untouched)"
fi

# --- 5. Frontend dependencies (install only when missing or changed) -------
info "Checking frontend dependencies"
mkdir -p "$CACHE_DIR"
current_deps_hash() {
  cat "$REPO_ROOT/frontend/package.json" "$REPO_ROOT/frontend/package-lock.json" 2>/dev/null \
    | sha256sum | awk '{print $1}'
}
DEPS_HASH="$(current_deps_hash)"
need_install=0
if [[ ! -d "$REPO_ROOT/frontend/node_modules" ]]; then
  need_install=1
elif [[ ! -f "$FRONTEND_DEPS_MARKER" ]] || [[ "$(cat "$FRONTEND_DEPS_MARKER")" != "$DEPS_HASH" ]]; then
  need_install=1
fi

if [[ "$need_install" -eq 1 ]]; then
  if [[ -f "$REPO_ROOT/frontend/package-lock.json" ]]; then
    info "Installing frontend dependencies (npm ci)"
    npm ci --prefix "$REPO_ROOT/frontend"
  else
    info "Installing frontend dependencies (npm install)"
    npm install --prefix "$REPO_ROOT/frontend"
  fi
  current_deps_hash > "$FRONTEND_DEPS_MARKER"
  ok "frontend dependencies installed"
else
  ok "frontend dependencies up to date (skipping npm install)"
fi

# --- 6. Django system checks + migrations ----------------------------------
info "Running Django system checks"
python "$REPO_ROOT/backend/manage.py" check

info "Applying database migrations"
python "$REPO_ROOT/backend/manage.py" migrate --noinput

# Warn (do not auto-generate) if models have drifted from their migrations.
if ! python "$REPO_ROOT/backend/manage.py" makemigrations --check --dry-run >/dev/null 2>&1; then
  warn "Model changes detected without migrations."
  warn "Review them and run: python backend/manage.py makemigrations"
fi

# --- 7. Start both servers -------------------------------------------------
# Each server runs in its own process group so one Ctrl+C tears down the whole
# tree (including Vite/autoreload children) with no orphans left behind.
SETSID=""
command -v setsid >/dev/null 2>&1 && SETSID="setsid"

BACKEND_PID=""
FRONTEND_PID=""

stop_proc() {
  local pid="$1"
  [[ -z "$pid" ]] && return 0
  if [[ -n "$SETSID" ]]; then
    kill -TERM -- "-$pid" 2>/dev/null || true
  else
    kill -TERM "$pid" 2>/dev/null || true
  fi
}

CLEANED=""
cleanup() {
  [[ -n "$CLEANED" ]] && return 0
  CLEANED=1
  stop_proc "$FRONTEND_PID"
  stop_proc "$BACKEND_PID"
  wait 2>/dev/null || true
}

# Ctrl+C (or SIGTERM) is an intentional, clean stop — exit 0.
on_signal() {
  trap - INT TERM
  printf '\n'
  info "Shutting down…"
  cleanup
  ok "Stopped."
  exit 0
}
trap on_signal INT TERM
trap cleanup EXIT

info "Starting Django backend on http://${DJANGO_HOST}:${DJANGO_PORT}"
$SETSID python "$REPO_ROOT/backend/manage.py" runserver "${DJANGO_HOST}:${DJANGO_PORT}" &
BACKEND_PID=$!

# Point the Vite proxy at wherever the backend is actually listening.
export VITE_BACKEND_URL="http://${DJANGO_HOST}:${DJANGO_PORT}"
export VITE_HOST VITE_PORT

info "Starting React frontend on http://${VITE_HOST}:${VITE_PORT}"
$SETSID npm run dev --prefix "$REPO_ROOT/frontend" -- --host "$VITE_HOST" --port "$VITE_PORT" &
FRONTEND_PID=$!

# Give Vite a moment to boot, then print how to reach the app.
sleep 2
APP_URL="http://localhost:${VITE_PORT}"
printf '\n%s\n' "${BOLD}${GREEN}Mito Data Agent is running.${RESET}"
printf '  %sOpen the app:%s  %s%s%s\n' "$BOLD" "$RESET" "$BOLD" "$APP_URL" "$RESET"
printf '  %sBackend API:%s   http://%s:%s\n' "$DIM" "$RESET" "$DJANGO_HOST" "$DJANGO_PORT"
printf '  %sStop:%s          Ctrl+C\n' "$DIM" "$RESET"
if [[ "$VITE_HOST" == "0.0.0.0" || "$DJANGO_HOST" == "0.0.0.0" ]]; then
  printf '  %sRemote/HPC:%s    ssh -L %s:localhost:%s <user>@<server>, then open %s\n' \
    "$DIM" "$RESET" "$VITE_PORT" "$VITE_PORT" "$APP_URL"
fi
printf '\n'

# --- Optionally open a browser (never fatal) -------------------------------
if [[ "$NO_BROWSER" != "1" ]]; then
  if command -v open >/dev/null 2>&1; then
    open "$APP_URL" >/dev/null 2>&1 || true          # macOS
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$APP_URL" >/dev/null 2>&1 || true      # Linux desktop
  fi
fi

# --- Wait; if either server exits, tear the other down ---------------------
EXIT_CODE=0
while true; do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    warn "Django backend exited unexpectedly."
    EXIT_CODE=1
    break
  fi
  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    warn "React frontend exited unexpectedly."
    EXIT_CODE=1
    break
  fi
  sleep 1
done

exit "$EXIT_CODE"
