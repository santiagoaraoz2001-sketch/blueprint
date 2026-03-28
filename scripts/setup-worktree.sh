#!/usr/bin/env bash
# setup-worktree.sh — Prepare a git worktree for development.
#
# Git worktrees share the repository but have their own working trees.
# Non-tracked directories (node_modules, __pycache__, etc.) are absent.
# This script creates the necessary symlinks and verifies the environment.
#
# Usage:
#   From any worktree root:    ./scripts/setup-worktree.sh
#   From project root:         ./scripts/setup-worktree.sh /path/to/worktree
#
# Idempotent — safe to run multiple times.

set -euo pipefail

# ── Resolve paths ─────────────────────────────────────────────

WORKTREE_ROOT="${1:-$(pwd)}"

# Find the main repository root by walking up from the worktree
# looking for a non-symlinked frontend/node_modules or .git directory
find_main_repo() {
    # git worktrees have a .git FILE (not directory) that points to the main repo
    local git_entry="${WORKTREE_ROOT}/.git"
    if [ -f "$git_entry" ]; then
        # Extract the gitdir path from the .git file
        local gitdir
        gitdir=$(sed 's/^gitdir: //' "$git_entry")
        # Resolve to absolute path
        gitdir=$(cd "${WORKTREE_ROOT}" && cd "$(dirname "$gitdir")" && pwd)/$(basename "$gitdir")
        # Walk up from gitdir to find the main repo root
        # Typical structure: /repo/.git/worktrees/<name>
        local main_git="${gitdir}/../.."
        main_git=$(cd "$main_git" && pwd)
        # The main repo root is the parent of .git
        echo "$(dirname "$main_git")"
    elif [ -d "$git_entry" ]; then
        # This IS the main repo
        echo "$WORKTREE_ROOT"
    else
        echo ""
    fi
}

MAIN_REPO=$(find_main_repo)

if [ -z "$MAIN_REPO" ]; then
    echo "ERROR: Could not find main repository root from ${WORKTREE_ROOT}"
    exit 1
fi

if [ "$MAIN_REPO" = "$WORKTREE_ROOT" ]; then
    echo "This is the main repository, not a worktree. Nothing to do."
    exit 0
fi

echo "Worktree root:  ${WORKTREE_ROOT}"
echo "Main repo root: ${MAIN_REPO}"

# ── Frontend node_modules ─────────────────────────────────────

MAIN_NODE_MODULES="${MAIN_REPO}/frontend/node_modules"
WT_NODE_MODULES="${WORKTREE_ROOT}/frontend/node_modules"

if [ -L "$WT_NODE_MODULES" ]; then
    echo "✓ frontend/node_modules symlink already exists"
elif [ -d "$WT_NODE_MODULES" ]; then
    echo "✓ frontend/node_modules directory already exists (real, not symlink)"
elif [ -d "$MAIN_NODE_MODULES" ]; then
    ln -s "$MAIN_NODE_MODULES" "$WT_NODE_MODULES"
    echo "✓ Created symlink: frontend/node_modules → main repo"
else
    echo "⚠ Main repo frontend/node_modules not found. Run 'npm install' in ${MAIN_REPO}/frontend/ first."
fi

# ── Python virtual environment (optional) ─────────────────────

for venv_name in .venv venv; do
    MAIN_VENV="${MAIN_REPO}/${venv_name}"
    WT_VENV="${WORKTREE_ROOT}/${venv_name}"
    if [ -d "$MAIN_VENV" ] && [ ! -e "$WT_VENV" ]; then
        ln -s "$MAIN_VENV" "$WT_VENV"
        echo "✓ Created symlink: ${venv_name} → main repo"
    fi
done

# ── Frontend dist (for SPA serving) ──────────────────────────

MAIN_DIST="${MAIN_REPO}/frontend/dist"
WT_DIST="${WORKTREE_ROOT}/frontend/dist"

if [ -d "$MAIN_DIST" ] && [ ! -e "$WT_DIST" ]; then
    ln -s "$MAIN_DIST" "$WT_DIST"
    echo "✓ Created symlink: frontend/dist → main repo"
elif [ -e "$WT_DIST" ]; then
    echo "✓ frontend/dist already exists"
fi

# ── Verification ──────────────────────────────────────────────

ERRORS=0

if [ ! -e "$WT_NODE_MODULES" ]; then
    echo "✗ frontend/node_modules missing"
    ERRORS=$((ERRORS + 1))
fi

if [ $ERRORS -eq 0 ]; then
    echo ""
    echo "Worktree setup complete. All symlinks verified."
else
    echo ""
    echo "Worktree setup completed with ${ERRORS} warning(s)."
fi
