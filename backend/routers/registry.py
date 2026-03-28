"""Registry API — single source of truth for block schemas.

Serves block definitions (transformed from block.yaml files) in the same
shape the frontend expects (BlockDefinition interface).  Replaces the
hand-maintained frontend block-registry.ts.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..config import BUILTIN_BLOCKS_DIR, BLOCKS_DIR, CUSTOM_BLOCKS_DIR

logger = logging.getLogger("blueprint.registry")

router = APIRouter(prefix="/api/registry", tags=["registry"])

# ─── Category defaults ───────────────────────────────────────────────
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

YAML_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "integer": "integer",
    "float": "float",
    "boolean": "boolean",
    "select": "select",
    "multiselect": "multiselect",
    "file_path": "file_path",
    "text_area": "text_area",
}

# ─── Port compatibility (loaded from docs/PORT_COMPATIBILITY.yaml) ────
_COMPAT_YAML = Path(__file__).resolve().parent.parent.parent / "docs" / "PORT_COMPATIBILITY.yaml"


def _load_port_compat() -> tuple[dict[str, str], dict[str, set[str]]]:
    """Load aliases and compatibility matrix from the canonical YAML file."""
    try:
        with open(_COMPAT_YAML) as f:
            data = yaml.safe_load(f)
        aliases = data.get("aliases", {})
        compat_raw = data.get("compatibility_matrix", {})
        compat = {k: set(v) for k, v in compat_raw.items()}
        return aliases, compat
    except (OSError, yaml.YAMLError) as e:
        logger.warning("Failed to load PORT_COMPATIBILITY.yaml, using empty compat: %s", e)
        return {}, {}


PORT_TYPE_ALIASES, COMPAT = _load_port_compat()


def _is_port_compatible(source: str, target: str) -> bool:
    s = PORT_TYPE_ALIASES.get(source, source)
    t = PORT_TYPE_ALIASES.get(target, target)
    return t in COMPAT.get(s, set())


# ─── Pydantic models ─────────────────────────────────────────────────

class PortSchema(BaseModel):
    id: str
    label: str
    dataType: str
    required: bool = False
    aliases: list[str] | None = None


class ConfigFieldSchema(BaseModel):
    name: str
    label: str
    type: str
    default: Any = None
    min: float | None = None
    max: float | None = None
    options: list[str] | None = None
    description: str | None = None
    depends_on: dict[str, Any] | None = None
    mandatory: bool | None = None
    path_mode: str | None = None
    file_extensions: list[str] | None = None
    propagate: bool | None = None
    section: str | None = None


class BlockDetailSchema(BaseModel):
    format: str | None = None
    formatEditable: bool | None = None
    codePreview: str | None = None
    tips: list[str] | None = None
    useCases: list[str] | None = None
    howItWorks: str | None = None


class BlockSchema(BaseModel):
    type: str
    name: str
    description: str
    category: str
    tags: list[str] = []
    aliases: list[str] = []
    icon: str
    accent: str
    maturity: str = "stable"
    inputs: list[PortSchema] = []
    outputs: list[PortSchema] = []
    defaultConfig: dict[str, Any] = {}
    configFields: list[ConfigFieldSchema] = []
    detail: BlockDetailSchema | None = None
    deprecated: bool | None = None
    deprecatedMessage: str | None = None
    recommended: bool | None = None
    side_inputs: list[PortSchema] | None = None


class ValidateConnectionRequest(BaseModel):
    src_type: str
    src_port: str
    dst_type: str
    dst_port: str


class ValidateConnectionResponse(BaseModel):
    valid: bool
    error: str | None = None


class RegistryVersionResponse(BaseModel):
    version: int


class RegistryHealthResponse(BaseModel):
    total_blocks: int
    categories: dict[str, int]
    broken_blocks: list[str]


# ─── Block discovery & caching ───────────────────────────────────────

_lock = threading.Lock()
_blocks: dict[str, BlockSchema] = {}
_broken: list[str] = []
_version: int = 0


def _convert_port(p: dict) -> PortSchema:
    port = PortSchema(
        id=p.get("id", ""),
        label=p.get("label", p.get("id", "")),
        dataType=p.get("data_type", "any"),
        required=p.get("required", False),
    )
    if p.get("aliases"):
        port.aliases = p["aliases"]
    return port


def _convert_config_fields(config_schema: dict | None) -> list[ConfigFieldSchema]:
    if not config_schema:
        return []
    fields = []
    for field_name, field_def in config_schema.items():
        if not isinstance(field_def, dict):
            continue
        field = ConfigFieldSchema(
            name=field_name,
            label=field_def.get("label", field_name.replace("_", " ").title()),
            type=YAML_TYPE_MAP.get(field_def.get("type", "string"), "string"),
        )
        if "default" in field_def:
            field.default = field_def["default"]
        if "min" in field_def:
            field.min = field_def["min"]
        if "max" in field_def:
            field.max = field_def["max"]
        if "options" in field_def:
            field.options = field_def["options"]
        if "description" in field_def:
            field.description = field_def["description"]
        if "depends_on" in field_def:
            field.depends_on = field_def["depends_on"]
        if field_def.get("mandatory"):
            field.mandatory = True
        if "path_mode" in field_def:
            field.path_mode = field_def["path_mode"]
        if "file_extensions" in field_def:
            field.file_extensions = field_def["file_extensions"]
        if field_def.get("propagate"):
            field.propagate = True
        if "section" in field_def:
            field.section = field_def["section"]
        fields.append(field)
    return fields


def _extract_defaults(config_schema: dict | None) -> dict:
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


def _load_block(yaml_path: Path, category: str) -> BlockSchema | None:
    """Load a single block.yaml and transform to BlockSchema."""
    try:
        with open(yaml_path) as f:
            schema = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError) as e:
        logger.warning("Skipping %s — YAML parse error: %s", yaml_path, e)
        return None

    block_dir = yaml_path.parent
    has_run = (block_dir / "run.py").exists()

    block = BlockSchema(
        type=schema.get("type", block_dir.name),
        name=schema.get("name", block_dir.name.replace("_", " ").title()),
        description=schema.get("description", ""),
        category=schema.get("category", category),
        tags=schema.get("tags", []),
        aliases=schema.get("aliases", []),
        icon=schema.get("icon", CATEGORY_ICONS.get(category, "Box")),
        accent=schema.get("accent", CATEGORY_ACCENTS.get(category, "#6b7280")),
        maturity=schema.get("maturity", "stable" if has_run else "experimental"),
        inputs=[_convert_port(p) for p in schema.get("inputs", [])],
        outputs=[_convert_port(p) for p in schema.get("outputs", [])],
        defaultConfig=_extract_defaults(schema.get("config", {})),
        configFields=_convert_config_fields(schema.get("config", {})),
    )

    # Side inputs
    side_inputs = schema.get("side_inputs", [])
    if side_inputs:
        block.side_inputs = [_convert_port(p) for p in side_inputs]

    # Optional detail fields
    if "detail" in schema:
        block.detail = BlockDetailSchema(**schema["detail"])
    if schema.get("deprecated"):
        block.deprecated = True
        block.deprecatedMessage = schema.get("deprecated_message", "")
    if schema.get("recommended"):
        block.recommended = True

    return block


def discover_all() -> tuple[dict[str, BlockSchema], list[str]]:
    """Scan all block directories and return (blocks_map, broken_list)."""
    blocks: dict[str, BlockSchema] = {}
    broken: list[str] = []

    for directory in [BUILTIN_BLOCKS_DIR, BLOCKS_DIR, CUSTOM_BLOCKS_DIR]:
        if not directory.exists():
            continue
        for category_dir in sorted(directory.iterdir()):
            if not category_dir.is_dir() or category_dir.name.startswith((".", "_")):
                continue
            category = category_dir.name
            for block_dir in sorted(category_dir.iterdir()):
                if not block_dir.is_dir() or block_dir.name.startswith((".", "_")):
                    continue
                yaml_path = block_dir / "block.yaml"
                if not yaml_path.exists():
                    continue
                block = _load_block(yaml_path, category)
                if block:
                    blocks[block.type] = block
                else:
                    broken.append(str(yaml_path))

    return blocks, broken


def _ensure_loaded():
    """Lazy-load blocks on first access."""
    global _blocks, _broken, _version
    if _version == 0:
        with _lock:
            if _version == 0:
                _blocks, _broken = discover_all()
                _version = 1
                logger.info("Registry loaded: %d blocks, %d broken", len(_blocks), len(_broken))


def get_all_blocks() -> dict[str, BlockSchema]:
    _ensure_loaded()
    return _blocks


def get_block(block_type: str) -> BlockSchema | None:
    _ensure_loaded()
    return _blocks.get(block_type)


def get_health() -> RegistryHealthResponse:
    _ensure_loaded()
    categories: dict[str, int] = {}
    for b in _blocks.values():
        categories[b.category] = categories.get(b.category, 0) + 1
    return RegistryHealthResponse(
        total_blocks=len(_blocks),
        categories=categories,
        broken_blocks=_broken,
    )


# ─── API endpoints ───────────────────────────────────────────────────

@router.get("/blocks", response_model=list[BlockSchema])
def list_registry_blocks(
    category: Optional[str] = Query(None, description="Filter by category"),
    source: Optional[str] = Query(None, description="Filter by source"),
    include_broken: bool = Query(False, description="Include broken blocks"),
):
    """List all block schemas (frontend-ready BlockDefinition shape)."""
    _ensure_loaded()
    result = list(_blocks.values())
    if category:
        result = [b for b in result if b.category == category]
    return result


@router.get("/blocks/{block_type}", response_model=BlockSchema)
def get_registry_block(block_type: str):
    """Get a single block schema by type, or 404."""
    _ensure_loaded()
    block = _blocks.get(block_type)
    if not block:
        raise HTTPException(404, f"Block type '{block_type}' not found")
    return block


@router.get("/version", response_model=RegistryVersionResponse)
def registry_version():
    """Return the current registry version (increments on refresh)."""
    _ensure_loaded()
    return RegistryVersionResponse(version=_version)


@router.post("/validate-connection", response_model=ValidateConnectionResponse)
def validate_connection(req: ValidateConnectionRequest):
    """Check if a source port type can connect to a destination port type."""
    valid = _is_port_compatible(req.src_port, req.dst_port)
    error = None if valid else f"Port type '{req.src_port}' is not compatible with '{req.dst_port}'"
    return ValidateConnectionResponse(valid=valid, error=error)


@router.get("/health", response_model=RegistryHealthResponse)
def registry_health():
    """Return health summary: total blocks, per-category counts, broken blocks."""
    return get_health()


@router.post("/refresh", response_model=RegistryVersionResponse)
def refresh_registry():
    """Re-scan block directories and update the registry. Returns new version."""
    global _blocks, _broken, _version
    with _lock:
        _blocks, _broken = discover_all()
        _version += 1
        logger.info("Registry refreshed: v%d, %d blocks, %d broken", _version, len(_blocks), len(_broken))
    return RegistryVersionResponse(version=_version)
