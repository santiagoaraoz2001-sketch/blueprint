"""
Config Resolver — propagates inheritable config keys through the pipeline DAG.

Called by the executor AFTER topological sort, BEFORE block execution.

Precedence (highest to lowest):
1. User-set values on the specific node
2. Workspace config (matching key names in the block's schema)
3. Inherited values from upstream nodes connected via edges
4. Block schema defaults from the registry

Inheritance rules:
- Keys marked as global propagation keys always flow downstream along edges.
- Category-specific keys only apply to blocks matching the category, but the
  value still flows through intermediate blocks of any category.
- Downstream blocks inherit the FIRST upstream value they encounter (topo order).
- If a downstream block has a user-set value, that takes precedence over all.

The resolver returns a dict of {node_id: (resolved_config, config_sources)}.
config_sources maps each key to its origin:
  'block_default' | 'workspace' | 'inherited:{upstream_node_id}' | 'user'
"""

from __future__ import annotations

import logging
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .block_registry import BlockRegistryService

logger = logging.getLogger(__name__)


def _get_workspace_settings() -> tuple[Optional[str], bool]:
    """Load workspace settings from DB.

    Returns (root_path, auto_fill_paths) or (None, False).
    """
    try:
        from ..database import SessionLocal
        from ..models.workspace import WorkspaceSettings
        session = SessionLocal()
        try:
            ws = session.query(WorkspaceSettings).filter_by(id="default").first()
            if ws and ws.root_path and ws.auto_fill_paths:
                return ws.root_path, True
            return None, False
        finally:
            session.close()
    except Exception:
        return None, False


# Keys that are ALWAYS propagated regardless of block.yaml declarations.
# These are the 5 known conflict keys from the config audit.
GLOBAL_PROPAGATION_KEYS = {
    "text_column",
    "seed",
    "trust_remote_code",
    "system_prompt",
    "prompt_template",
}

# Keys that propagate WITHIN specific categories only.
CATEGORY_PROPAGATION_KEYS: dict[str, set[str]] = {
    "inference": {"system_prompt", "temperature", "max_tokens", "top_p"},
    "agents": {"system_prompt", "temperature", "max_tokens", "top_p"},
    "evaluation": {"decimal_precision", "max_samples"},
    "training": {"training_format", "prompt_template", "max_seq_length"},
}

# Union of all category-specific keys — used when building propagation pools.
_ALL_CATEGORY_KEYS: set[str] = set()
for _keys in CATEGORY_PROPAGATION_KEYS.values():
    _ALL_CATEGORY_KEYS.update(_keys)


def _get_propagation_keys(category: str) -> set[str]:
    """Get the set of keys that should propagate for a given block category."""
    keys = set(GLOBAL_PROPAGATION_KEYS)
    keys.update(CATEGORY_PROPAGATION_KEYS.get(category, set()))
    return keys


def _get_all_propagation_keys() -> set[str]:
    """Get the full set of keys that may propagate (global + all categories)."""
    keys = set(GLOBAL_PROPAGATION_KEYS)
    keys.update(_ALL_CATEGORY_KEYS)
    return keys


def _is_user_override(key: str, value: Any, schema_default: Any) -> bool:
    """Determine if a config value was explicitly set by the user.

    A value is considered a user override if:
    - It differs from the schema default
    - The schema has no default and the value is non-empty
    """
    if schema_default is None:
        return value is not None and value != ""
    return value != schema_default


def resolve_configs(
    nodes: list[dict],
    edges: list[dict],
    exec_order: list[str],
    workspace_config: dict | None,
    registry: BlockRegistryService,
) -> dict[str, tuple[dict, dict]]:
    """Resolve config inheritance for all nodes in the pipeline.

    Args:
        nodes: Pipeline node definitions (from pipeline JSON).
        edges: Pipeline edge definitions.
        exec_order: Topologically sorted node IDs.
        workspace_config: Workspace-level config dict (key->value). When a key
            matches a block's schema field, it is applied to EVERY matching
            block (not just the first consumer). ``None`` means no workspace config.
        registry: Block registry service for loading schema defaults and versions.

    Returns:
        Dict of {node_id: (resolved_config, config_sources)}.
        resolved_config is the final config dict for the block.
        config_sources maps each resolved key to its origin string:
          'block_default' | 'workspace' | 'inherited:<upstream_node_id>' | 'user'
    """
    workspace_config = workspace_config or {}
    node_map = {n["id"]: n for n in nodes}

    # Build adjacency: for each node, which nodes feed INTO it?
    incoming: dict[str, list[str]] = {nid: [] for nid in exec_order}
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if tgt in incoming and src in node_map:
            incoming[tgt].append(src)

    all_prop_keys = _get_all_propagation_keys()

    # Phase 1: Load schema defaults and determine categories
    schema_defaults: dict[str, dict[str, Any]] = {}
    categories: dict[str, str] = {}
    block_types: dict[str, str] = {}

    for node_id in exec_order:
        node = node_map.get(node_id)
        if not node:
            continue
        if node.get("type") == "groupNode":
            continue

        node_data = node.get("data", {})
        block_type = node_data.get("type", "")
        category = node_data.get("category", "")
        block_types[node_id] = block_type
        categories[node_id] = category

        if block_type:
            try:
                schema_defaults[node_id] = dict(
                    registry.get_block_schema_defaults(block_type)
                )
            except Exception as exc:
                logger.warning(
                    "Could not load schema defaults for %r (node %s): %s",
                    block_type, node_id, exc,
                )
                schema_defaults[node_id] = {}
        else:
            schema_defaults[node_id] = {}

    # Phase 2: Walk DAG in topo order, resolving configs with full precedence
    resolved: dict[str, tuple[dict, dict]] = {}
    propagation_pool: dict[str, dict[str, Any]] = {}

    for node_id in exec_order:
        node = node_map.get(node_id)
        if not node:
            continue
        if node.get("type") == "groupNode":
            continue

        node_data = node.get("data", {})
        user_config = dict(node_data.get("config", {}))
        category = categories.get(node_id, "")
        defaults = schema_defaults.get(node_id, {})
        prop_keys = _get_propagation_keys(category)

        # Collect propagated values from all upstream nodes
        upstream_values: dict[str, Any] = {}
        upstream_sources: dict[str, str] = {}
        for parent_id in incoming.get(node_id, []):
            parent_pool = propagation_pool.get(parent_id, {})
            for key, value in parent_pool.items():
                if key not in upstream_values:  # First upstream wins
                    upstream_values[key] = value
                    upstream_sources[key] = parent_id

        # Build resolved config and sources with precedence:
        # user > workspace > inherited > block_default
        resolved_config: dict[str, Any] = {}
        config_sources: dict[str, str] = {}

        # Start with all keys from schema defaults
        all_keys = set(defaults.keys())
        all_keys.update(user_config.keys())
        all_keys.update(
            k for k in workspace_config if k in defaults
        )
        all_keys.update(
            k for k in upstream_values if k in defaults and k in prop_keys
        )

        for key in all_keys:
            has_user_value = key in user_config
            user_value = user_config.get(key)
            has_default = key in defaults
            default_value = defaults.get(key)

            # Check if user explicitly set this value (differs from default)
            if has_user_value and (
                not has_default or _is_user_override(key, user_value, default_value)
            ):
                resolved_config[key] = user_value
                config_sources[key] = "user"
            elif key in workspace_config and has_default:
                # Workspace config applies to every block that has this key in schema
                resolved_config[key] = workspace_config[key]
                config_sources[key] = "workspace"
            elif key in upstream_values and has_default and key in prop_keys:
                # Inherited from upstream
                resolved_config[key] = upstream_values[key]
                config_sources[key] = f"inherited:{upstream_sources[key]}"
            elif has_default:
                resolved_config[key] = default_value
                config_sources[key] = "block_default"
            elif has_user_value:
                # User set a key not in schema — pass through
                resolved_config[key] = user_value
                config_sources[key] = "user"

        resolved[node_id] = (resolved_config, config_sources)

        # Build propagation pool for downstream nodes.
        # Pool starts from upstream values (so values flow through any category),
        # then merges in this node's own propagatable values.
        pool = dict(upstream_values)
        pool_keys = all_prop_keys
        for key in pool_keys:
            val = resolved_config.get(key)
            if val is not None and val != "":
                pool[key] = val
        propagation_pool[node_id] = pool

    return resolved


def inject_workspace_file_paths(
    resolved: dict[str, tuple[dict, dict]],
    nodes: list[dict],
    registry: BlockRegistryService,
) -> None:
    """Replace schema-default file_path values with workspace absolute paths.

    This is a **post-resolution** phase that runs AFTER ``resolve_configs``.
    It only touches values whose source is ``'block_default'`` — user overrides,
    workspace config, and inherited values are never replaced.

    Mutates ``resolved`` in place. If the workspace is not configured or
    auto_fill_paths is disabled, this is a no-op.

    Args:
        resolved: Output of ``resolve_configs`` — mutated in place.
        nodes: Pipeline node definitions (for extracting block types/categories).
        registry: Block registry service for looking up file_path fields.
    """
    root_path, auto_fill = _get_workspace_settings()
    if not root_path or not auto_fill:
        return

    try:
        from ..services.workspace_manager import WorkspaceManager
    except ImportError:
        logger.warning("WorkspaceManager not available; skipping file_path auto-fill")
        return

    manager = WorkspaceManager(root_path)
    node_map = {n["id"]: n for n in nodes}

    for node_id, (resolved_config, config_sources) in resolved.items():
        node = node_map.get(node_id)
        if not node:
            continue

        node_data = node.get("data", {})
        block_type = node_data.get("type", "")
        category = node_data.get("category", "")

        if not block_type:
            continue

        try:
            file_path_fields = registry.get_file_path_fields(block_type)
        except Exception:
            continue

        if not file_path_fields:
            continue

        for field_name in file_path_fields:
            # Only auto-fill if the current value came from schema defaults
            if config_sources.get(field_name) != "block_default":
                continue

            workspace_path = manager.resolve_output_path(
                block_type, field_name, category,
            )
            if workspace_path:
                resolved_config[field_name] = workspace_path
                config_sources[field_name] = "workspace_auto_fill"
                logger.debug(
                    "Workspace auto-fill: %s.%s → %s",
                    block_type, field_name, workspace_path,
                )
