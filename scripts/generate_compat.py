#!/usr/bin/env python3
"""
Generate frontend/src/lib/generated/port-compat.generated.ts from docs/PORT_COMPATIBILITY.yaml.

Single source of truth for port-type compatibility and backward-compat aliases.
The generated module exposes the same API as the old hand-maintained COMPAT dict
in block-registry-types.ts so call-sites are a drop-in replacement.

Usage:
    python scripts/generate_compat.py

Reads:  docs/PORT_COMPATIBILITY.yaml
Writes: frontend/src/lib/generated/port-compat.generated.ts
"""

import sys
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
YAML_FILE = PROJECT_ROOT / "docs" / "PORT_COMPATIBILITY.yaml"
OUTPUT_DIR = PROJECT_ROOT / "frontend" / "src" / "lib" / "generated"
OUTPUT_FILE = OUTPUT_DIR / "port-compat.generated.ts"


def main():
    if not YAML_FILE.exists():
        print(f"ERROR: {YAML_FILE} not found", file=sys.stderr)
        sys.exit(1)

    with open(YAML_FILE) as f:
        data = yaml.safe_load(f)

    aliases: dict[str, str] = data.get("aliases", {})
    compat: dict[str, list[str]] = data.get("compatibility_matrix", {})

    lines = [
        "// AUTO-GENERATED from docs/PORT_COMPATIBILITY.yaml — DO NOT EDIT",
        "// Run: python scripts/generate_compat.py",
        "",
        "/** Backward-compat aliases — map old type names to new 10-type system */",
        "export const PORT_TYPE_ALIASES: Record<string, string> = {",
    ]
    for old_name, new_name in sorted(aliases.items()):
        lines.append(f"  '{old_name}': '{new_name}',")
    lines.append("}")
    lines.append("")

    lines.append("/** Port compatibility matrix: source type → set of allowed target types */")
    lines.append("const COMPAT: Record<string, Set<string>> = {")
    for src_type, targets in compat.items():
        targets_str = ", ".join(f"'{t}'" for t in targets)
        lines.append(f"  '{src_type}': new Set([{targets_str}]),")
    lines.append("}")
    lines.append("")

    lines.append("/** Check if a source port type is compatible with a target port type. */")
    lines.append("export function isPortCompatible(source: string, target: string): boolean {")
    lines.append("  const s = PORT_TYPE_ALIASES[source] || source")
    lines.append("  const t = PORT_TYPE_ALIASES[target] || target")
    lines.append("  return COMPAT[s]?.has(t) ?? false")
    lines.append("}")
    lines.append("")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text("\n".join(lines) + "\n")

    print(f"Generated {OUTPUT_FILE}")
    print(f"  {len(aliases)} aliases, {len(compat)} port types")


if __name__ == "__main__":
    main()
