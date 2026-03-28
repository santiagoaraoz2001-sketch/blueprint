#!/usr/bin/env python3
"""
diff_frontend_backend_contracts.py — Compares backend contract snapshots
with frontend validation summaries to highlight cross-stack drift.

Usage:
    python scripts/diff_frontend_backend_contracts.py

Reads:
  - backend/tests/fixtures/contracts/__snapshots__/*.snapshot.json
  - frontend/src/lib/__tests__/__snapshots__/*.frontend.snapshot.json

If frontend snapshots don't exist yet, falls back to static analysis
of the COMPAT matrices in source code.
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
BE_SNAPSHOT_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "contracts" / "__snapshots__"
FE_SNAPSHOT_DIR = REPO_ROOT / "frontend" / "src" / "lib" / "__tests__" / "__snapshots__"

# ─── Source Code Analysis (fallback) ──────────────────────────────

def extract_frontend_compat() -> dict[str, set[str]]:
    """Parse COMPAT from block-registry-types.ts."""
    path = REPO_ROOT / "frontend" / "src" / "lib" / "block-registry-types.ts"
    content = path.read_text()
    compat: dict[str, set[str]] = {}
    match = re.search(r"const COMPAT:.*?=\s*\{(.*?)\}", content, re.DOTALL)
    if match:
        for line in match.group(1).split("\n"):
            m = re.match(r"\s*(\w+):\s*new Set\(\[([^\]]*)\]\)", line)
            if m:
                src = m.group(1)
                targets = {t.strip().strip("'\"") for t in m.group(2).split(",") if t.strip()}
                compat[src] = targets
    return compat


def extract_backend_compat() -> dict[str, set[str]]:
    """Parse COMPAT from validator.py.

    Supports both the old tuple-set format and the new dict-of-sets format.
    """
    path = REPO_ROOT / "backend" / "engine" / "validator.py"
    content = path.read_text()
    compat: dict[str, set[str]] = {}
    match = re.search(r"COMPAT[^=]*=\s*\{(.*?)\n\}", content, re.DOTALL)
    if match:
        block = match.group(1)
        # Try new dict-of-sets format: "key": {"val1", "val2"}
        for m in re.finditer(r'"(\w+)":\s*\{([^}]*)\}', block):
            src = m.group(1)
            targets = {
                t.strip().strip('"').strip("'")
                for t in m.group(2).split(",")
                if t.strip().strip('"').strip("'")
            }
            compat[src] = targets
        # Fallback: old tuple-set format
        if not compat:
            for m in re.finditer(r'\("(\w+)",\s*"(\w+)"\)', block):
                src, tgt = m.group(1), m.group(2)
                compat.setdefault(src, set()).add(tgt)
    return compat


def extract_frontend_aliases() -> dict[str, str]:
    path = REPO_ROOT / "frontend" / "src" / "lib" / "block-registry-types.ts"
    content = path.read_text()
    aliases: dict[str, str] = {}
    match = re.search(r"const PORT_TYPE_ALIASES:.*?=\s*\{(.*?)\}", content, re.DOTALL)
    if match:
        for m in re.finditer(r"(\w+):\s*'(\w+)'", match.group(1)):
            aliases[m.group(1)] = m.group(2)
    return aliases


def extract_backend_aliases() -> dict[str, str]:
    path = REPO_ROOT / "backend" / "engine" / "validator.py"
    content = path.read_text()
    aliases: dict[str, str] = {}
    match = re.search(r"_PORT_TYPE_ALIASES.*?=\s*\{(.*?)\}", content, re.DOTALL)
    if match:
        for m in re.finditer(r'"(\w+)":\s*"(\w+)"', match.group(1)):
            aliases[m.group(1)] = m.group(2)
    return aliases


# ─── Snapshot-Based Comparison ────────────────────────────────────

def load_be_snapshots() -> dict:
    snapshots = {}
    if BE_SNAPSHOT_DIR.exists():
        for p in sorted(BE_SNAPSHOT_DIR.glob("*.snapshot.json")):
            name = p.stem.replace(".snapshot", "")
            snapshots[name] = json.loads(p.read_text())
    return snapshots


def load_fe_snapshots() -> dict:
    snapshots = {}
    if FE_SNAPSHOT_DIR.exists():
        for p in sorted(FE_SNAPSHOT_DIR.glob("*.frontend.snapshot.json")):
            name = p.stem.replace(".frontend.snapshot", "")
            snapshots[name] = json.loads(p.read_text())
    return snapshots


# ─── Main ─────────────────────────────────────────────────────────

def main():
    drift_count = 0

    print("=" * 80)
    print("CROSS-STACK CONTRACT DRIFT REPORT")
    print("=" * 80)
    print()

    # 1. COMPAT matrix comparison
    fe_compat = extract_frontend_compat()
    be_compat = extract_backend_compat()

    print("--- PORT COMPATIBILITY MATRIX DRIFT ---")
    print()

    all_types = sorted(set(list(fe_compat.keys()) + list(be_compat.keys()) + ["llm"]))

    # Build comparison
    print(f"{'Source→Target':<25s} {'Frontend':<12s} {'Backend':<12s} {'Status':<10s}")
    print("-" * 59)

    for src in all_types:
        fe_targets = fe_compat.get(src, set())
        be_targets = be_compat.get(src, set())

        for tgt in all_types:
            fe_ok = tgt in fe_targets
            be_ok = tgt in be_targets

            if fe_ok == be_ok:
                continue  # Agreement — skip

            drift_count += 1
            fe_str = "ALLOW" if fe_ok else "BLOCK"
            be_str = "ALLOW" if be_ok else "BLOCK"
            print(f"  {src}→{tgt:<15s} {fe_str:<12s} {be_str:<12s} **DRIFT**")

    print()

    # 2. Alias comparison
    fe_aliases = extract_frontend_aliases()
    be_aliases = extract_backend_aliases()

    print("--- PORT TYPE ALIAS DRIFT ---")
    print()

    all_alias_keys = sorted(set(list(fe_aliases.keys()) + list(be_aliases.keys())))
    alias_drift = False
    for key in all_alias_keys:
        fe_val = fe_aliases.get(key, "(missing)")
        be_val = be_aliases.get(key, "(missing)")
        if fe_val != be_val:
            alias_drift = True
            drift_count += 1
            print(f"  {key}: frontend={fe_val}, backend={be_val}")

    if not alias_drift:
        print("  No alias drift.")
    print()

    # 3. Snapshot comparison (if both exist)
    be_snaps = load_be_snapshots()
    fe_snaps = load_fe_snapshots()

    print("--- FIXTURE SNAPSHOT COMPARISON ---")
    print()

    if not fe_snaps:
        print("  Frontend snapshots not yet generated. Run:")
        print("    cd frontend && npx vitest run src/lib/__tests__/pipeline-contract.test.ts")
        print()
    else:
        for name in sorted(set(list(be_snaps.keys()) + list(fe_snaps.keys()))):
            be = be_snaps.get(name)
            fe = fe_snaps.get(name)

            if not be:
                print(f"  {name}: BACKEND SNAPSHOT MISSING")
                continue
            if not fe:
                print(f"  {name}: FRONTEND SNAPSHOT MISSING")
                continue

            # Compare cycle/loop detection
            be_has_illegal = bool(be.get("validation", {}).get("errors") and
                                any("cycle" in e.lower() for e in be.get("validation", {}).get("errors", [])))
            # Frontend snapshots may use either old "cycle_detection" or new "loop_detection" key
            fe_loop = fe.get("loop_detection", {})
            fe_has_illegal = fe_loop.get("illegal_cycle", False)
            # Fallback to old cycle_detection key
            if not fe_loop:
                fe_has_illegal = fe.get("cycle_detection", {}).get("has_cycle", False)

            if be_has_illegal != fe_has_illegal:
                print(f"  {name}: CYCLE/LOOP DETECTION DRIFT — backend_illegal={be_has_illegal}, frontend_illegal={fe_has_illegal}")
                drift_count += 1

            # Compare edge compatibility
            be_val = be.get("validation", {})
            fe_edges = fe.get("edge_compatibility", {})

            be_incompat_edges = set()
            for err in be_val.get("errors", []):
                if "incompatible" in err.lower():
                    be_incompat_edges.add(err)

            fe_incompat_edges = {
                eid for eid, info in fe_edges.items()
                if not info.get("compatible", True)
            }

            if be_incompat_edges or fe_incompat_edges:
                print(f"  {name}: backend incompat errors={len(be_incompat_edges)}, frontend incompat edges={len(fe_incompat_edges)}")

    # 4. Summary
    print("=" * 80)
    print(f"TOTAL DRIFT ITEMS: {drift_count}")
    print("=" * 80)

    if drift_count > 0:
        print()
        print("ACTION REQUIRED: Backend validator.py COMPAT must be updated to match")
        print("frontend block-registry-types.ts. See docs/EXECUTION_CONTRACT_V1.md")
        print("for the authoritative compatibility matrix.")

    return 1 if drift_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
