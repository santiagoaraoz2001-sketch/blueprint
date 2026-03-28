#!/usr/bin/env python3
"""Generate frontend/src/lib/port-compatibility.generated.ts from docs/PORT_COMPATIBILITY.yaml.

This script reads the single source of truth for port type compatibility and
generates TypeScript constants that the frontend uses for connection validation,
port coloring, and backward-compat alias resolution.

Usage:
    python3 scripts/generate_port_compat.py
    python3 scripts/generate_port_compat.py --check   # CI: exit 1 if stale
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
YAML_PATH = PROJECT_ROOT / "docs" / "PORT_COMPATIBILITY.yaml"
OUTPUT_PATH = PROJECT_ROOT / "frontend" / "src" / "lib" / "port-compatibility.generated.ts"

HEADER = """\
// ──────────────────────────────────────────────────────────────────
// AUTO-GENERATED from docs/PORT_COMPATIBILITY.yaml — DO NOT EDIT
// Regenerate: python3 scripts/generate_port_compat.py
// ──────────────────────────────────────────────────────────────────
"""


def generate() -> str:
    with open(YAML_PATH, "r") as f:
        data = yaml.safe_load(f) or {}

    aliases: dict[str, str] = data.get("aliases", {})
    matrix: dict[str, list[str]] = data.get("compatibility_matrix", {})

    lines: list[str] = [HEADER]

    # 1. PORT_TYPE_ALIASES
    lines.append("/** Backward-compat aliases — map old type names to current 10-type system. */")
    lines.append("export const PORT_TYPE_ALIASES: Record<string, string> = {")
    for old_name, new_name in sorted(aliases.items()):
        lines.append(f"  {old_name!s:16s}: '{new_name}',")
    lines.append("}")
    lines.append("")

    # 2. COMPAT matrix
    lines.append("/** Port compatibility matrix — source type → set of allowed target types. */")
    lines.append("export const COMPAT: Record<string, Set<string>> = {")
    for source in matrix:
        targets = matrix[source]
        target_list = ", ".join(f"'{t}'" for t in targets)
        lines.append(f"  {source!s:12s}: new Set([{target_list}]),")
    lines.append("}")
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    check_only = "--check" in sys.argv
    new_content = generate()

    if check_only:
        if not OUTPUT_PATH.exists():
            print(f"ERROR: {OUTPUT_PATH.name} does not exist. Run: python3 scripts/generate_port_compat.py")
            return 1
        existing = OUTPUT_PATH.read_text()
        if existing != new_content:
            print(f"ERROR: {OUTPUT_PATH.name} is stale. Run: python3 scripts/generate_port_compat.py")
            return 1
        print(f"{OUTPUT_PATH.name} is up to date.")
        return 0

    OUTPUT_PATH.write_text(new_content)
    print(f"Generated {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
