#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  Build Blueprint.app — Full distributable macOS application
#  Produces a standalone .app and .dmg installer via Electron.
#
#  Usage:  bash build-app.sh
#  Output: frontend/out/make/ (contains .app and .dmg)
# ──────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
DIM='\033[0;90m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${CYAN}${BOLD}  ┌─────────────────────────────────────┐${NC}"
echo -e "${CYAN}${BOLD}  │   BLUEPRINT — App Builder            │${NC}"
echo -e "${CYAN}${BOLD}  └─────────────────────────────────────┘${NC}"
echo ""

# ── Step 1: Build the PyInstaller backend binary ─────────────

echo -e "${CYAN}[1/4] Building backend binary...${NC}"

VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo -e "${DIM}Creating Python virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
fi

PYTHON="$VENV_DIR/bin/python3"
PIP="$VENV_DIR/bin/pip3"

# Install backend dependencies if needed
if ! "$PYTHON" -c "import fastapi" 2>/dev/null; then
    echo -e "${DIM}Installing Python dependencies...${NC}"
    "$PIP" install -r backend/requirements.txt --quiet
fi

# Install PyInstaller if needed
if ! "$PYTHON" -c "import PyInstaller" 2>/dev/null; then
    echo -e "${DIM}Installing PyInstaller...${NC}"
    "$PIP" install pyinstaller --quiet
fi

echo -e "${DIM}Running PyInstaller...${NC}"
cd "$SCRIPT_DIR/backend"
"$PYTHON" -m PyInstaller blueprint_backend.spec \
    --distpath "$SCRIPT_DIR/dist" \
    --workpath "$SCRIPT_DIR/build" \
    --noconfirm \
    2>&1 | tail -5
cd "$SCRIPT_DIR"

if [ ! -f "$SCRIPT_DIR/dist/blueprint_backend" ]; then
    echo -e "${RED}Error: PyInstaller failed — dist/blueprint_backend not found.${NC}"
    exit 1
fi

echo -e "${GREEN}Backend binary built: dist/blueprint_backend${NC}"

# ── Step 2: Install frontend dependencies ─────────────────────

echo ""
echo -e "${CYAN}[2/4] Installing frontend dependencies...${NC}"

cd "$SCRIPT_DIR/frontend"

if [ ! -d "node_modules" ]; then
    npm install --silent
else
    echo -e "${DIM}node_modules already present${NC}"
fi

# ── Step 3: Build frontend (Vite) ────────────────────────────

echo ""
echo -e "${CYAN}[3/4] Building frontend...${NC}"

npm run build --silent
cd "$SCRIPT_DIR"

if [ ! -f "$SCRIPT_DIR/frontend/dist/index.html" ]; then
    echo -e "${RED}Error: Vite build failed — frontend/dist/index.html not found.${NC}"
    exit 1
fi

echo -e "${GREEN}Frontend built: frontend/dist/${NC}"

# ── Step 4: Package with Electron Forge ──────────────────────

echo ""
echo -e "${CYAN}[4/4] Packaging with Electron Forge...${NC}"

cd "$SCRIPT_DIR/frontend"
npx electron-forge make 2>&1 | tail -10
cd "$SCRIPT_DIR"

# ── Report results ────────────────────────────────────────────

echo ""
echo -e "${GREEN}${BOLD}Build complete!${NC}"
echo ""

# Find the output
APP_PATH=$(find frontend/out -name "Blueprint.app" -maxdepth 3 2>/dev/null | head -1)
DMG_PATH=$(find frontend/out/make -name "*.dmg" 2>/dev/null | head -1)

if [ -n "$APP_PATH" ]; then
    echo -e "  ${GREEN}App:${NC} $APP_PATH"
fi
if [ -n "$DMG_PATH" ]; then
    echo -e "  ${GREEN}DMG:${NC} $DMG_PATH"
fi

echo ""
echo -e "  ${CYAN}To install:${NC}"
if [ -n "$DMG_PATH" ]; then
    echo -e "    • Open ${GREEN}$DMG_PATH${NC} and drag Blueprint to Applications"
elif [ -n "$APP_PATH" ]; then
    echo -e "    • Copy to Applications: ${DIM}cp -r \"$APP_PATH\" /Applications/${NC}"
fi
echo ""
