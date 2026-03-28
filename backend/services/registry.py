"""BlockRegistryService — single authoritative registry for all block discovery and port compatibility."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from backend.models.block_schema import (
    VALID_DATA_TYPES,
    VALID_RULE_OPERATORS,
    BlockSchema,
    ConfigField,
    ConfigValidationRule,
    PortSchema,
)

logger = logging.getLogger("blueprint.registry")

# Resolve once — lives next to project root
_PORT_COMPAT_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "PORT_COMPATIBILITY.yaml"


class BlockRegistryService:
    """Discovers, validates, and serves block metadata.

    One instance is created at startup and stored on ``app.state.registry``.
    """

    def __init__(self) -> None:
        self._blocks: dict[str, BlockSchema] = {}
        self._version: int = 0
        # Lazy-loaded from docs/PORT_COMPATIBILITY.yaml
        self._compat_matrix: dict[str, set[str]] | None = None
        self._compat_aliases: dict[str, str] | None = None

    # ── Discovery ─────────────────────────────────────────────────

    def discover_all(self, paths: list[Path]) -> None:
        """Scan *paths* for block.yaml files and populate the registry.

        Each path is expected to contain ``<category>/<block_type>/block.yaml``.
        Invalid blocks are kept with ``maturity='broken'`` so they appear in
        health reports rather than being silently dropped.
        """
        self._blocks.clear()
        for base in paths:
            if not base.exists():
                logger.debug("Block path does not exist, skipping: %s", base)
                continue
            source_type = "builtin" if "blocks" in base.parts else "user"
            for category_dir in sorted(base.iterdir()):
                if not category_dir.is_dir() or category_dir.name.startswith((".", "_")):
                    continue
                for block_dir in sorted(category_dir.iterdir()):
                    if not block_dir.is_dir() or block_dir.name.startswith((".", "_")):
                        continue
                    yaml_path = block_dir / "block.yaml"
                    if not yaml_path.exists():
                        continue
                    try:
                        schema = self._parse_block_yaml(yaml_path, source_type)
                        issues = self._validate_schema(schema)
                        if issues:
                            logger.warning(
                                "Block %s has validation issues (marking broken): %s",
                                schema.block_type,
                                "; ".join(issues),
                            )
                            schema.maturity = "broken"
                        self._blocks[schema.block_type] = schema
                    except Exception as exc:
                        logger.error("Failed to parse %s: %s", yaml_path, exc)
        self._version += 1
        logger.info(
            "Registry v%d: discovered %d blocks (%d broken)",
            self._version,
            len(self._blocks),
            sum(1 for b in self._blocks.values() if b.maturity == "broken"),
        )

    # ── Parsing ───────────────────────────────────────────────────

    @staticmethod
    def _parse_block_yaml(yaml_path: Path, source_type: str = "builtin") -> BlockSchema:
        with open(yaml_path, "r") as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}

        def _parse_port(p: dict) -> PortSchema:
            return PortSchema(
                id=p.get("id", ""),
                label=p.get("label", p.get("id", "")),
                data_type=p.get("data_type", "any"),
                required=p.get("required", False),
                default=p.get("default"),
                aliases=p.get("aliases", []),
                description=p.get("description", ""),
                position=p.get("position"),
            )

        def _parse_config(raw_config: dict[str, Any]) -> list[ConfigField]:
            fields: list[ConfigField] = []
            for key, val in raw_config.items():
                if not isinstance(val, dict):
                    continue
                fields.append(ConfigField(
                    key=key,
                    label=val.get("label", key),
                    type=val.get("type", "string"),
                    default=val.get("default"),
                    required=val.get("mandatory", False),
                    options=val.get("options", []),
                    min=val.get("min"),
                    max=val.get("max"),
                    description=val.get("description", ""),
                    propagate=val.get("propagate", False),
                    section=val.get("section", ""),
                    depends_on=val.get("depends_on"),
                    path_mode=val.get("path_mode"),
                    file_extensions=val.get("file_extensions", []),
                ))
            return fields

        inputs = [_parse_port(p) for p in raw.get("inputs", [])]
        outputs = [_parse_port(p) for p in raw.get("outputs", [])]
        side_inputs = [_parse_port(p) for p in raw.get("side_inputs", [])]
        config = _parse_config(raw.get("config", {}))

        # Parse declarative cross-field validation rules
        config_validation: list[ConfigValidationRule] = []
        for rule_raw in raw.get("config_validation", []):
            if not isinstance(rule_raw, dict):
                continue
            op = rule_raw.get("op", "")
            if op not in VALID_RULE_OPERATORS:
                logger.warning("Block %s: skipping rule with unknown op %r", yaml_path, op)
                continue
            try:
                config_validation.append(ConfigValidationRule(**rule_raw))
            except Exception as exc:
                logger.warning("Block %s: invalid validation rule: %s", yaml_path, exc)

        version_str = str(raw.get("version", "0.1.0"))
        maturity = raw.get("maturity", "stable")

        return BlockSchema(
            block_type=raw.get("type", yaml_path.parent.name),
            category=raw.get("category", yaml_path.parent.parent.name),
            label=raw.get("name", raw.get("type", yaml_path.parent.name)),
            description=raw.get("description", ""),
            version=version_str,
            inputs=inputs,
            outputs=outputs,
            config=config,
            config_validation=config_validation,
            side_inputs=side_inputs,
            source_type=source_type,
            source_path=str(yaml_path.parent),
            exportable=raw.get("exportable", True),
            maturity=maturity,
            tags=raw.get("tags", []),
            aliases=raw.get("aliases", []),
            icon=raw.get("icon", ""),
            accent=raw.get("accent", ""),
            deprecated=raw.get("deprecated", False),
        )

    @staticmethod
    def _validate_schema(schema: BlockSchema) -> list[str]:
        """Return a list of human-readable issues. Empty list means valid."""
        issues: list[str] = []

        # Must have at least one port (input or output)
        if not schema.inputs and not schema.outputs:
            issues.append("Block has no inputs or outputs")

        # Validate data_types on all ports
        for port in [*schema.inputs, *schema.outputs, *schema.side_inputs]:
            if port.data_type not in VALID_DATA_TYPES:
                issues.append(f"Port '{port.id}' has unknown data_type '{port.data_type}'")

        # required + default is contradictory (warning, not fatal)
        for port in schema.inputs:
            if port.required and port.default is not None:
                issues.append(f"Port '{port.id}' is required but also has a default")

        return issues

    # ── Lookups ───────────────────────────────────────────────────

    def get(self, block_type: str) -> BlockSchema | None:
        return self._blocks.get(block_type)

    def list_all(self, category: str | None = None) -> list[BlockSchema]:
        if category is None:
            return list(self._blocks.values())
        return [b for b in self._blocks.values() if b.category == category]

    def get_health(self) -> dict[str, Any]:
        total = len(self._blocks)
        broken = [b.block_type for b in self._blocks.values() if b.maturity == "broken"]
        return {
            "total": total,
            "valid": total - len(broken),
            "broken": len(broken),
            "broken_blocks": broken,
            "version": self._version,
        }

    def get_version(self) -> int:
        return self._version

    # ── Port Compatibility ────────────────────────────────────────

    def _load_compat(self) -> None:
        """Lazy-load and cache PORT_COMPATIBILITY.yaml."""
        if self._compat_matrix is not None:
            return
        try:
            with open(_PORT_COMPAT_PATH, "r") as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.error("PORT_COMPATIBILITY.yaml not found at %s", _PORT_COMPAT_PATH)
            self._compat_matrix = {}
            self._compat_aliases = {}
            return

        self._compat_aliases = data.get("aliases", {})
        raw_matrix = data.get("compatibility_matrix", {})
        self._compat_matrix = {k: set(v) for k, v in raw_matrix.items()}

    def _resolve_alias(self, data_type: str) -> str:
        self._load_compat()
        assert self._compat_aliases is not None
        return self._compat_aliases.get(data_type, data_type)

    def validate_connection(
        self,
        src_type: str,
        src_port_id: str,
        dst_type: str,
        dst_port_id: str,
    ) -> dict[str, Any]:
        """Check whether a connection between two block ports is valid.

        Returns ``{"valid": True}`` or ``{"valid": False, "error": "..."}``
        """
        self._load_compat()
        assert self._compat_matrix is not None

        src_block = self.get(src_type)
        if src_block is None:
            return {"valid": False, "error": f"Unknown source block type: {src_type}"}

        dst_block = self.get(dst_type)
        if dst_block is None:
            return {"valid": False, "error": f"Unknown destination block type: {dst_type}"}

        # Find ports
        src_port = next((p for p in src_block.outputs if p.id == src_port_id), None)
        if src_port is None:
            return {"valid": False, "error": f"Source port '{src_port_id}' not found on block '{src_type}'"}

        dst_port = next((p for p in [*dst_block.inputs, *dst_block.side_inputs] if p.id == dst_port_id), None)
        if dst_port is None:
            return {"valid": False, "error": f"Destination port '{dst_port_id}' not found on block '{dst_type}'"}

        # Resolve aliases and check compatibility
        src_dt = self._resolve_alias(src_port.data_type)
        dst_dt = self._resolve_alias(dst_port.data_type)

        allowed = self._compat_matrix.get(src_dt)
        if allowed is None:
            return {"valid": False, "error": f"Unknown source data type: {src_dt}"}

        if dst_dt in allowed:
            return {"valid": True, "error": None}

        return {
            "valid": False,
            "error": f"Incompatible: {src_dt} (port '{src_port_id}') cannot connect to {dst_dt} (port '{dst_port_id}')",
        }

    def is_port_compatible(self, source_type: str, target_type: str) -> bool:
        """Lightweight type-only compatibility check (no block lookup needed)."""
        self._load_compat()
        assert self._compat_matrix is not None
        src = self._resolve_alias(source_type)
        tgt = self._resolve_alias(target_type)
        allowed = self._compat_matrix.get(src, set())
        return tgt in allowed

    # ── Compatibility API (matches old block_registry.py) ─────────

    def is_known_block(self, block_type: str) -> bool:
        return block_type in self._blocks

    def get_block_types(self) -> set[str]:
        return set(self._blocks.keys())

    def get_block_info(self, block_type: str) -> dict[str, Any] | None:
        """Return a dict matching the old block_registry.get_block_info() shape."""
        schema = self._blocks.get(block_type)
        if schema is None:
            return None
        return {
            "type": schema.block_type,
            "category": schema.category,
            "path": schema.source_path,
            "has_run": True,
        }

    def get_category(self, block_type: str) -> str:
        schema = self._blocks.get(block_type)
        return schema.category if schema else "unknown"

    def get_block_yaml(self, block_type: str) -> dict[str, Any] | None:
        """Load the raw YAML dict for a block. Uses the on-disk file."""
        schema = self._blocks.get(block_type)
        if schema is None:
            return None
        yaml_path = Path(schema.source_path) / "block.yaml"
        if not yaml_path.exists():
            return None
        try:
            with open(yaml_path, "r") as f:
                return yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError):
            return None

    def get_block_config_schema(self, block_type: str) -> dict[str, Any]:
        """Return the raw 'config' section from a block's block.yaml."""
        block_yaml = self.get_block_yaml(block_type)
        if not block_yaml:
            return {}
        return block_yaml.get("config", {})

    def get_output_alias_map(self, block_type: str) -> dict[str, str]:
        """Build {old_id: canonical_id} for output ports with aliases."""
        schema = self._blocks.get(block_type)
        if schema is None:
            return {}
        alias_map: dict[str, str] = {}
        for output in schema.outputs:
            for alias in output.aliases:
                alias_map[alias] = output.id
        return alias_map

    def resolve_output_handle(self, block_type: str, handle: str) -> str:
        """Resolve an output handle ID, mapping old aliases to canonical IDs."""
        alias_map = self.get_output_alias_map(block_type)
        return alias_map.get(handle, handle)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Module-level singleton — the canonical way to access the registry
#  from code that doesn't go through FastAPI dependency injection
#  (engine modules, scripts, tests).
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_instance: BlockRegistryService | None = None


def set_global_registry(service: BlockRegistryService) -> None:
    """Install the app-level singleton. Called once by ``main.py`` at startup."""
    global _instance
    _instance = service


def get_global_registry() -> BlockRegistryService:
    """Return the module-level singleton, lazy-initializing if needed.

    Engine code and scripts call this when they don't have access to the
    FastAPI ``Request``.  On first access (before ``main.py`` sets the
    singleton), a fresh service is created and discovery runs against all
    configured block directories.
    """
    global _instance
    if _instance is None:
        from backend.config import BLOCKS_DIR, BUILTIN_BLOCKS_DIR, CUSTOM_BLOCKS_DIR
        _instance = BlockRegistryService()
        _instance.discover_all([BUILTIN_BLOCKS_DIR, BLOCKS_DIR, CUSTOM_BLOCKS_DIR])
        logger.info("Lazy-initialized global registry (%d blocks)", len(_instance.list_all()))
    return _instance


def reset_global_registry() -> None:
    """Clear and re-discover blocks. Called after installing/removing blocks."""
    global _instance
    if _instance is not None:
        from backend.config import BLOCKS_DIR, BUILTIN_BLOCKS_DIR, CUSTOM_BLOCKS_DIR
        _instance.discover_all([BUILTIN_BLOCKS_DIR, BLOCKS_DIR, CUSTOM_BLOCKS_DIR])
    else:
        get_global_registry()
