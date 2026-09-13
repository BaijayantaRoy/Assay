#!/usr/bin/env bash
# =============================================================================
#  Assay — Developer Control Script (macOS / Linux)
#
#  The twin of start-assay.bat. Same commands, same flags, same exit codes, so a
#  README instruction is correct on every platform.
#
#    ./start-assay.sh <command> [flags]
#
#  Commands: fresh nuke start stop restart clean reset status doctor logs
#            test verify help
#  Flags:    -y  --no-frontend  --no-install  --deep  --port-api N  --port-web N
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")"

PROJECT="Assay"
API_PORT="${API_PORT:-8001}"
WEB_PORT="${WEB_PORT:-3001}"
STATE_DIR=".assay/state"
LOG_DIR=".assay/logs"
ASSUME_YES=0
SKIP_FRONTEND=0
SKIP_INSTALL=0
DEEP=0
EXITCODE=0
TS="$(date +%Y%m%d-%H%M%S)"

CMD="${1:-menu}"; shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    -y|--yes)       ASSUME_YES=1 ;;
    --no-frontend)  SKIP_FRONTEND=1 ;;
    --no-install)   SKIP_INSTALL=1 ;;
    --deep)         DEEP=1 ;;
    --port-api)     API_PORT="$2"; shift ;;
    --port-web)     WEB_PORT="$2"; shift ;;
  esac
  shift
done

mkdir -p "$STATE_DIR" "$LOG_DIR"

C_OK=$'\033[32m'; C_BAD=$'\033[31m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
[ -t 1 ] || { C_OK=""; C_BAD=""; C_DIM=""; C_OFF=""; }

banner() { printf '\n==============================================================\n %s — dev control\n==============================================================\n\n' "$PROJECT"; }
ok()     { printf '  %s[ok]%s %s\n' "$C_OK" "$C_OFF" "$1"; }
step()   { printf '  [..] %s\n' "$1"; }
bad()    { printf '  %s[X]%s %s\n' "$C_BAD" "$C_OFF" "$1"; }

confirm() {
  [ "$ASSUME_YES" = "1" ] && return 0
  printf '  %s? Type YES to continue: ' "$1"
  read -r ans
  [ "$ans" = "YES" ] && return 0
  echo "  Aborted. Nothing was changed."
  return 1
}

http_code() {
  # On a refused connection curl BOTH prints 000 and exits non-zero, so a
  # `curl … || echo 000` fallback emits "000000" — which then fails every
  # equality test and reports a dead service as healthy. Capture, then normalise.
  local code=""
  if command -v curl >/dev/null 2>&1; then
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$1" 2>/dev/null)"
  elif command -v wget >/dev/null 2>&1; then
    code="$(wget -q -T 3 -O /dev/null -S "$1" 2>&1 | awk '/HTTP\//{c=$2} END{print c}')"
  fi
  case "$code" in
    ''|000|000000) echo "000" ;;
    *)             echo "$code" ;;
  esac
}

is_up() { [ "$1" != "000" ]; }

kill_port() {  # $1 port, $2 label
  local pids
  pids="$(lsof -ti tcp:"$1" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -z "$pids" ]; then
    echo "       nothing listening on port $1"
    return
  fi
  for p in $pids; do
    kill -9 "$p" 2>/dev/null && echo "       killed $2 pid $p on port $1"
  done
}

detect_tools() {
  command -v python3 >/dev/null 2>&1 || { bad "python3 not found"; return 1; }
  if [ "$SKIP_FRONTEND" = "0" ] && ! command -v node >/dev/null 2>&1; then
    bad "node not found — install it, or use --no-frontend"; return 1
  fi
  return 0
}

ensure_venv() {
  [ -x venv/bin/python ] || { step "creating virtual environment"; python3 -m venv venv || return 1; }
  ok "venv ready"; return 0
}

install_deps() {
  step "installing backend dependencies"
  venv/bin/python -m pip install --upgrade pip -q >/dev/null 2>&1
  venv/bin/python -m pip install -r backend/requirements.txt -q || { bad "backend deps failed"; return 1; }
  # The project was called MyPromptLibrary and shipped an `mpl` CLI until ADR-0009. A venv
  # created before that still has mpl-core/mpl-cli/mpl-mcp installed, with .pth files
  # pointing at packages/mpl-core/src — a directory that no longer exists. pip will not
  # remove them, because the new distributions have different names, so the two sets sit
  # side by side and the stale half breaks imports and entry-point discovery.
  if venv/bin/python -m pip show mpl-core >/dev/null 2>&1; then
    step "removing packages left over from before the rename to Assay"
    venv/bin/python -m pip uninstall -y mpl-core mpl-cli mpl-mcp mypromptlibrary >/dev/null 2>&1 || true
    rm -f venv/lib/python*/site-packages/_editable_impl_mpl_*.pth \
          venv/lib/python*/site-packages/__editable__.mpl_* \
          venv/bin/mpl venv/bin/mpl-mcp 2>/dev/null || true
    ok "stale packages removed"
  fi

  step "installing assay packages (editable)"
  venv/bin/python -m pip install -e packages/assay-core -e packages/assay-cli -e packages/assay-mcp -q \
    || { bad "assay package install failed"; return 1; }

  # pip exiting 0 does not mean the package imports. An editable install whose target
  # directory was renamed leaves pip happy and Python unable to find anything — exactly
  # the state a rename produces. Check the thing we actually need.
  venv/bin/python -c "import assay_core, assay_cli" 2>/dev/null || {
    bad "assay installed but cannot be imported — usually a venv from an older checkout"
    echo "     Fix: rm -rf venv && ./start-assay.sh fresh"
    return 1
  }
  ok "python dependencies installed"
  if [ "$SKIP_FRONTEND" = "0" ] && [ ! -d frontend/node_modules ]; then
    step "installing frontend dependencies"
    (cd frontend && npm install --silent) || { bad "npm install failed"; return 1; }
  fi
  [ "$SKIP_FRONTEND" = "0" ] && ok "frontend dependencies present"
  return 0
}

stop_all() {
  step "stopping services"
  kill_port "$API_PORT" backend
  kill_port "$WEB_PORT" frontend
  ok "services stopped"
}

clean_caches() {
  step "clearing caches"
  rm -rf .pytest_cache frontend/out .ruff_cache .mypy_cache 2>/dev/null || true
  # frontend/.next is Next.js's incremental build cache (~90 MB). Deleting it on every
  # start forces a full cold compile taking minutes, which makes the UI look broken
  # while it is merely rebuilding. Only --deep removes it.
  [ "$DEEP" = "1" ] && rm -rf frontend/.next
  # -prune, not -not -path. The latter filters find's *output* while still walking
  # every file in venv/ and node_modules/ — 30s+ on this repo. Pruning skips the
  # subtree entirely. Same mistake, same fix, as assay_core.promptfile.discover().
  find . \( -path ./venv -o -path ./frontend/node_modules -o -path ./.git \) -prune -o \
       -type d \( -name __pycache__ -o -name '*.egg-info' \) -print0 2>/dev/null \
    | xargs -0 rm -rf 2>/dev/null || true
  echo "       removed __pycache__ and egg-info"
  if [ "$DEEP" = "1" ]; then
    rm -rf venv frontend/node_modules
    echo "       deep clean: venv and node_modules removed"
  fi
  ok "caches cleared"
}

reset_state() {
  step "deleting local state"
  if [ -f database.db ]; then
    cp database.db "$STATE_DIR/database-backup-$TS.db" 2>/dev/null || true
    rm -f database.db
    echo "       database.db deleted, backup in $STATE_DIR"
  fi
  rm -rf chroma_data .assay/memory "$LOG_DIR"
  mkdir -p "$LOG_DIR"
  ok "state cleared"
}

start_backend() {
  step "starting backend on port $API_PORT"
  export ASSAY_WORKSPACE="${ASSAY_WORKSPACE:-$PWD}"
  nohup venv/bin/python -m uvicorn backend.main:app --reload --port "$API_PORT" \
        > "$LOG_DIR/backend-$TS.log" 2>&1 &
  ln -sf "backend-$TS.log" "$LOG_DIR/backend-latest.log" 2>/dev/null || true
}

start_frontend() {
  step "starting frontend on port $WEB_PORT"
  (cd frontend && nohup npm run dev > "../$LOG_DIR/frontend-$TS.log" 2>&1 &)
  ln -sf "frontend-$TS.log" "$LOG_DIR/frontend-latest.log" 2>/dev/null || true
}

wait_ready() {
  # The backend answers in seconds; Next.js compiles on first start and can take
  # minutes cold. Giving them the same budget is what made the frontend look broken.
  step "waiting for services"
  [ "$SKIP_FRONTEND" = "0" ] && echo "       the frontend compiles on first start; a cold build can take 1-3 minutes"
  local api_up=0 web_up=0
  WEB_UP=0
  [ "$SKIP_FRONTEND" = "1" ] && web_up=1
  for i in $(seq 1 180); do
    [ "$api_up" = "0" ] && [ "$(http_code "http://127.0.0.1:$API_PORT/health")" = "200" ] \
      && { api_up=1; echo "       backend  ready after ${i}s"; }
    # Next.js binds the port before it can serve, so "answered" is not "ready".
    if [ "$web_up" = "0" ]; then
      c="$(http_code "http://127.0.0.1:$WEB_PORT")"
      case "$c" in
        200|307|308) web_up=1; echo "       frontend ready after ${i}s" ;;
        5*) echo "       frontend is up but returning HTTP $c - check its log" ;;
      esac
    fi
    [ "$api_up" = "1" ] && [ "$web_up" = "1" ] && break
    if [ "$api_up" = "1" ] && [ "$web_up" = "0" ] && [ $((i % 15)) -eq 0 ]; then
      echo "       still compiling the frontend... ${i}s"
    fi
    sleep 1
  done
  WEB_UP=$web_up
  if [ "$api_up" = "1" ]; then ok "backend healthy"; else
    bad "backend did not answer in 180s — see $LOG_DIR/backend-latest.log"
    EXITCODE=1
  fi
  if [ "$SKIP_FRONTEND" = "0" ] && [ "$web_up" = "0" ]; then
    echo
    bad "the frontend has not answered after 3 minutes"
    echo "      It may still be compiling. Try http://localhost:$WEB_PORT shortly."
    echo "      Next.js buffers redirected output, so its log often lags:"
    [ -f "$LOG_DIR/frontend-latest.log" ] && tail -20 "$LOG_DIR/frontend-latest.log"
    echo "      To see the real error:  cd frontend && npm run dev"
  fi
}

collect_status() {
  STATUS_FILE="$STATE_DIR/status-$TS.txt"
  local api web branch commit
  api="$(http_code "http://127.0.0.1:$API_PORT/health")"
  web="$(http_code "http://127.0.0.1:$WEB_PORT")"
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  commit="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  {
    echo "  $PROJECT status — $(date)"
    echo
    echo "  backend  http://127.0.0.1:$API_PORT   $(is_up "$api" && echo up || echo down)  (HTTP $api)"
    echo "  frontend http://127.0.0.1:$WEB_PORT   $(is_up "$web" && echo up || echo down)  (HTTP $web)"
    echo "  docs     http://127.0.0.1:$API_PORT/docs"
    echo
    echo "  git      $branch @ $commit"
    [ -x venv/bin/python ] && echo "  python   $(venv/bin/python --version 2>&1)" || echo "  python   venv not built"
    [ -f database.db ] && echo "  database present" || echo "  database absent"
  } > "$STATUS_FILE"
  cat > "$STATE_DIR/status-$TS.json" <<JSON
{
  "timestamp": "$TS",
  "backend": { "port": $API_PORT, "http": "$api", "state": "$(is_up "$api" && echo up || echo down)" },
  "frontend": { "port": $WEB_PORT, "http": "$web", "state": "$(is_up "$web" && echo up || echo down)" },
  "git": { "branch": "$branch", "commit": "$commit" }
}
JSON
}

summary() {
  echo
  echo "=============================================================="
  [ "$EXITCODE" = "0" ] && echo "  RUNNING" || echo "  STARTED WITH PROBLEMS — see above"
  echo "=============================================================="
  echo
  echo "   Web UI      http://localhost:$WEB_PORT        file-backed /v1 workbench"
  echo "   API docs    http://localhost:$API_PORT/docs   harness, loop, memory,"
  echo "                                            redteam, calibration"
  echo
  echo "   Logs        ./start-assay.sh logs      Status  ./start-assay.sh status"
  echo "   Diagnostics ./start-assay.sh doctor    Stop    ./start-assay.sh stop"
  echo
}

doctor() {
  local doc="$STATE_DIR/doctor-$TS.txt"
  echo "  Collecting diagnostics (runs the test suite)…"
  {
    echo "============================================================"
    echo " $PROJECT diagnostic report — $(date)"
    echo " root: $PWD"
    echo "============================================================"
    echo; echo "--- TOOLCHAIN ---"
    echo "python: $(python3 --version 2>&1)"
    echo "node:   $(node --version 2>&1 || echo absent)"
    echo "git:    $(git --version 2>&1)"
    echo; echo "--- GIT ---"
    echo "branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
    echo "commit: $(git rev-parse --short HEAD 2>/dev/null)"
    git status --short 2>&1
    echo; echo "--- PORTS ---"
    lsof -i tcp:"$API_PORT" -sTCP:LISTEN 2>/dev/null || echo "port $API_PORT free"
    lsof -i tcp:"$WEB_PORT" -sTCP:LISTEN 2>/dev/null || echo "port $WEB_PORT free"
    echo; echo "--- HEALTH ---"
    for u in "/health" "/v1/health" "/docs"; do
      echo "  http://127.0.0.1:$API_PORT$u -> $(http_code "http://127.0.0.1:$API_PORT$u")"
    done
    echo; echo "--- ENVIRONMENT (names only, never values) ---"
    for k in OPENAI_API_KEY ANTHROPIC_API_KEY GOOGLE_API_KEY ASSAY_WORKSPACE ASSAY_MEMORY_ROOT; do
      [ -n "${!k:-}" ] && echo "  $k: set" || echo "  $k: not set"
    done
    echo; echo "--- DISK ---"
    du -sh venv frontend/node_modules chroma_data .assay/memory frontend/.next 2>/dev/null || true
    echo; echo "--- PLUGINS ---"
    [ -x venv/bin/python ] && venv/bin/python -c "from assay_core import get_registry; d=get_registry().describe(); [print(f'  {g:20s} {len(v):3d}') for g,v in sorted(d.items()) if v]; print(f'  TOTAL {sum(len(v) for v in d.values())}')" 2>&1
    echo; echo "--- TESTS ---"
    [ -x venv/bin/python ] && venv/bin/python -m pytest packages/assay-core/tests -q 2>&1 | tail -5
    [ -x venv/bin/python ] && venv/bin/python -m pytest backend/tests -q 2>&1 | tail -5
    echo; echo "--- LOG TAIL ---"
    [ -f "$LOG_DIR/backend-latest.log" ] && tail -30 "$LOG_DIR/backend-latest.log"
  } > "$doc" 2>&1
  echo "  Report: $doc"
  echo "  Contains no secret values — safe to attach to a bug report."
}

case "$CMD" in
  fresh)
    banner; collect_status; cp "$STATUS_FILE" "$STATE_DIR/snapshot-before-fresh-$TS.txt"
    stop_all; clean_caches
    detect_tools || exit 1; ensure_venv || exit 1
    [ "$SKIP_INSTALL" = "0" ] && { install_deps || exit 1; }
    start_backend; [ "$SKIP_FRONTEND" = "0" ] && start_frontend
    wait_ready; collect_status; summary; exit $EXITCODE ;;
  nuke)
    banner; confirm "Wipe all state and rebuild from scratch" || exit 1
    stop_all; reset_state; clean_caches
    detect_tools || exit 1; ensure_venv || exit 1; install_deps || exit 1
    start_backend; [ "$SKIP_FRONTEND" = "0" ] && start_frontend
    wait_ready; collect_status; summary; exit $EXITCODE ;;
  start)
    banner; detect_tools || exit 1; ensure_venv || exit 1
    [ "$SKIP_INSTALL" = "0" ] && { install_deps || exit 1; }
    start_backend; [ "$SKIP_FRONTEND" = "0" ] && start_frontend
    wait_ready; summary; exit $EXITCODE ;;
  stop)     banner; stop_all; echo; echo "  Stopped." ;;
  restart)  banner; stop_all; start_backend
            [ "$SKIP_FRONTEND" = "0" ] && start_frontend
            wait_ready; summary; exit $EXITCODE ;;
  clean)    banner; clean_caches; echo; echo "  Caches cleared. Data untouched." ;;
  reset)    banner; confirm "Delete all local state" || exit 1; stop_all; reset_state ;;
  status)   banner; collect_status; cat "$STATUS_FILE"; echo "  Saved to $STATUS_FILE" ;;
  doctor)   banner; doctor ;;
  logs)     banner
            [ -f "$LOG_DIR/backend-latest.log" ]  && { echo "  ---- backend ----";  tail -40 "$LOG_DIR/backend-latest.log"; }
            [ -f "$LOG_DIR/frontend-latest.log" ] && { echo "  ---- frontend ----"; tail -40 "$LOG_DIR/frontend-latest.log"; } ;;
  test)     banner; detect_tools || exit 1; ensure_venv || exit 1
            venv/bin/python -m pytest packages/assay-core/tests -q; core=$?
            venv/bin/python -m pytest backend/tests -q; be=$?
            [ $core -eq 0 ] && [ $be -eq 0 ] && { ok "all tests passed"; exit 0; }
            bad "tests failed (core=$core backend=$be)"; exit 4 ;;
  verify)   banner; wait_ready; summary; exit $EXITCODE ;;
  menu|help|*)
    banner
    sed -n '3,15p' "$0" | sed 's/^# \{0,1\}//'
    echo "  Examples:"
    echo "    ./start-assay.sh fresh                everyday restart"
    echo "    ./start-assay.sh fresh --no-frontend  backend only"
    echo "    ./start-assay.sh nuke -y              wipe and rebuild"
    echo "    ./start-assay.sh doctor               report for a bug"
    ;;
esac
