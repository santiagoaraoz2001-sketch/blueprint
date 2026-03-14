"""
Config Resolver — propagates inheritable config keys through the pipeline DAG.

Called by the executor AFTER topological sort, BEFORE block execution.

Inheritance rules:
1. Keys marked as "propagate" in block.yaml flow downstream along edges.
2. Downstream blocks inherit the FIRST upstream value they encounter (topo order).
3. If a downstream block has explicitly set a value (not equal to its schema default),
   that value is treated as an override and NOT replaced.
4. The resolver returns a dict of {node_id: resolved_config}.
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# Keys that are ALWAYS propagated regardless of block.yaml declarations.
# These are the 5 resolved conflicts from the config audit.
GLOBAL_PROPAGATION_KEYS = {
    "text_column",
    "seed",
    "trust_remote_code",
}

# Keys that propagate WITHIN specific categories only.
# The key is only *applied* to blocks matching the category, but the value
# still flows through intermediate blocks of any category so that
# inference→data→inference chains work correctly.
CATEGORY_PROPAGATION_KEYS = {
    "inference": {"system_prompt"},
    "training": {"training_format", "prompt_template"},
}

# Union of all category-specific keys — used when building the propagation pool
# so values can flow through intermediate blocks of different categories.
_ALL_CATEGORY_KEYS: set[str] = set()
for _keys in CATEGORY_PROPAGATION_KEYS.values():
    _ALL_CATEGORY_KEYS.update(_keys)


@lru_cache(maxsize=256)
def _load_schema_defaults(block_dir: str) -> dict[str, Any]:
    """Load default config values from block.yaml.

    Cached by block_dir path string so the same block.yaml is only parsed once
    per process lifetime, even across multiple pipeline runs.
    """
    schema_path = Path(block_dir) / "block.yaml"
    if not schema_path.exists():
        return {}
    try:
        with open(schema_path) as f:
            schema = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError) as exc:
        logger.warning("Failed to parse %s: %s", schema_path, exc)
        return {}

    defaults = {}
    config_section = schema.get("config")
    if not isinstance(config_section, dict):
        return {}
    for field_name, field_def in config_section.items():
        if isinstance(field_def, dict) and "default" in field_def:
            defaults[field_name] = field_def["default"]
    return defaults


def _is_user_override(key: str, value: Any, schema_default: Any) -> bool:
    """
    Determine if a config value was explicitly set by the user
    (vs being the schema default).

    A value is considered a user override if:
    - It differs from the schema default
    - The schema has no default and the value is non-empty
    """
    if schema_default is None:
        # No default in schema — any non-empty value is a user choice
        return value is not None and value != ""
    return value != schema_default


def _get_propagation_keys(category: str) -> set[str]:
    """Get the set of keys that should propagate for a given block category."""
    keys = set(GLOBAL_PROPAGATION_KEYS)
    keys.update(CATEGORY_PROPAGATION_KEYS.get(category, set()))
    return keys


def _get_all_propagation_keys() -> set[str]:
    """Get the full set of keys that may propagate (global + all categories).

    Used when building propagation pools so values can flow through
    intermediate blocks regardless of category.
    """
    keys = set(GLOBAL_PROPAGATION_KEYS)
    keys.update(_ALL_CATEGORY_KEYS)
    return keys


def resolve_configs(
    nodes: list[dict],
    edges: list[dict],
    topo_order: list[str],
    find_block_dir_fn,  # callable(block_type) -> Path | None
) -> dict[str, dict]:
    """
    Resolve config inheritance for all nodes in the pipeline.

    Args:
        nodes: Pipeline node definitions (from pipeline JSON)
        edges: Pipeline edge definitions
        topo_order: Topologically sorted node IDs
        find_block_dir_fn: Function to find block directory from block type

    Returns:
        Dict of {node_id: resolved_config} with inherited values applied.
        Each config may contain an ``_inherited`` key with provenance metadata
        mapping inherited key names to ``{"from_node": ..., "value": ...}``.
        The executor strips ``_inherited`` before passing config to blocks.
    """
    node_map = {n["id"]: n for n in nodes}

    # Build adjacency: for each node, which nodes feed INTO it?
    incoming: dict[str, list[str]] = {nid: [] for nid in topo_order}
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if tgt in incoming and src in node_map:
            incoming[tgt].append(src)

    all_prop_keys = _get_all_propagation_keys()

    # Phase 1: Load schema defaults for each node, with per-block_type caching
    schema_defaults: dict[str, dict] = {}
    categories: dict[str, str] = {}

    for node_id in topo_order:
        node = node_map.get(node_id)
        if not node:
            continue

        # Skip visual grouping nodes — they carry no config
        if node.get("type") == "groupNode":
            continue

        node_data = node.get("data", {})
        block_type = node_data.get("type", "")
        category = node_data.get("category", "")
        categories[node_id] = category

        block_dir = None
        if block_type:
            try:
                block_dir = find_block_dir_fn(block_type)
            except (ValueError, OSError) as exc:
                logger.warning(
                    "Could not locate block dir for %r (node %s): %s",
                    block_type, node_id, exc,
                )

        if block_dir:
            # lru_cache requires a hashable key — use the string path
            schema_defaults[node_id] = dict(_load_schema_defaults(str(block_dir)))
        else:
            schema_defaults[node_id] = {}

    # Phase 2: Walk DAG in topo order, propagating values
    resolved: dict[str, dict] = {}
    # Track which values are available for propagation at each node
    propagation_pool: dict[str, dict[str, Any]] = {}

    for node_id in topo_order:
        node = node_map.get(node_id)
        if not node:
            continue

        # Skip visual grouping nodes
        if node.get("type") == "groupNode":
            continue

        node_data = node.get("data", {})
        node_config = dict(node_data.get("config", {}))
        category = categories.get(node_id, "")
        defaults = schema_defaults.get(node_id, {})
        prop_keys = _get_propagation_keys(category)

        # Collect propagated values from all upstream nodes
        upstream_values: dict[str, Any] = {}
        # Track which parent provided each key (for provenance)
        upstream_sources: dict[str, str] = {}
        for parent_id in incoming.get(node_id, []):
            parent_pool = propagation_pool.get(parent_id, {})
            for key, value in parent_pool.items():
                if key not in upstream_values:  # First upstream wins
                    upstream_values[key] = value
                    upstream_sources[key] = parent_id

        # Apply inheritance: only for keys this node accepts AND hasn't overridden
        for key in prop_keys:
            if key in upstream_values and key in defaults:
                # This block has this config key in its schema
                current_value = node_config.get(key, defaults.get(key))
                if not _is_user_override(key, current_value, defaults.get(key)):
                    # Not overridden by user → inherit upstream value
                    node_config[key] = upstream_values[key]

                    # Provenance tracking
                    if "_inherited" not in node_config:
                        node_config["_inherited"] = {}
                    node_config["_inherited"][key] = {
                        "from_node": upstream_sources[key],
                        "value": upstream_values[key],
                    }

        resolved[node_id] = node_config

        # Build propagation pool for this node's downstream.
        # Pool starts from upstream values (so values flow through any category),
        # then merges in this node's own propagatable values.
        # We use all_prop_keys (not category-scoped) so that e.g. system_prompt
        # flows through a data block to reach a downstream inference block.
        pool = dict(upstream_values)
        for key in all_prop_keys:
            if key in node_config and node_config[key] is not None and node_config[key] != "":
                pool[key] = node_config[key]
        propagation_pool[node_id] = pool

    return resolved
