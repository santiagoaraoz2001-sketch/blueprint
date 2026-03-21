#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  Blueprint — Launch Script
#  Starts the FastAPI backend + Vite frontend, opens browser
# ──────────────────────────────────────────────────────────────

set -e

# Allow SCRIPT_DIR to be set externally (e.g. by Blueprint.app launcher)
SCRIPT_DIR="${SCRIPT_DIR:-$(cd "$(dirname "$0")" && pwd)}"
cd "$SCRIPT_DIR"

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
DIM='\033[0;90m'
BOLD='\033[1m'
NC='\033[0m'
RED='\033[0;31m'
YELLOW='\033[0;33m'

# ── Check Python version (require 3.10+) ────────────────────

if ! command -v python3 >/dev/null 2>&1; then
  echo -e "${RED}Error: python3 is not installed or not in PATH.${NC}"
  exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
  echo -e "${RED}Error: Python 3.10+ is required (found $PYTHON_VERSION).${NC}"
  exit 1
fi

echo -e "${DIM}Python version: ${NC}${GREEN}$PYTHON_VERSION${NC}"

# ── Check Node.js version (require 18+) ─────────────────────

if ! command -v node >/dev/null 2>&1; then
  echo -e "${RED}Error: Node.js is not installed or not in PATH.${NC}"
  exit 1
fi

NODE_VERSION=$(node -v | sed 's/^v//' | cut -d. -f1)

if [ "$NODE_VERSION" -lt 18 ]; then
  echo -e "${RED}Error: Node.js 18+ is required (found v$(node -v | sed 's/^v//'))."
  echo -e "Please upgrade Node.js: https://nodejs.org/${NC}"
  exit 1
fi

echo -e "${DIM}Node.js version:${NC} ${GREEN}$(node -v)${NC}"

echo ""
echo -e "${CYAN}${BOLD}  ┌─────────────────────────────────────┐${NC}"
echo -e "${CYAN}${BOLD}  │   SPECIFIC LABS — BLUEPRINT         │${NC}"
echo -e "${CYAN}${BOLD}  │   ML Experiment Workbench            │${NC}"
echo -e "${CYAN}${BOLD}  └─────────────────────────────────────┘${NC}"
echo ""

# ── Setup Python virtual environment ─────────────────────────

VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
  echo -e "${CYAN}Creating Python virtual environment...${NC}"
  python3 -m venv "$VENV_DIR"
fi

# Activate venv — use this Python for all subsequent commands
PYTHON="$VENV_DIR/bin/python3"
PIP="$VENV_DIR/bin/pip3"

echo -e "${DIM}Virtual env:    ${NC}${GREEN}.venv${NC}"

# ── Kill stale Blueprint processes ────────────────────────────
# Ensures you never accidentally use an old backend/frontend from
# a previous session that wasn't cleaned up properly.

kill_stale() {
  local port=$1
  local pids
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo -e "${YELLOW}Killing stale process on port $port (PID: $pids)${NC}"
    echo "$pids" | xargs kill -9 2>/dev/null || true
    sleep 0.3
  fi
}

kill_stale 8000
kill_stale 4174

BACKEND_PORT=8000
FRONTEND_PORT=4174

echo -e "${DIM}Backend port:  ${NC}${GREEN}$BACKEND_PORT${NC}"
echo -e "${DIM}Frontend port: ${NC}${GREEN}$FRONTEND_PORT${NC}"
echo ""

# ── Cleanup on exit ──────────────────────────────────────────
# Uses process group kill (-$$) to ensure ALL child processes die,
# even if they spawned grandchildren (e.g. vite spawns node).

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  echo -e "${DIM}Shutting down...${NC}"
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
  # Also kill anything still on our ports (catches orphaned grandchildren)
  lsof -ti :"$BACKEND_PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true
  lsof -ti :"$FRONTEND_PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true
  wait 2>/dev/null
  echo -e "${GREEN}Blueprint stopped.${NC}"
}

trap cleanup EXIT INT TERM

# ── Check Python dependencies ────────────────────────────────

if ! "$PYTHON" -c "import fastapi" 2>/dev/null; then
  echo -e "${CYAN}Installing Python dependencies...${NC}"
  if ! "$PIP" install -r backend/requirements.txt --quiet; then
    echo -e "${RED}Error: Failed to install Python dependencies.${NC}"
    echo -e "${RED}Try running manually: ${VENV_DIR}/bin/pip3 install -r backend/requirements.txt${NC}"
    exit 1
  fi
  echo -e "${GREEN}Dependencies installed.${NC}"
fi

# ── Check Node dependencies ──────────────────────────────────

if [ ! -d "frontend/node_modules" ]; then
  echo -e "${CYAN}Installing frontend dependencies...${NC}"
  (cd frontend && npm install --silent)
fi

# ── Rebuild frontend if source is newer than dist ────────────
# Prevents serving stale JS bundles from a previous build.

DIST_INDEX="$SCRIPT_DIR/frontend/dist/index.html"
SRC_DIR="$SCRIPT_DIR/frontend/src"

if [ ! -f "$DIST_INDEX" ] || [ -n "$(find "$SRC_DIR" -newer "$DIST_INDEX" -name '*.ts' -o -name '*.tsx' 2>/dev/null | head -1)" ]; then
  echo -e "${CYAN}Frontend source changed — rebuilding dist...${NC}"
  (cd "$SCRIPT_DIR/frontend" && npm run build --silent)
  echo -e "${GREEN}Frontend rebuilt.${NC}"
else
  echo -e "${DIM}Frontend dist is up to date.${NC}"
fi

# ── Start Backend ────────────────────────────────────────────

echo -e "${CYAN}Starting backend on port $BACKEND_PORT...${NC}"
cd "$SCRIPT_DIR"
"$PYTHON" -m uvicorn backend.main:app \
  --host 127.0.0.1 \
  --port "$BACKEND_PORT" \
  --log-level warning \
  &
BACKEND_PID=$!

# Wait for backend to be ready
echo -ne "${DIM}Waiting for backend"
for i in $(seq 1 30); do
  if curl -s "http://127.0.0.1:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
    echo -e " ${GREEN}ready${NC}"
    break
  fi
  echo -n "."
  sleep 0.5
done

if ! curl -s "http://127.0.0.1:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
  echo -e " ${NC}timeout (continuing anyway)"
fi

# ── Start Frontend ───────────────────────────────────────────

echo -e "${CYAN}Starting frontend on port $FRONTEND_PORT...${NC}"
cd "$SCRIPT_DIR/frontend"
VITE_PORT="$FRONTEND_PORT" VITE_API_TARGET="http://127.0.0.1:$BACKEND_PORT" \
  npx vite --port "$FRONTEND_PORT" --host 127.0.0.1 2>&1 | while IFS= read -r line; do
    # Only show the "ready" line
    if echo "$line" | grep -q "Local:"; then
      echo -e "${GREEN}$line${NC}"
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

# ── Open Browser ─────────────────────────────────────────────

URL="http://localhost:$FRONTEND_PORT"
echo ""
echo -e "${GREEN}${BOLD}Blueprint is running at: $URL${NC}"
echo -e "${DIM}Press Ctrl+C to stop${NC}"
echo ""

# Open in default browser
if command -v open >/dev/null 2>&1; then
  open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL"
fi

# ── Keep running ─────────────────────────────────────────────

wait
