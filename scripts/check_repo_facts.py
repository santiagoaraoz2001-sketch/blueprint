#!/usr/bin/env python3
"""
CI check: regenerate REPO_FACTS.json and fail if the committed version is stale.

Usage:
    python scripts/check_repo_facts.py

Exit codes:
    0 — committed REPO_FACTS.json matches the filesystem
    1 — stale or missing REPO_FACTS.json (re-run scripts/generate_repo_facts.py)
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FACTS_PATH = REPO_ROOT / "docs" / "REPO_FACTS.json"

# Reuse the generator to get fresh facts
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from generate_repo_facts import generate_facts


def normalize(facts: dict) -> dict:
    """Strip volatile fields (_generated timestamp) for comparison."""
    copy = dict(facts)
    copy.pop("_generated", None)
    return copy


def main() -> int:
    if not FACTS_PATH.exists():
        print(f"FAIL: {FACTS_PATH.relative_to(REPO_ROOT)} does not exist.")
        print("  Run: python scripts/generate_repo_facts.py")
        return 1

    committed = json.loads(FACTS_PATH.read_text())
    fresh = generate_facts()

    if normalize(committed) != normalize(fresh):
        print(f"FAIL: {FACTS_PATH.relative_to(REPO_ROOT)} is stale.")
        # Show what differs
        committed_norm = normalize(committed)
        fresh_norm = normalize(fresh)
        for key in sorted(set(committed_norm) | set(fresh_norm)):
            if committed_norm.get(key) != fresh_norm.get(key):
                print(f"  {key}:")
                print(f"    committed: {json.dumps(committed_norm.get(key))}")
                print(f"    actual:    {json.dumps(fresh_norm.get(key))}")
        print()
        print("  Run: python scripts/generate_repo_facts.py")
        return 1

    print(f"OK: {FACTS_PATH.relative_to(REPO_ROOT)} is up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
