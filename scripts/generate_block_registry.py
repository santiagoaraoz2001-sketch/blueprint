#!/usr/bin/env python3
"""
Generate frontend/src/lib/block-registry.generated.ts from block.yaml files.

Usage:
    python scripts/generate_block_registry.py

Reads: blocks/**/block.yaml
Writes: frontend/src/lib/block-registry.generated.ts
"""

import json
import sys
import yaml
from pathlib import Path
from typing import Any

BLOCKS_DIR = Path(__file__).parent.parent / "blocks"
OUTPUT_FILE = Path(__file__).parent.parent / "frontend" / "src" / "lib" / "block-registry.generated.ts"

# Map block.yaml config types to TypeScript ConfigField types
YAML_TYPE_TO_TS = {
    "string": "string",
    "integer": "integer",
    "float": "float",
    "boolean": "boolean",
    "select": "select",
    "multiselect": "multiselect",
    "file_path": "file_path",
    "text_area": "text_area",
}

# Category → default icon mapping (for blocks that don't specify one)
CATEGORY_ICONS: dict[str, str] = {
    "data": "Database",
    "source": "Download",
    "training": "GraduationCap",
    "inference": "Cpu",
    "evaluation": "BarChart3",
    "merge": "GitMerge",
    "flow": "Workflow",
    "agents": "Bot",
    "endpoints": "Upload",
    "output": "FileOutput",
    "embedding": "Waypoints",
    "interventions": "Wrench",
}

# Category → default accent color
CATEGORY_ACCENTS: dict[str, str] = {
    "data": "#3b82f6",
    "source": "#F97316",
    "training": "#f59e0b",
    "inference": "#8b5cf6",
    "evaluation": "#10b981",
    "merge": "#ec4899",
    "flow": "#6366f1",
    "agents": "#06b6d4",
    "endpoints": "#84cc16",
    "output": "#f97316",
    "embedding": "#FB7185",
    "interventions": "#FBBF24",
}


def load_all_blocks() -> list[dict]:
    """Scan blocks/ directory and load all block.yaml files."""
    blocks = []

    for category_dir in sorted(BLOCKS_DIR.iterdir()):
        if not category_dir.is_dir() or category_dir.name.startswith((".", "_")):
            continue
        category = category_dir.name

        for block_dir in sorted(category_dir.iterdir()):
            if not block_dir.is_dir() or block_dir.name.startswith((".", "_")):
                continue

            yaml_path = block_dir / "block.yaml"
            if not yaml_path.exists():
                continue

            try:
                with open(yaml_path) as f:
                    schema = yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                print(f"WARNING: Skipping {yaml_path} — YAML parse error: {e}", file=sys.stderr)
                continue

            has_run = (block_dir / "run.py").exists()

            block: dict[str, Any] = {
                "type": schema.get("type", block_dir.name),
                "name": schema.get("name", block_dir.name.replace("_", " ").title()),
                "description": schema.get("description", ""),
                "category": schema.get("category", category),
                "version": schema.get("version", "1.0.0"),
                "tags": schema.get("tags", []),
                "aliases": schema.get("aliases", []),
                "icon": schema.get("icon", CATEGORY_ICONS.get(category, "Box")),
                "accent": schema.get("accent", CATEGORY_ACCENTS.get(category, "#6b7280")),
                "maturity": schema.get("maturity", "stable" if has_run else "experimental"),
                "inputs": _convert_ports(schema.get("inputs", [])),
                "outputs": _convert_ports(schema.get("outputs", [])),
                "defaultConfig": _extract_defaults(schema.get("config", {})),
                "configFields": _convert_config_fields(schema.get("config", {})),
            }

            # Optional detail fields
            if "detail" in schema:
                block["detail"] = schema["detail"]
            if schema.get("deprecated"):
                block["deprecated"] = True
                block["deprecatedMessage"] = schema.get("deprecated_message", "")
            if schema.get("recommended"):
                block["recommended"] = True

            blocks.append(block)

    return blocks


def _convert_ports(ports: list[dict] | None) -> list[dict]:
    """Convert block.yaml port definitions to TypeScript PortDefinition format."""
    if not ports:
        return []
    return [
        {
            "id": p.get("id", ""),
            "label": p.get("label", p.get("id", "")),
            "dataType": p.get("data_type", "any"),
            "required": p.get("required", False),
        }
        for p in ports
    ]


def _extract_defaults(config_schema: dict | None) -> dict:
    """Extract default values from config schema."""
    if not config_schema:
        return {}
    defaults = {}
    for field_name, field_def in config_schema.items():
        if not isinstance(field_def, dict):
            continue
        if "default" in field_def:
            defaults[field_name] = field_def["default"]
        elif field_def.get("type") == "boolean":
            defaults[field_name] = False
        elif field_def.get("type") in ("integer", "float"):
            defaults[field_name] = 0
        else:
            defaults[field_name] = ""
    return defaults


def _convert_config_fields(config_schema: dict | None) -> list[dict]:
    """Convert block.yaml config to TypeScript ConfigField[] format."""
    if not config_schema:
        return []
    fields = []
    for field_name, field_def in config_schema.items():
        if not isinstance(field_def, dict):
            continue
        field: dict[str, Any] = {
            "name": field_name,
            "label": field_def.get("label", field_name.replace("_", " ").title()),
            "type": YAML_TYPE_TO_TS.get(field_def.get("type", "string"), "string"),
        }
        if "default" in field_def:
            field["default"] = field_def["default"]
        if "min" in field_def:
            field["min"] = field_def["min"]
        if "max" in field_def:
            field["max"] = field_def["max"]
        if "options" in field_def:
            field["options"] = field_def["options"]
        if "description" in field_def:
            field["description"] = field_def["description"]
        if "depends_on" in field_def:
            field["depends_on"] = field_def["depends_on"]
        fields.append(field)
    return fields


def _ts_value(value: Any, indent: int = 0) -> str:
    """Convert a Python value to a TypeScript literal string."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        # Preserve scientific notation for small floats like 2e-5
        if 0 < abs(value) < 0.001:
            # Use scientific notation
            s = f"{value:.1e}".replace("+", "")
            # Clean up: 2.0e-5 -> 2e-5
            s = s.replace(".0e", "e")
            return s
        return repr(value)
    if isinstance(value, str):
        # Escape for single-quoted TS string
        escaped = value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
        return f"'{escaped}'"
    if isinstance(value, list):
        if not value:
            return "[]"
        items = [_ts_value(v, indent + 2) for v in value]
        if sum(len(i) for i in items) + len(items) * 2 < 80:
            return "[" + ", ".join(items) + "]"
        pad = " " * (indent + 2)
        inner = (",\n" + pad).join(items)
        return f"[\n{pad}{inner},\n{' ' * indent}]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        pad = " " * (indent + 2)
        pairs = []
        for k, v in value.items():
            key = k if k.isidentifier() else f"'{k}'"
            pairs.append(f"{key}: {_ts_value(v, indent + 2)}")
        if sum(len(p) for p in pairs) + len(pairs) * 2 < 80:
            return "{ " + ", ".join(pairs) + " }"
        inner = (",\n" + pad).join(pairs)
        return f"{{\n{pad}{inner},\n{' ' * indent}}}"
    return repr(value)


def _format_port(port: dict) -> str:
    """Format a port definition as a single-line TS object."""
    parts = [
        f"id: '{port['id']}'",
        f"label: '{port['label']}'",
        f"dataType: '{port['dataType']}'",
        f"required: {'true' if port['required'] else 'false'}",
    ]
    return "{ " + ", ".join(parts) + " }"


def _format_config_field(field: dict, indent: str) -> str:
    """Format a config field as a TS object."""
    parts = [
        f"name: '{field['name']}'",
        f"label: '{field['label']}'",
        f"type: '{field['type']}'",
    ]
    for key in ("default", "min", "max"):
        if key in field:
            parts.append(f"{key}: {_ts_value(field[key])}")
    if "options" in field:
        opts = ", ".join(f"'{o}'" for o in field["options"])
        parts.append(f"options: [{opts}]")
    if "description" in field:
        parts.append(f"description: {_ts_value(field['description'])}")
    if "depends_on" in field:
        dep = field["depends_on"]
        parts.append(f"depends_on: {{ field: '{dep['field']}', value: {_ts_value(dep['value'])} }}")

    joined = ", ".join(parts)
    if len(joined) < 100:
        return "{ " + joined + " }"
    # Multi-line
    inner = (",\n" + indent + "  ").join(parts)
    return "{\n" + indent + "  " + inner + ",\n" + indent + "}"


def _format_block(block: dict) -> str:
    """Format a single block definition as a TypeScript object literal."""
    lines = []
    lines.append("  {")
    lines.append(f"    type: '{block['type']}',")
    lines.append(f"    name: {_ts_value(block['name'])},")
    lines.append(f"    description: {_ts_value(block['description'])},")
    lines.append(f"    category: '{block['category']}',")
    # tags
    if block["tags"]:
        tags = ", ".join(f"'{t}'" for t in block["tags"])
        lines.append(f"    tags: [{tags}],")
    else:
        lines.append("    tags: [],")
    # aliases
    if block["aliases"]:
        aliases = ", ".join(f"'{a}'" for a in block["aliases"])
        lines.append(f"    aliases: [{aliases}],")
    else:
        lines.append("    aliases: [],")
    lines.append(f"    icon: '{block['icon']}',")
    lines.append(f"    accent: '{block['accent']}',")
    lines.append(f"    maturity: '{block['maturity']}',")

    # inputs
    if block["inputs"]:
        port_strs = [f"      {_format_port(p)}," for p in block["inputs"]]
        lines.append("    inputs: [")
        lines.extend(port_strs)
        lines.append("    ],")
    else:
        lines.append("    inputs: [],")

    # outputs
    if block["outputs"]:
        port_strs = [f"      {_format_port(p)}," for p in block["outputs"]]
        lines.append("    outputs: [")
        lines.extend(port_strs)
        lines.append("    ],")
    else:
        lines.append("    outputs: [],")

    # defaultConfig
    lines.append(f"    defaultConfig: {_ts_value(block['defaultConfig'], 4)},")

    # configFields
    if block["configFields"]:
        lines.append("    configFields: [")
        for cf in block["configFields"]:
            lines.append(f"      {_format_config_field(cf, '      ')},")
        lines.append("    ],")
    else:
        lines.append("    configFields: [],")

    # Optional fields
    if "detail" in block:
        lines.append(f"    detail: {_ts_value(block['detail'], 4)},")
    if block.get("deprecated"):
        lines.append("    deprecated: true,")
        lines.append(f"    deprecatedMessage: {_ts_value(block.get('deprecatedMessage', ''))},")
    if block.get("recommended"):
        lines.append("    recommended: true,")

    lines.append("  }")
    return "\n".join(lines)


def generate_typescript(blocks: list[dict]) -> str:
    """Generate the TypeScript source for block-registry.generated.ts."""
    # Count stats
    categories: dict[str, int] = {}
    for b in blocks:
        cat = b["category"]
        categories[cat] = categories.get(cat, 0) + 1

    header = [
        "// AUTO-GENERATED — DO NOT EDIT MANUALLY",
        f"// Generated from {len(blocks)} block.yaml files across {len(categories)} categories",
        "// Run: python scripts/generate_block_registry.py",
        "",
        "import type { BlockDefinition } from './block-registry-types'",
        "",
        "export const BLOCK_REGISTRY: BlockDefinition[] = [",
    ]

    # Group blocks by category for readability
    block_sections = []
    current_category = None
    for block in blocks:
        if block["category"] != current_category:
            current_category = block["category"]
            block_sections.append("")
            block_sections.append(f"  // ═══════════════════════════════════════════════")
            cat_label = current_category.upper()
            count = categories[current_category]
            block_sections.append(f"  //  {cat_label} ({count} blocks)")
            block_sections.append(f"  // ═══════════════════════════════════════════════")
            block_sections.append("")
        block_sections.append(_format_block(block) + ",")

    footer = [
        "]",
        "",
    ]

    return "\n".join(header) + "\n" + "\n".join(block_sections) + "\n" + "\n".join(footer)


def main():
    blocks = load_all_blocks()

    if not blocks:
        print("ERROR: No block.yaml files found!", file=sys.stderr)
        sys.exit(1)

    ts_content = generate_typescript(blocks)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(ts_content)

    print(f"Generated {OUTPUT_FILE} with {len(blocks)} blocks")

    # Verify: count by category
    categories: dict[str, int] = {}
    for b in blocks:
        cat = b["category"]
        categories[cat] = categories.get(cat, 0) + 1
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count} blocks")


if __name__ == "__main__":
    main()
