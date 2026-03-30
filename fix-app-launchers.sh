#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  Fix Blueprint.app and Model Manager.app launchers
#  Usage:  bash fix-app-launchers.sh
# ──────────────────────────────────────────────────────────────

set -e

GREEN='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Fix 1: Blueprint.app ─────────────────────────────────────
BLUEPRINT_LAUNCHER="/Applications/Blueprint.app/Contents/MacOS/blueprint-launcher"

if [ -f "$BLUEPRINT_LAUNCHER" ]; then
    # Check if the launcher contains the unsafe pattern that causes TCC issues
    if grep -q "bash \"\$LAUNCH_SCRIPT\"" "$BLUEPRINT_LAUNCHER"; then
        echo -e "${CYAN}Fixing Blueprint.app launcher (unsafe pattern found)...${NC}"
        bash "$SCRIPT_DIR/make-dev-app.sh"
    else
        echo -e "${CYAN}Blueprint.app launcher is already safe (no unsafe pattern).${NC}"
    fi
else
    echo -e "${CYAN}Blueprint.app not found, installing...${NC}"
    bash "$SCRIPT_DIR/make-dev-app.sh"
fi

echo ""

# ── Fix 2: Model Manager.app ─────────────────────────────────
MM_LAUNCHER="/Applications/Model Manager.app/Contents/MacOS/ModelManager"

if [ -f "$MM_LAUNCHER" ]; then
    echo -e "${CYAN}Fixing Model Manager.app launcher...${NC}"

    cat > "$MM_LAUNCHER" << 'LAUNCHER'
#!/bin/bash
# Model Manager — Launch Streamlit Dashboard
# Explicit paths for macOS .app bundle environment

# macOS GUI apps do NOT inherit your terminal PATH.
# Set PATH BEFORE detecting streamlit so `which` can find it.
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/Library/Python/3.12/bin:$HOME/.npm-global/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# Source shell profiles for any custom PATH additions
[ -f "$HOME/.zprofile" ]     && source "$HOME/.zprofile"     2>/dev/null || true
[ -f "$HOME/.zshrc" ]        && source "$HOME/.zshrc"        2>/dev/null || true
[ -f "$HOME/.bash_profile" ] && source "$HOME/.bash_profile" 2>/dev/null || true

export OLLAMA_MODELS="/Volumes/Cold Storage 1/models/ollama"

STREAMLIT="/Library/Frameworks/Python.framework/Versions/3.12/bin/streamlit"
if [ ! -f "$STREAMLIT" ]; then
    STREAMLIT="$HOME/Library/Python/3.12/bin/streamlit"
fi
if [ ! -f "$STREAMLIT" ]; then
    STREAMLIT=$(which streamlit 2>/dev/null)
fi

if [ -z "$STREAMLIT" ] || [ ! -f "$STREAMLIT" ]; then
    osascript -e 'display alert "Model Manager Error" message "Cannot find streamlit. Install it with: pip3 install streamlit" as critical' 2>/dev/null
    exit 1
fi

APP_DIR="/Applications/model-manager"
LOG_FILE="$APP_DIR/model-manager.log"
PORT=8501

# Check if already running
if curl -sf "http://localhost:$PORT" >/dev/null 2>&1; then
    open "http://localhost:$PORT"
    exit 0
fi

# Start Streamlit
cd "$APP_DIR"
"$STREAMLIT" run frontend/app.py \
    --server.port "$PORT" \
    --server.headless true \
    --browser.gatherUsageStats false \
    >> "$LOG_FILE" 2>&1 &

# Wait for server
for i in {1..20}; do
    if curl -sf "http://localhost:$PORT" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

open "http://localhost:$PORT"
LAUNCHER

    chmod +x "$MM_LAUNCHER"
    xattr -cr "/Applications/Model Manager.app" 2>/dev/null || true
    echo -e "${GREEN}Model Manager.app fixed!${NC}"
else
    echo -e "${RED}Model Manager.app not found in /Applications${NC}"
fi

echo ""
echo -e "${GREEN}Done! Apps should now launch correctly.${NC}"
echo -e "  Try opening them from Launchpad or Spotlight."
