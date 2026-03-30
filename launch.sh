#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  Blueprint — Launch Script
#  Starts the FastAPI backend + Vite frontend, opens browser
# ──────────────────────────────────────────────────────────────

set -e

# Allow SCRIPT_DIR to be set externally (e.g. by Blueprint.app launcher)
SCRIPT_DIR="${SCRIPT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
cd "$SCRIPT_DIR"

# ── Parse arguments ─────────────────────────────────────────
PROFILE="base"
while [[ $# -gt 0 ]]; do
  case $1 in
    --profile)
      PROFILE="$2"
      shift 2
      ;;
    --profile=*)
      PROFILE="${1#*=}"
      shift
      ;;
    *)
      shift
      ;;
  esac
done

# Validate profile
case "$PROFILE" in
  base|inference|training|eval|full) ;;
  *)
    echo -e "\033[0;31mError: Unknown profile '$PROFILE'. Choose from: base, inference, training, eval, full\033[0m"
    exit 1
    ;;
esac

# ── Colors ──────────────────────────────────────────────────
# Basic ANSI (fallback)
CYAN='\033[0;36m'
GREEN='\033[0;32m'
DIM='\033[0;90m'
BOLD='\033[1m'
NC='\033[0m'
RED='\033[0;31m'
YELLOW='\033[0;33m'

# Brand true-color (24-bit — supported by Terminal.app 10.15+ and iTerm2)
TEAL='\033[38;2;47;252;200m'
BGREEN='\033[38;2;62;240;122m'
AMBER='\033[38;2;255;190;69m'
PURPLE='\033[38;2;168;126;255m'
BTEAL='\033[38;2;53;216;240m'

# ── Spinner ─────────────────────────────────────────────────
SPINNER_PID=""
SPINNER_MSG=""

start_spinner() {
  SPINNER_MSG="$1"
  if [ -t 1 ]; then
    local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
    (
      while true; do
        for f in "${frames[@]}"; do
          printf "\r  ${TEAL}%s${NC} ${DIM}%s${NC}" "$f" "$SPINNER_MSG"
          sleep 0.08
        done
      done
    ) &
    SPINNER_PID=$!
  else
    echo "  $SPINNER_MSG..."
  fi
}

stop_spinner() {
  local label="$1"
  local status="${2:-ok}"
  if [ -n "$SPINNER_PID" ]; then
    kill "$SPINNER_PID" 2>/dev/null
    wait "$SPINNER_PID" 2>/dev/null || true
    SPINNER_PID=""
  fi
  if [ -t 1 ]; then
    printf "\r\033[K"
  fi
  case "$status" in
    ok)   echo -e "  ${BGREEN}✔${NC} ${label}" ;;
    warn) echo -e "  ${AMBER}⚠${NC} ${label}" ;;
    fail) echo -e "  ${RED}✖${NC} ${label}" ;;
  esac
}

# ── Banner ──────────────────────────────────────────────────

print_banner() {
  # Set terminal tab title
  echo -ne "\033]0;Blueprint — Specific Labs\007"

  # Set iTerm2 tab color to brand teal
  if [ "$TERM_PROGRAM" = "iTerm.app" ]; then
    echo -ne "\033]6;1;bg;red;brightness;47\a"
    echo -ne "\033]6;1;bg;green;brightness;252\a"
    echo -ne "\033]6;1;bg;blue;brightness;200\a"
  fi

  echo ""
  echo -e "  ${TEAL}${BOLD}██████╗ ██╗     ██╗   ██╗███████╗██████╗ ██████╗ ██╗███╗   ██╗████████╗${NC}"
  echo -e "  ${TEAL}${BOLD}██╔══██╗██║     ██║   ██║██╔════╝██╔══██╗██╔══██╗██║████╗  ██║╚══██╔══╝${NC}"
  echo -e "  ${TEAL}██████╔╝██║     ██║   ██║█████╗  ██████╔╝██████╔╝██║██╔██╗ ██║   ██║${NC}"
  echo -e "  ${BTEAL}██╔══██╗██║     ██║   ██║██╔══╝  ██╔═══╝ ██╔══██╗██║██║╚██╗██║   ██║${NC}"
  echo -e "  ${PURPLE}██████╔╝███████╗╚██████╔╝███████╗██║     ██║  ██║██║██║ ╚████║   ██║${NC}"
  echo -e "  ${PURPLE}╚═════╝ ╚══════╝ ╚═════╝ ╚══════╝╚═╝     ╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝   ╚═╝${NC}"
  echo ""
  echo -e "  ${DIM}SPECIFIC LABS  ·  ML Experiment Workbench${NC}"
  echo ""
}

print_banner

# ── Check Python version (require 3.10+) ────────────────────

if ! command -v python3 >/dev/null 2>&1; then
  echo -e "  ${RED}✖${NC} python3 is not installed or not in PATH"
  exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
  echo -e "  ${RED}✖${NC} Python 3.10+ required ${DIM}(found $PYTHON_VERSION)${NC}"
  exit 1
fi

echo -e "  ${BGREEN}✔${NC} Python ${GREEN}$PYTHON_VERSION${NC}"

# ── Check Node.js version (require 18+) ─────────────────────

if ! command -v node >/dev/null 2>&1; then
  echo -e "  ${RED}✖${NC} Node.js is not installed or not in PATH"
  exit 1
fi

NODE_VERSION=$(node -v | sed 's/^v//' | cut -d. -f1)

if [ "$NODE_VERSION" -lt 18 ]; then
  echo -e "  ${RED}✖${NC} Node.js 18+ required ${DIM}(found v$(node -v | sed 's/^v//'))${NC}"
  exit 1
fi

echo -e "  ${BGREEN}✔${NC} Node.js ${GREEN}$(node -v)${NC}"

# ── Setup Python virtual environment ─────────────────────────

VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
  start_spinner "Creating virtual environment"
  python3 -m venv "$VENV_DIR"
  stop_spinner "Virtual environment created" "ok"
else
  echo -e "  ${BGREEN}✔${NC} Virtual env ${GREEN}.venv${NC}"
fi

# Activate venv — use this Python for all subsequent commands
PYTHON="$VENV_DIR/bin/python3"
PIP="$VENV_DIR/bin/pip3"

# ── Kill stale Blueprint processes ────────────────────────────

kill_stale() {
  local port=$1
  local pids
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo -e "  ${AMBER}⚠${NC} Killing stale process on port ${BOLD}$port${NC}"
    echo "$pids" | xargs kill -9 2>/dev/null || true
    sleep 0.3
  fi
}

kill_stale 8000
kill_stale 4174

BACKEND_PORT=8000
FRONTEND_PORT=4174

# ── Cleanup on exit ──────────────────────────────────────────

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  # Kill spinner first to avoid garbled output
  [ -n "$SPINNER_PID" ] && kill "$SPINNER_PID" 2>/dev/null
  SPINNER_PID=""
  echo ""
  echo -e "  ${DIM}Shutting down Blueprint...${NC}"
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
  lsof -ti :"$BACKEND_PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true
  lsof -ti :"$FRONTEND_PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true
  wait 2>/dev/null
  echo -e "  ${BGREEN}✔${NC} Blueprint stopped"
}

trap cleanup EXIT INT TERM

# ── Check Python dependencies ────────────────────────────────

# Map profile to requirements file
case "$PROFILE" in
  full|eval) REQ_FILE="backend/requirements-eval.txt" ;;
  training)  REQ_FILE="backend/requirements-training.txt" ;;
  inference) REQ_FILE="backend/requirements-inference.txt" ;;
  *)         REQ_FILE="backend/requirements-base.txt" ;;
esac

echo -e "  ${BGREEN}✔${NC} Profile ${GREEN}$PROFILE${NC} ${DIM}($REQ_FILE)${NC}"

if ! "$PYTHON" -c "import fastapi" 2>/dev/null; then
  start_spinner "Installing Python dependencies ($PROFILE)"
  if ! "$PIP" install -r "$REQ_FILE" --quiet 2>/dev/null; then
    stop_spinner "Python dependencies" "fail"
    echo -e "  ${DIM}Try: ${VENV_DIR}/bin/pip3 install -r $REQ_FILE${NC}"
    exit 1
  fi
  stop_spinner "Python dependencies installed" "ok"
fi

# ── Check Node dependencies ──────────────────────────────────

if [ ! -d "frontend/node_modules" ]; then
  start_spinner "Installing frontend dependencies"
  (cd frontend && npm install --silent)
  stop_spinner "Frontend dependencies installed" "ok"
fi

# ── Rebuild frontend if source is newer than dist ────────────

DIST_INDEX="$SCRIPT_DIR/frontend/dist/index.html"
SRC_DIR="$SCRIPT_DIR/frontend/src"

if [ ! -f "$DIST_INDEX" ] || [ -n "$(find "$SRC_DIR" -newer "$DIST_INDEX" -name '*.ts' -o -name '*.tsx' 2>/dev/null | head -1)" ]; then
  start_spinner "Building frontend"
  (cd "$SCRIPT_DIR/frontend" && npm run build --silent) > /dev/null 2>&1
  stop_spinner "Frontend built" "ok"
else
  echo -e "  ${BGREEN}✔${NC} Frontend dist ${DIM}up to date${NC}"
fi

echo ""

# ── Start Backend ────────────────────────────────────────────

start_spinner "Starting backend"
cd "$SCRIPT_DIR"
"$PYTHON" -m uvicorn backend.main:app \
  --host 127.0.0.1 \
  --port "$BACKEND_PORT" \
  --log-level warning \
  &
BACKEND_PID=$!

# Wait for backend to be ready
for i in $(seq 1 30); do
  if curl -s "http://127.0.0.1:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
    stop_spinner "Backend ready on ${GREEN}:$BACKEND_PORT${NC}" "ok"
    break
  fi
  sleep 0.5
done

if ! curl -s "http://127.0.0.1:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
  stop_spinner "Backend timeout on :$BACKEND_PORT" "warn"
fi

# ── Start Frontend ───────────────────────────────────────────

start_spinner "Starting frontend"
cd "$SCRIPT_DIR/frontend"
VITE_PORT="$FRONTEND_PORT" VITE_API_TARGET="http://127.0.0.1:$BACKEND_PORT" \
  npx vite --port "$FRONTEND_PORT" --host 127.0.0.1 2>&1 | while IFS= read -r line; do
    if echo "$line" | grep -q "Local:"; then
      :
    fi
  done &
FRONTEND_PID=$!

# Wait for frontend
sleep 2
for i in $(seq 1 20); do
  if curl -s "http://127.0.0.1:$FRONTEND_PORT" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if curl -s "http://127.0.0.1:$FRONTEND_PORT" >/dev/null 2>&1; then
  stop_spinner "Frontend ready on ${GREEN}:$FRONTEND_PORT${NC}" "ok"
else
  stop_spinner "Frontend timeout on :$FRONTEND_PORT" "warn"
fi

# ── Summary ─────────────────────────────────────────────────

URL="http://localhost:$FRONTEND_PORT"

echo ""
echo -e "  ${TEAL}${BOLD}◆ Blueprint is live${NC}"
echo -e "  ${DIM}─────────────────────────────────────${NC}"
echo -e "  ${DIM}Frontend${NC}  ${GREEN}http://localhost:$FRONTEND_PORT${NC}"
echo -e "  ${DIM}Backend${NC}   ${GREEN}http://localhost:$BACKEND_PORT${NC}"
echo -e "  ${DIM}Profile${NC}   ${GREEN}$PROFILE${NC}"
echo -e "  ${DIM}─────────────────────────────────────${NC}"
echo -e "  ${DIM}Press ${BOLD}Ctrl+C${NC}${DIM} to stop${NC}"
echo ""

# Open in default browser
if command -v open >/dev/null 2>&1; then
  open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL"
fi

# ── Keep running ─────────────────────────────────────────────

wait
