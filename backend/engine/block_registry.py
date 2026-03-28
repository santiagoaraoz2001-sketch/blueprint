"""Block Registry — thin delegation layer over BlockRegistryService.

All block discovery and metadata now lives in ``backend.services.registry``.
This module preserves the original function-call API so existing callers
(executor, compiler, validator, routers) continue to work without changes.

**New code should import from ``backend.services.registry`` directly.**

Deprecation timeline:
  - v0.3.0: callers should migrate to ``BlockRegistryService`` or
    ``get_global_registry()``.
  - v0.4.0: this module will be removed.
"""

from __future__ import annotations

import warnings
from typing import Any, Optional

from backend.services.registry import (
    BlockRegistryService,
    get_global_registry,
    reset_global_registry,
)

# ── Deprecation helper ────────────────────────────────────────

_DEPRECATION_MSG = (
    "backend.engine.block_registry is deprecated. "
    "Use backend.services.registry.get_global_registry() instead. "
    "This module will be removed in v0.4.0."
)


def _warn() -> None:
    warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=3)


def _svc() -> BlockRegistryService:
    """Return the global singleton (lazy-initializes if needed)."""
    return get_global_registry()


# ── Public API (mirrors the old module exactly) ────────────────

def scan_blocks() -> dict[str, dict]:
    """Scan block directories and return {block_type: info_dict}."""
    _warn()
    svc = _svc()
    return {
        bt: {
            "type": bt,
            "category": schema.category,
            "path": schema.source_path,
            "has_run": True,
        }
        for bt, schema in svc._blocks.items()
    }


def get_block_types() -> set[str]:
    _warn()
    return _svc().get_block_types()


def is_known_block(block_type: str) -> bool:
    _warn()
    return _svc().is_known_block(block_type)


def get_block_info(block_type: str) -> Optional[dict]:
    _warn()
    return _svc().get_block_info(block_type)


def get_category(block_type: str) -> str:
    _warn()
    return _svc().get_category(block_type)


def get_block_yaml(block_type: str) -> Optional[dict]:
    _warn()
    return _svc().get_block_yaml(block_type)


def get_block_config_schema(block_type: str) -> dict[str, Any]:
    _warn()
    return _svc().get_block_config_schema(block_type)


def get_output_alias_map(block_type: str) -> dict[str, str]:
    _warn()
    return _svc().get_output_alias_map(block_type)


def resolve_output_handle(block_type: str, handle: str) -> str:
    _warn()
    return _svc().resolve_output_handle(block_type, handle)


def get_block_schema_defaults(block_type: str) -> dict[str, Any]:
    """Return a dict of {field_name: default_value} from block.yaml config section."""
    config_schema = get_block_config_schema(block_type)
    defaults: dict[str, Any] = {}
    for field_name, field_def in config_schema.items():
        if isinstance(field_def, dict) and "default" in field_def:
            defaults[field_name] = field_def["default"]
    return defaults


def get_block_version(block_type: str) -> str:
    """Return the version string from block.yaml, or '0.0.0' if absent."""
    block_yaml = get_block_yaml(block_type)
    if block_yaml:
        return str(block_yaml.get("version", "0.0.0"))
    return "0.0.0"


def get_file_path_fields(block_type: str) -> frozenset[str]:
    """Return config field names that have type ``file_path`` from block.yaml."""
    config_schema = get_block_config_schema(block_type)
    return frozenset(
        field_name
        for field_name, field_def in config_schema.items()
        if isinstance(field_def, dict) and field_def.get("type") == "file_path"
    )


class BlockRegistryService:
    """Object-oriented wrapper around the block registry module functions.

    Provides the interface expected by config_resolver and fingerprint modules.
    """

    def get_block_info(self, block_type: str) -> Optional[dict]:
        return get_block_info(block_type)

    def get_block_config_schema(self, block_type: str) -> dict[str, Any]:
        return get_block_config_schema(block_type)

    def get_block_schema_defaults(self, block_type: str) -> dict[str, Any]:
        return get_block_schema_defaults(block_type)

    def get_block_version(self, block_type: str) -> str:
        return get_block_version(block_type)

    def get_category(self, block_type: str) -> str:
        return get_category(block_type)

    def get_file_path_fields(self, block_type: str) -> frozenset[str]:
        return get_file_path_fields(block_type)


def reset() -> None:
    """Re-discover all blocks (called after installing/removing blocks)."""
    _warn()
    reset_global_registry()
