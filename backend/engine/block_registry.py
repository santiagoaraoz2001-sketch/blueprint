"""Block Registry — discovers all available blocks by scanning the blocks/ directory."""

import os
from pathlib import Path
from typing import Any, Optional

import yaml

# Root blocks directory
BLOCKS_DIR = Path(__file__).parent.parent.parent / "blocks"

# Cache of discovered block types
_registry: dict[str, dict] = {}
_scanned = False


def scan_blocks() -> dict[str, dict]:
    """Scan the blocks/ directory and build a registry of available block types."""
    global _registry, _scanned
    if _scanned:
        return _registry

    _registry = {}
    if not BLOCKS_DIR.exists():
        _scanned = True
        return _registry

    for category_dir in sorted(BLOCKS_DIR.iterdir()):
        if not category_dir.is_dir() or category_dir.name.startswith(('.', '_')):
            continue
        category = category_dir.name
        for block_dir in sorted(category_dir.iterdir()):
            if not block_dir.is_dir() or block_dir.name.startswith(('.', '_')):
                continue
            run_file = block_dir / "run.py"
            if run_file.exists():
                block_type = block_dir.name
                _registry[block_type] = {
                    "type": block_type,
                    "category": category,
                    "path": str(block_dir),
                    "has_run": True,
                }

    _scanned = True
    return _registry


def get_block_types() -> set[str]:
    """Return all known block type identifiers."""
    return set(scan_blocks().keys())


def is_known_block(block_type: str) -> bool:
    """Check if a block type exists in the registry."""
    return block_type in scan_blocks()


def get_block_info(block_type: str) -> Optional[dict]:
    """Get info about a specific block type."""
    return scan_blocks().get(block_type)


def get_category(block_type: str) -> str:
    """Get the category of a block type."""
    info = get_block_info(block_type)
    return info["category"] if info else "unknown"


# Cache parsed block.yaml schemas
_yaml_cache: dict[str, dict] = {}


def get_block_yaml(block_type: str) -> Optional[dict]:
    """Load and cache the full block.yaml for a block type.

    Returns the parsed YAML dict, or None if the block type is unknown
    or has no block.yaml.
    """
    if block_type in _yaml_cache:
        return _yaml_cache[block_type]

    info = get_block_info(block_type)
    if not info:
        return None

    yaml_path = Path(info["path"]) / "block.yaml"
    if not yaml_path.exists():
        return None

    try:
        with open(yaml_path, "r") as f:
            parsed = yaml.safe_load(f) or {}
        _yaml_cache[block_type] = parsed
        return parsed
    except (yaml.YAMLError, OSError):
        return None


def get_block_config_schema(block_type: str) -> dict[str, Any]:
    """Return the 'config' section from a block's block.yaml.

    Returns an empty dict if the block has no config schema.
    """
    block_yaml = get_block_yaml(block_type)
    if not block_yaml:
        return {}
    return block_yaml.get("config", {})


# Cache output alias maps: block_type -> {old_id: new_id}
_output_alias_cache: dict[str, dict[str, str]] = {}


def get_output_alias_map(block_type: str) -> dict[str, str]:
    """Build a map from aliased (old) output port IDs to canonical (current) IDs.

    Returns {old_id: canonical_id} for any output port that declares aliases.
    Used by the executor to resolve edge sourceHandles that reference old port names.
    """
    if block_type in _output_alias_cache:
        return _output_alias_cache[block_type]

    alias_map: dict[str, str] = {}
    schema = get_block_yaml(block_type)
    if schema:
        for output in schema.get("outputs", []):
            canonical = output.get("id", "")
            for alias in output.get("aliases", []):
                alias_map[alias] = canonical

    _output_alias_cache[block_type] = alias_map
    return alias_map


def resolve_output_handle(block_type: str, handle: str) -> str:
    """Resolve an output handle ID, mapping old aliases to canonical IDs.

    Returns the canonical ID if the handle is an alias, otherwise returns handle unchanged.
    """
    alias_map = get_output_alias_map(block_type)
    return alias_map.get(handle, handle)


def reset() -> None:
    """Clear all cached state so the next scan_blocks() re-discovers blocks."""
    global _registry, _scanned, _yaml_cache, _output_alias_cache
    _scanned = False
    _registry = {}
    _yaml_cache = {}
    _output_alias_cache = {}
