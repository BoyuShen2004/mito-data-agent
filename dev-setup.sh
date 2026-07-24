#!/usr/bin/env bash
#
# dev-setup.sh — verify/prepare everything Mito Data Agent needs to run.
#
#   conda activate mito-data-agent
#   ./dev-setup.sh
#
# Checks required tools, creates a local .env on first run, installs frontend
# dependencies only when missing or changed, and applies Django migrations.
# Safe to re-run any time. Run this once (or whenever dependencies/migrations
# change), then use ./dev-launch.sh to start the app.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

CONDA_ENV_NAME="mito-data-agent"
CACHE_DIR="$REPO_ROOT/.dev-cache"
FRONTEND_DEPS_MARKER="$CACHE_DIR/frontend-deps.sha256"

if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; RED=$'\033[31m'; GREEN=$'\033[32m'
  YELLOW=$'\033[33m'; BLUE=$'\033[34m'; RESET=$'\033[0m'
else
  BOLD=""; RED=""; GREEN=""; YELLOW=""; BLUE=""; RESET=""
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

if [[ "${CONDA_DEFAULT_ENV:-}" != "$CONDA_ENV_NAME" ]]; then
  warn "conda env '${CONDA_ENV_NAME}' is not active (current: '${CONDA_DEFAULT_ENV:-none}')."
  warn "Recommended: conda activate ${CONDA_ENV_NAME}"
fi

# --- 2. Backend dependencies (verify, never silently install) --------------
info "Checking backend Python dependencies"
if ! python - <<'PY' 2>/dev/null
import django, rest_framework, corsheaders, dotenv, numpy, tifffile  # noqa: F401
PY
then
  die "backend dependencies are missing (Django / DRF / numpy / tifffile / ...). Install with: conda env update -f environment.yml --prune"
fi
ok "Django $(python -c 'import django; print(django.get_version())') and REST framework available"

# --- 3. Local configuration (.env) -----------------------------------------
if [[ ! -f "$REPO_ROOT/.env" ]]; then
  info "Creating .env from .env.example (first run)"
  cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
  ok ".env created — review MITO_DATA_ROOT in it before registering real data"
else
  ok ".env present (left untouched)"
fi

# --- 4. Frontend dependencies (install only when missing or changed) -------
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

# --- 5. Django system checks + migrations ----------------------------------
info "Running Django system checks"
python "$REPO_ROOT/backend/manage.py" check

info "Applying database migrations"
python "$REPO_ROOT/backend/manage.py" migrate --noinput

printf '\n'
ok "Setup complete — run ./dev-launch.sh to start the app."
