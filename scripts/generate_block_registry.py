#!/usr/bin/env python3
"""
Generate frontend/src/lib/block-registry.generated.ts from block.yaml files.

Usage:
    python scripts/generate_block_registry.py

Reads: blocks/**/block.yaml
Writes: frontend/src/lib/block-registry.generated.ts
"""

import sys
import yaml
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BLOCKS_DIR = PROJECT_ROOT / "blocks"
OUTPUT_FILE = PROJECT_ROOT / "frontend" / "src" / "lib" / "block-registry.generated.ts"
CONFIGS_FILE = PROJECT_ROOT / "frontend" / "src" / "lib" / "block-configs.generated.ts"
BLOCK_TYPES_FILE = PROJECT_ROOT / "frontend" / "src" / "lib" / "generated" / "block-types.ts"

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

            # Side inputs (control ports rendered on left edge)
            side_inputs = _convert_ports(schema.get("side_inputs", []))
            if side_inputs:
                block["side_inputs"] = side_inputs

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
    result = []
    for p in ports:
        port: dict[str, Any] = {
            "id": p.get("id", ""),
            "label": p.get("label", p.get("id", "")),
            "dataType": p.get("data_type", "any"),
            "required": p.get("required", False),
        }
        if p.get("aliases"):
            port["aliases"] = p["aliases"]
        result.append(port)
    return result


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
        if field_def.get("mandatory"):
            field["mandatory"] = True
        if "path_mode" in field_def:
            field["path_mode"] = field_def["path_mode"]
        if "file_extensions" in field_def:
            field["file_extensions"] = field_def["file_extensions"]
        if field_def.get("propagate"):
            field["propagate"] = True
        if "section" in field_def:
            field["section"] = field_def["section"]
        fields.append(field)
    return fields


def _esc(s: str) -> str:
    """Escape a string for embedding in a single-quoted TypeScript literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")


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
        return f"'{_esc(value)}'"
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
            key = k if k.isidentifier() else f"'{_esc(k)}'"
            pairs.append(f"{key}: {_ts_value(v, indent + 2)}")
        if sum(len(p) for p in pairs) + len(pairs) * 2 < 80:
            return "{ " + ", ".join(pairs) + " }"
        inner = (",\n" + pad).join(pairs)
        return f"{{\n{pad}{inner},\n{' ' * indent}}}"
    return repr(value)


def _format_port(port: dict) -> str:
    """Format a port definition as a single-line TS object."""
    parts = [
        f"id: '{_esc(port['id'])}'",
        f"label: '{_esc(port['label'])}'",
        f"dataType: '{_esc(port['dataType'])}'",
        f"required: {'true' if port['required'] else 'false'}",
    ]
    if port.get("aliases"):
        aliases_str = ", ".join(f"'{_esc(a)}'" for a in port["aliases"])
        parts.append(f"aliases: [{aliases_str}]")
    return "{ " + ", ".join(parts) + " }"


def _format_config_field(field: dict, indent: str) -> str:
    """Format a config field as a TS object."""
    parts = [
        f"name: '{_esc(field['name'])}'",
        f"label: '{_esc(field['label'])}'",
        f"type: '{_esc(field['type'])}'",
    ]
    for key in ("default", "min", "max"):
        if key in field:
            parts.append(f"{key}: {_ts_value(field[key])}")
    if "options" in field:
        opts = ", ".join(f"'{_esc(o)}'" for o in field["options"])
        parts.append(f"options: [{opts}]")
    if "description" in field:
        parts.append(f"description: {_ts_value(field['description'])}")
    if "depends_on" in field:
        dep = field["depends_on"]
        parts.append(f"depends_on: {{ field: '{_esc(dep['field'])}', value: {_ts_value(dep['value'])} }}")
    if field.get("mandatory"):
        parts.append("mandatory: true")
    if "path_mode" in field:
        parts.append(f"path_mode: '{_esc(field['path_mode'])}'")
    if "file_extensions" in field:
        exts = ", ".join(f"'{_esc(e)}'" for e in field["file_extensions"])
        parts.append(f"file_extensions: [{exts}]")
    if field.get("propagate"):
        parts.append("propagate: true")
    if "section" in field:
        parts.append(f"section: '{_esc(field['section'])}'")


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
    lines.append(f"    type: '{_esc(block['type'])}',")
    lines.append(f"    name: {_ts_value(block['name'])},")
    lines.append(f"    description: {_ts_value(block['description'])},")
    lines.append(f"    category: '{_esc(block['category'])}',")
    # tags
    if block["tags"]:
        tags = ", ".join(f"'{_esc(t)}'" for t in block["tags"])
        lines.append(f"    tags: [{tags}],")
    else:
        lines.append("    tags: [],")
    # aliases
    if block["aliases"]:
        aliases = ", ".join(f"'{_esc(a)}'" for a in block["aliases"])
        lines.append(f"    aliases: [{aliases}],")
    else:
        lines.append("    aliases: [],")
    lines.append(f"    icon: '{_esc(block['icon'])}',")
    lines.append(f"    accent: '{_esc(block['accent'])}',")
    lines.append(f"    maturity: '{_esc(block['maturity'])}',")

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

    # Side inputs (control ports on left edge)
    if block.get("side_inputs"):
        port_strs = [f"      {_format_port(p)}," for p in block["side_inputs"]]
        lines.append("    side_inputs: [")
        lines.extend(port_strs)
        lines.append("    ],")

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


def _to_pascal_case(snake: str) -> str:
    """Convert snake_case block type to PascalCase for TypeScript interface name."""
    return "".join(word.capitalize() for word in snake.split("_"))


def _yaml_type_to_ts_type(field_def: dict) -> str:
    """Map a YAML config field type + default to a TypeScript type string."""
    yaml_type = field_def.get("type", "string")
    default = field_def.get("default")

    if yaml_type == "boolean":
        return "boolean"
    if yaml_type in ("integer", "float"):
        # If default is null/None, the field is nullable
        if default is None:
            return "number | null"
        return "number"
    if yaml_type == "select":
        options = field_def.get("options", [])
        if options:
            return " | ".join(f"'{_esc(o)}'" for o in options)
        return "string"
    if yaml_type == "multiselect":
        return "string[]"
    # string, file_path, text_area → string
    return "string"


def _ts_default_literal(value: Any, ts_type: str) -> str:
    """Convert a default value to its TypeScript literal, type-safe."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if 0 < abs(value) < 0.001:
            s = f"{value:.1e}".replace("+", "")
            s = s.replace(".0e", "e")
            return s
        return repr(value)
    if isinstance(value, list):
        items = ", ".join(f"'{_esc(str(v))}'" for v in value)
        return f"[{items}]"
    return f"'{_esc(str(value))}'"


def generate_block_configs(blocks: list[dict]) -> str:
    """Generate block-configs.generated.ts with per-block config interfaces and defaults."""
    lines = [
        "// AUTO-GENERATED — DO NOT EDIT MANUALLY",
        f"// Generated from {len(blocks)} block.yaml config schemas",
        "// Run: python scripts/generate_block_registry.py",
        "",
    ]

    interface_names: list[tuple[str, str]] = []  # (block_type, InterfaceName)
    default_names: list[tuple[str, str]] = []  # (block_type, CONSTANT_NAME)

    for block in blocks:
        block_type = block["type"]
        pascal = _to_pascal_case(block_type)
        interface_name = f"{pascal}Config"
        const_name = f"{block_type.upper()}_DEFAULTS"
        config_fields = block.get("configFields", [])

        if not config_fields:
            # Blocks with no config get an empty interface
            lines.append(f"/** Config for `{block_type}` block */")
            lines.append(f"export interface {interface_name} {{")
            lines.append(f"  [key: string]: unknown")
            lines.append(f"}}")
            lines.append("")
            lines.append(f"export const {const_name}: {interface_name} = {{}}")
            lines.append("")
            interface_names.append((block_type, interface_name))
            default_names.append((block_type, const_name))
            continue

        # Interface
        lines.append(f"/** Config for `{block_type}` block */")
        lines.append(f"export interface {interface_name} {{")
        for field in config_fields:
            fname = field["name"]
            ts_type = _yaml_type_to_ts_type(field)
            desc = field.get("description", "")
            if desc:
                lines.append(f"  /** {desc} */")
            lines.append(f"  {fname}: {ts_type}")
        lines.append("}")
        lines.append("")

        # Defaults constant
        defaults = block.get("defaultConfig", {})
        lines.append(f"export const {const_name}: {interface_name} = {{")
        for field in config_fields:
            fname = field["name"]
            default_val = defaults.get(fname)
            ts_type = _yaml_type_to_ts_type(field)
            lit = _ts_default_literal(default_val, ts_type)
            lines.append(f"  {fname}: {lit},")
        lines.append("}")
        lines.append("")

        interface_names.append((block_type, interface_name))
        default_names.append((block_type, const_name))

    # Discriminated union: BlockType → Config type
    lines.append("// ═══════════════════════════════════════════════")
    lines.append("//  DISCRIMINATED UNION: block type → config type")
    lines.append("// ═══════════════════════════════════════════════")
    lines.append("")
    lines.append("export interface BlockConfigMap {")
    for block_type, iname in interface_names:
        lines.append(f"  {block_type}: {iname}")
    lines.append("}")
    lines.append("")

    # Type-safe accessor
    lines.append("/** All known block type strings */")
    lines.append("export type BlockType = keyof BlockConfigMap")
    lines.append("")

    # Defaults lookup
    lines.append("/** Type-safe default config lookup by block type */")
    lines.append("export const BLOCK_DEFAULTS: { [K in BlockType]: BlockConfigMap[K] } = {")
    for block_type, cname in default_names:
        lines.append(f"  {block_type}: {cname},")
    lines.append("}")
    lines.append("")

    return "\n".join(lines)


def generate_block_types_union(blocks: list[dict]) -> str:
    """Generate frontend/src/lib/generated/block-types.ts — union type of all block types."""
    block_types = sorted(set(b["type"] for b in blocks))
    lines = [
        "// AUTO-GENERATED — DO NOT EDIT MANUALLY",
        f"// Generated from {len(blocks)} block.yaml files",
        "// Run: python scripts/generate_block_registry.py",
        "",
        "export type BlockType =",
    ]
    for i, bt in enumerate(block_types):
        sep = "" if i == len(block_types) - 1 else " |"
        lines.append(f"  | '{_esc(bt)}'")
    lines.append("")
    return "\n".join(lines) + "\n"


def main():
    if not BLOCKS_DIR.is_dir():
        print(f"ERROR: Blocks directory not found: {BLOCKS_DIR}", file=sys.stderr)
        sys.exit(1)

    blocks = load_all_blocks()

    if not blocks:
        print("ERROR: No block.yaml files found!", file=sys.stderr)
        sys.exit(1)

    ts_content = generate_typescript(blocks)
    configs_content = generate_block_configs(blocks)
    block_types_content = generate_block_types_union(blocks)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(ts_content)
    CONFIGS_FILE.write_text(configs_content)

    BLOCK_TYPES_FILE.parent.mkdir(parents=True, exist_ok=True)
    BLOCK_TYPES_FILE.write_text(block_types_content)

    print(f"Generated {OUTPUT_FILE} with {len(blocks)} blocks")
    print(f"Generated {CONFIGS_FILE} with {len(blocks)} config interfaces")
    print(f"Generated {BLOCK_TYPES_FILE} with {len(blocks)} block types")

    # Summary by category
    categories: dict[str, int] = {}
    for b in blocks:
        cat = b["category"]
        categories[cat] = categories.get(cat, 0) + 1
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count} blocks")


if __name__ == "__main__":
    main()
