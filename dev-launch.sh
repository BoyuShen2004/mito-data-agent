#!/usr/bin/env bash
#
# dev-launch.sh — start Mito Data Agent (Django + Vite).
#
#   ./dev-launch.sh
#
# Assumes ./dev-setup.sh has already been run. Always frees ports left by a
# previous launch on this node, then starts both servers and stops them
# together on one Ctrl+C.
#
# On a SLURM compute node reached via srun/salloc from a login node: if
# $SLURM_SUBMIT_HOST is set (SLURM sets this automatically) and password-less
# SSH back to it works, this also opens a reverse tunnel so the app's ports
# appear on the login node too — needed because VS Code/Cursor Remote-SSH's
# port forwarding only ever sees whatever machine it's actually connected to
# (normally the login node), never a compute node one hop further in. Set
# LOGIN_NODE=<host> to override if $SLURM_SUBMIT_HOST is wrong or unset.
#
# Host/port are configurable for remote/HPC use, e.g.:
#   VITE_HOST=0.0.0.0 DJANGO_HOST=0.0.0.0 NO_BROWSER=1 ./dev-launch.sh
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

CONDA_ENV_NAME="mito-data-agent"

DJANGO_HOST="${DJANGO_HOST:-127.0.0.1}"
DJANGO_PORT="${DJANGO_PORT:-8000}"
VITE_HOST="${VITE_HOST:-127.0.0.1}"
VITE_PORT="${VITE_PORT:-5173}"
NO_BROWSER="${NO_BROWSER:-0}"

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      cat <<'EOF'
Usage: ./dev-launch.sh

  Always frees Django/Vite ports from a previous launch on this node, then
  starts both servers fresh. Ctrl+C stops this launch cleanly.

Env overrides: DJANGO_HOST DJANGO_PORT VITE_HOST VITE_PORT NO_BROWSER
               LOGIN_NODE=<host>
EOF
      exit 0
      ;;
  esac
done

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

command -v python >/dev/null 2>&1 || die "python not found. Activate the '${CONDA_ENV_NAME}' conda environment first."
command -v npm    >/dev/null 2>&1 || die "npm not found. Activate the '${CONDA_ENV_NAME}' conda environment first."
[[ -f "$REPO_ROOT/.env" ]] || die "No .env found. Run ./dev-setup.sh first."
[[ -d "$REPO_ROOT/frontend/node_modules" ]] || die "Frontend dependencies not installed. Run ./dev-setup.sh first."

# --- Port preflight ---------------------------------------------------------
# Always clear our ports before start. A previous ./dev-launch.sh that wasn't
# Ctrl+C'd (closed terminal, SSH drop, killed outer srun, second launch from
# another shell) otherwise leaves Django on :8000 and/or Vite on :5173 — Vite
# then hops to :5174 while Django dies with "That port is already in use".
port_pids() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -tlnp 2>/dev/null | awk -v p=":$port" '
      index($4, p) {
        while (match($0, /pid=[0-9]+/)) {
          print substr($0, RSTART+4, RLENGTH-4)
          $0 = substr($0, RSTART+RLENGTH)
        }
      }' | sort -u
  elif command -v lsof >/dev/null 2>&1; then
    lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
  fi
}

free_port() {
  local port="$1" label="$2"
  local pids
  pids="$(port_pids "$port" | tr '\n' ' ')"
  pids="${pids%% }"
  pids="${pids## }"
  if [[ -z "$pids" ]]; then
    return 0
  fi
  warn "Freeing stale ${label} on :${port} (pids: ${pids})"
  # shellcheck disable=SC2086
  kill -TERM $pids 2>/dev/null || true
  sleep 1
  # shellcheck disable=SC2086
  kill -KILL $pids 2>/dev/null || true
  sleep 0.3
  if [[ -n "$(port_pids "$port")" ]]; then
    die "Could not free port ${port}. Free it manually (kill those pids), then re-run."
  fi
  ok "Port ${port} is free."
}

info "Clearing ports ${DJANGO_PORT} / ${VITE_PORT} if still held by a previous launch…"
free_port "$DJANGO_PORT" "Django"
free_port "$VITE_PORT" "Vite"

# --- Start both servers -----------------------------------------------------
# Each server runs in its own process group so one Ctrl+C tears down the whole
# tree (including Vite/autoreload children) with no orphans left behind.
SETSID=""
command -v setsid >/dev/null 2>&1 && SETSID="setsid"

BACKEND_PID=""
FRONTEND_PID=""
TUNNEL_PID=""

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
  [[ -n "$TUNNEL_PID" ]] && kill "$TUNNEL_PID" 2>/dev/null
  stop_proc "$FRONTEND_PID"
  stop_proc "$BACKEND_PID"
  wait 2>/dev/null || true
}

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

# Django checks the incoming request's Host header against ALLOWED_HOSTS and
# otherwise returns 400 Bad Request — same class of problem as Vite's
# allowedHosts (see vite.config.ts): a remote-dev proxy (VS Code/Cursor
# Remote-SSH port forwarding, an SSH tunnel through a jump host, a machine's
# real network IP) can present a Host header that isn't literally
# "localhost"/"127.0.0.1", and the request gets rejected before this app
# sees it. `*` disables the check — fine for a local/HPC dev server, never
# for a public deployment. Scoped to this launcher only (exported here, not
# changed in settings.py's committed default) so it doesn't affect anyone
# running Django directly.
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-*}"

info "Starting Django backend on http://${DJANGO_HOST}:${DJANGO_PORT}"
$SETSID python "$REPO_ROOT/backend/manage.py" runserver "${DJANGO_HOST}:${DJANGO_PORT}" &
BACKEND_PID=$!

# Django/Vite run on the same machine, so Vite always reaches the backend via
# loopback regardless of what DJANGO_HOST is *bound* to — "0.0.0.0" is a bind
# address (means "all interfaces"), not something you can connect *to*.
export VITE_BACKEND_URL="http://127.0.0.1:${DJANGO_PORT}"
export VITE_HOST VITE_PORT

info "Starting React frontend on http://${VITE_HOST}:${VITE_PORT}"
# --strictPort: fail if VITE_PORT is taken instead of silently moving to
# 5174/5175 (which desyncs the printed URL, Cursor port-forward, and the
# login-node tunnel that still targets VITE_PORT).
$SETSID npm run dev --prefix "$REPO_ROOT/frontend" -- --host "$VITE_HOST" --port "$VITE_PORT" --strictPort &
FRONTEND_PID=$!

sleep 2
APP_URL="http://localhost:${VITE_PORT}"

if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
  wait "$BACKEND_PID" 2>/dev/null
  die "Django backend failed to start — see the output above."
fi
if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
  wait "$FRONTEND_PID" 2>/dev/null
  die "Vite frontend failed to start — see the output above."
fi

# --- Bridge to a login node, if we're on a SLURM compute node --------------
# VS Code/Cursor Remote-SSH forwards ports on whatever machine its remote
# connection actually lands on — typically a cluster's login node, even when
# a terminal there has hopped further to a compute node (srun/salloc/ssh).
# Ports opened only on the compute node are invisible to that forwarding no
# matter what this app does — confirmed directly: same app, same script,
# reachable from a login node, not from a compute node.
#
# Login-node detection, in order:
#   1. LOGIN_NODE=<host> — explicit override, always wins.
#   2. $SLURM_SUBMIT_HOST — SLURM's documented mechanism for this. Kept as a
#      fallback since some clusters populate it, but verified EMPTY on this
#      one for a real interactive srun/salloc session — don't rely on it alone.
#   3. `scontrol show job $SLURM_JOB_ID` -> AllocNode — the node that issued
#      srun/salloc, tracked by the SLURM controller itself independent of
#      what the job's own environment exports. Confirmed populated and
#      correct here even when SLURM_SUBMIT_HOST is empty.
detect_login_node() {
  if [[ -n "${LOGIN_NODE:-}" ]]; then
    printf '%s' "$LOGIN_NODE"; return 0
  fi
  if [[ -n "${SLURM_SUBMIT_HOST:-}" ]]; then
    printf '%s' "$SLURM_SUBMIT_HOST"; return 0
  fi
  if [[ -n "${SLURM_JOB_ID:-}" ]] && command -v scontrol >/dev/null 2>&1; then
    local alloc
    alloc="$(scontrol show job "$SLURM_JOB_ID" 2>/dev/null \
      | grep -oP 'AllocNode:Sid=\K[^:]+' 2>/dev/null | head -1 || true)"
    if [[ -n "$alloc" ]]; then
      printf '%s' "$alloc"; return 0
    fi
  fi
  return 1
}

CURRENT_HOST="$(hostname 2>/dev/null || true)"
CURRENT_HOST_SHORT="$(hostname -s 2>/dev/null || true)"
LOGIN_HOST=""
if detect_login_node_result="$(detect_login_node)"; then
  LOGIN_HOST="$detect_login_node_result"
fi

if [[ -n "$LOGIN_HOST" && "$LOGIN_HOST" != "$CURRENT_HOST" && "$LOGIN_HOST" != "$CURRENT_HOST_SHORT" ]] \
  && command -v ssh >/dev/null 2>&1; then
  info "On a compute node (${CURRENT_HOST:-this host}) — bridging ports to ${LOGIN_HOST}…"
  TUNNEL_ERR="$(mktemp 2>/dev/null || echo /tmp/mito-tunnel-err.$$)"
  ssh -N -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new -o ExitOnForwardFailure=yes \
    -R "${VITE_PORT}:localhost:${VITE_PORT}" \
    -R "${DJANGO_PORT}:localhost:${DJANGO_PORT}" \
    "$LOGIN_HOST" 2>"$TUNNEL_ERR" &
  TUNNEL_PID=$!
  sleep 2
  if kill -0 "$TUNNEL_PID" 2>/dev/null; then
    # The tunnel process being alive only means SSH connected and both -R
    # binds succeeded — it does NOT prove the app is actually reachable
    # through it end-to-end. Verify for real: ask the login node itself to
    # curl the forwarded port.
    if ssh -o BatchMode=yes -o ConnectTimeout=5 "$LOGIN_HOST" \
         "curl -s -o /dev/null -m 5 -w '%{http_code}' http://127.0.0.1:${VITE_PORT}/" 2>/dev/null \
         | grep -qE '^(2|3)[0-9][0-9]$'; then
      ok "Bridged to ${LOGIN_HOST} — verified reachable from there. Open the app the same way you would from ${LOGIN_HOST}."
    else
      warn "SSH tunnel to ${LOGIN_HOST} is up, but it still can't reach the app through it. Give it a few more seconds (Vite may still be starting) and try opening from ${LOGIN_HOST}; if that keeps failing, the bridge itself isn't working end-to-end."
    fi
  else
    warn "Couldn't bridge to ${LOGIN_HOST}: $(tr -s '\n' ' ' < "$TUNNEL_ERR" 2>/dev/null | sed 's/ *$//')"
    warn "Open from ${LOGIN_HOST} directly, or set LOGIN_NODE=<host> if that's the wrong one."
    TUNNEL_PID=""
  fi
  rm -f "$TUNNEL_ERR"
elif [[ -z "$LOGIN_HOST" && -n "${SLURM_JOB_ID:-}" ]]; then
  warn "On a SLURM compute node but couldn't determine the login node automatically (SLURM_SUBMIT_HOST empty, scontrol lookup failed). If VS Code/Cursor can't reach ${APP_URL:-the app}, set LOGIN_NODE=<host> and re-run."
fi

printf '\n%s\n' "${BOLD}${GREEN}Mito Data Agent is running.${RESET}"
printf '  %s%s%s\n' "$BOLD" "$APP_URL" "$RESET"
printf '  Ctrl+C to stop\n\n'

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
