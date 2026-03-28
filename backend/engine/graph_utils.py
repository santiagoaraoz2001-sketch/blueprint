"""
Graph utilities for kill-switch validation.

Provides safety checks that block dangerous operations on pipelines
containing loops, custom code blocks, or stale caches.  Referenced by
the execution contract (V1, §§ 3-5).
"""

import collections
import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from ..models.run import Run
from .executor import _find_block_module
from .schema_validator import load_block_schema
from .block_registry import get_block_yaml

logger = logging.getLogger("blueprint.graph_utils")


# ---------------------------------------------------------------------------
# 1.  contains_loop_or_cycle
# ---------------------------------------------------------------------------

def contains_loop_or_cycle(nodes: list[dict], edges: list[dict]) -> bool:
    """Return True if the pipeline contains a loop_controller block or a cycle.

    Checks two things:
      (a) any node whose data.block_type == 'loop_controller'
      (b) standard DFS-based cycle detection on the adjacency list
    """
    # (a) Explicit loop_controller blocks
    for node in nodes:
        data = node.get("data", {})
        block_type = data.get("type", "")
        if block_type == "loop_controller":
            return True

    # (b) Cycle detection via Kahn's algorithm (nodes remaining = cyclic)
    node_ids = {n["id"] for n in nodes}
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
    adj: dict[str, list[str]] = {nid: [] for nid in node_ids}

    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in adj and tgt in in_degree:
            adj[src].append(tgt)
            in_degree[tgt] += 1

    queue = collections.deque(nid for nid, deg in in_degree.items() if deg == 0)
    visited = 0
    while queue:
        nid = queue.popleft()
        visited += 1
        for neighbor in adj.get(nid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return visited < len(node_ids)


# ---------------------------------------------------------------------------
# 2.  validate_exportable
# ---------------------------------------------------------------------------

# Block types that are inherently not exportable
_NON_EXPORTABLE_BLOCK_TYPES = {"python_runner"}


def validate_exportable(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Return a list of human-readable reasons the pipeline cannot be exported.

    Checks for:
      - loop_controller blocks or cycles (loops change semantics in exported code)
      - python_runner / custom_code blocks (arbitrary user code cannot be safely
        inlined into a standalone script)
      - blocks with exportable=False in their block.yaml

    Uses the cached block registry (``get_block_yaml``) for schema lookups
    instead of per-node filesystem walks, so cost is O(n) dict lookups rather
    than O(n * categories) directory scans.
    """
    reasons: list[str] = []

    # Check loops / cycles
    if contains_loop_or_cycle(nodes, edges):
        reasons.append(
            "Pipeline contains loops or cycles. "
            "The compiler cannot faithfully reproduce loop semantics in a standalone script."
        )

    # Per-node checks
    for node in nodes:
        # Skip visual-only nodes
        if node.get("type") in ("groupNode", "stickyNote"):
            continue

        data = node.get("data", {})
        block_type = data.get("type", "")
        label = data.get("label", block_type)

        # Check non-exportable block types
        if block_type in _NON_EXPORTABLE_BLOCK_TYPES:
            reasons.append(
                f"Block '{label}' is a {block_type} block which cannot be exported."
            )

        # Check block.yaml exportable flag via cached registry
        schema = get_block_yaml(block_type)
        if schema and schema.get("exportable") is False:
            reasons.append(
                f"Block '{label}' ({block_type}) is marked as non-exportable."
            )

    return reasons


# ---------------------------------------------------------------------------
# 3.  is_cache_valid
# ---------------------------------------------------------------------------

def is_cache_valid(
    node_id: str,
    pipeline_id: str,
    current_config: dict[str, Any],
    db: Session,
) -> bool:
    """Check whether cached outputs from the most recent run can be reused.

    Validates three conditions:
      1. The previous run completed successfully (status == 'complete').
      2. The node's config in the previous run matches *current_config*
         (JSON comparison with sorted keys).
      3. The block version in the current block.yaml matches the version
         recorded at run time (if available).

    Returns True only if all conditions are met.
    """
    # Find the most recent completed run for this pipeline
    last_run = (
        db.query(Run)
        .filter(Run.pipeline_id == pipeline_id)
        .order_by(Run.started_at.desc())
        .first()
    )

    if not last_run:
        logger.info("Cache invalid for %s: no previous run found", node_id)
        return False

    # Condition 1: previous run completed
    if last_run.status != "complete":
        logger.info(
            "Cache invalid for %s: last run status is '%s', not 'complete'",
            node_id,
            last_run.status,
        )
        return False

    # Condition 2: config matches
    config_snapshot = last_run.config_snapshot or {}
    snapshot_nodes = config_snapshot.get("nodes", [])
    snapshot_node_map = {n["id"]: n for n in snapshot_nodes}
    snapshot_node = snapshot_node_map.get(node_id)

    if not snapshot_node:
        logger.info("Cache invalid for %s: node not found in snapshot", node_id)
        return False

    snapshot_config = snapshot_node.get("data", {}).get("config", {})

    # Canonical JSON comparison with sorted keys
    def _canonical(obj: Any) -> str:
        return json.dumps(obj, sort_keys=True, default=str)

    if _canonical(snapshot_config) != _canonical(current_config):
        logger.info("Cache invalid for %s: config changed", node_id)
        return False

    # Condition 3: block version matches
    snapshot_block_type = snapshot_node.get("data", {}).get("type", "")
    block_dir = _find_block_module(snapshot_block_type)
    if block_dir:
        schema = load_block_schema(block_dir)
        current_version = schema.get("version")
        # We store config_snapshot at run time — if a version field was
        # embedded we could compare; for now we compare the on-disk version
        # against itself (a future run that upgrades blocks will see a
        # mismatch when the saved snapshot config no longer matches).
        # This is a forward-looking guard: if the block.yaml version
        # changes between runs, the cache is stale.
        if current_version:
            # Check if a previous snapshot recorded the block version
            # We embed it during execution in config_snapshot's node data
            snapshot_version = snapshot_node.get("data", {}).get("block_version")
            if snapshot_version and snapshot_version != current_version:
                logger.info(
                    "Cache invalid for %s: block version changed (%s -> %s)",
                    node_id,
                    snapshot_version,
                    current_version,
                )
                return False

    return True
