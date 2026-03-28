#!/usr/bin/env python3
"""Normalize block.yaml files and generate blocks/MANIFEST.json.

Ensures every block.yaml has critical fields with sensible defaults:
  - version    (default '0.1.0' if missing)
  - maturity   (default 'stable')
  - exportable (default True)
  - requires   (default [])
  - execution.isolation (default 'inprocess')

Also generates a deterministic MANIFEST.json listing all blocks.

Usage:
    python scripts/normalize_blocks.py          # normalize + generate manifest
    python scripts/normalize_blocks.py --check  # CI mode: exit 1 if stale
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BLOCKS_DIR = PROJECT_ROOT / "blocks"
MANIFEST_PATH = BLOCKS_DIR / "MANIFEST.json"

DEFAULTS = {
    "version": "0.1.0",
    "maturity": "stable",
    "exportable": True,
    "requires": [],
}

EXECUTION_DEFAULTS = {
    "isolation": "inprocess",
}


def normalize_yaml(yaml_path: Path) -> bool:
    """Add missing fields to a block.yaml. Returns True if the file was modified."""
    with open(yaml_path, "r") as f:
        raw_text = f.read()
    data = yaml.safe_load(raw_text) or {}
    modified = False

    for key, default in DEFAULTS.items():
        if key not in data:
            data[key] = default
            modified = True

    # Nested execution.isolation
    if "execution" not in data:
        data["execution"] = dict(EXECUTION_DEFAULTS)
        modified = True
    elif isinstance(data["execution"], dict):
        for key, default in EXECUTION_DEFAULTS.items():
            if key not in data["execution"]:
                data["execution"][key] = default
                modified = True

    if modified:
        with open(yaml_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return modified


def build_manifest() -> list[dict]:
    """Build a sorted manifest of all blocks."""
    entries: list[dict] = []
    for category_dir in sorted(BLOCKS_DIR.iterdir()):
        if not category_dir.is_dir() or category_dir.name.startswith((".", "_")):
            continue
        for block_dir in sorted(category_dir.iterdir()):
            if not block_dir.is_dir() or block_dir.name.startswith((".", "_")):
                continue
            yaml_path = block_dir / "block.yaml"
            if not yaml_path.exists():
                continue
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f) or {}
            entries.append({
                "block_type": data.get("type", block_dir.name),
                "category": data.get("category", category_dir.name),
                "name": data.get("name", block_dir.name),
                "version": data.get("version", "0.1.0"),
                "maturity": data.get("maturity", "stable"),
                "exportable": data.get("exportable", True),
                "has_run": (block_dir / "run.py").exists(),
                "inputs": len(data.get("inputs", [])),
                "outputs": len(data.get("outputs", [])),
            })
    entries.sort(key=lambda e: (e["category"], e["block_type"]))
    return entries


def main() -> int:
    check_only = "--check" in sys.argv

    if not check_only:
        modified_count = 0
        for category_dir in sorted(BLOCKS_DIR.iterdir()):
            if not category_dir.is_dir() or category_dir.name.startswith((".", "_")):
                continue
            for block_dir in sorted(category_dir.iterdir()):
                if not block_dir.is_dir() or block_dir.name.startswith((".", "_")):
                    continue
                yaml_path = block_dir / "block.yaml"
                if yaml_path.exists() and normalize_yaml(yaml_path):
                    modified_count += 1
                    print(f"  normalized: {yaml_path.relative_to(PROJECT_ROOT)}")
        if modified_count:
            print(f"\nNormalized {modified_count} block.yaml file(s).")
        else:
            print("All block.yaml files already normalized.")

    # Generate manifest
    manifest = build_manifest()
    new_manifest_text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"

    if check_only:
        if not MANIFEST_PATH.exists():
            print("ERROR: MANIFEST.json does not exist. Run: python scripts/normalize_blocks.py")
            return 1
        existing = MANIFEST_PATH.read_text()
        if existing != new_manifest_text:
            print("ERROR: MANIFEST.json is stale. Run: python scripts/normalize_blocks.py")
            return 1
        print("MANIFEST.json is up to date.")
        return 0

    MANIFEST_PATH.write_text(new_manifest_text)
    print(f"Generated {MANIFEST_PATH.relative_to(PROJECT_ROOT)} with {len(manifest)} blocks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
