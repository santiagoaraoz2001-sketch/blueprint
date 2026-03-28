"""
Cache Fingerprints — deterministic Merkle-chain hashes for pipeline nodes.

For each node in topological order, the fingerprint is computed as:

    SHA-256(block_type | block_version | json(resolved_config) | sorted(upstream_fingerprints))

This creates a Merkle chain: any upstream change (config, version, or
structure) invalidates all downstream fingerprints. Two runs with identical
inputs are guaranteed to produce the same fingerprints.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .block_registry import BlockRegistryService


def _extract_block_types(nodes: list[dict]) -> dict[str, str]:
    """Build a node_id -> block_type mapping from pipeline node definitions."""
    block_types: dict[str, str] = {}
    for node in nodes:
        node_id = node.get("id", "")
        if node.get("type") == "groupNode":
            continue
        block_type = node.get("data", {}).get("type", "")
        if node_id and block_type:
            block_types[node_id] = block_type
    return block_types


def compute_fingerprints(
    nodes_resolved: dict[str, tuple[dict, dict]],
    exec_order: list[str],
    edges: list[dict],
    registry: BlockRegistryService,
    nodes: list[dict],
) -> dict[str, str]:
    """Compute deterministic cache fingerprints for every resolved node.

    Args:
        nodes_resolved: Output of ``resolve_configs`` — mapping of
            node_id -> (resolved_config, config_sources).
        exec_order: Topologically sorted node IDs.
        edges: Pipeline edge definitions.
        registry: Block registry service for looking up block versions.
        nodes: Pipeline node definitions (used to extract block types).

    Returns:
        Dict of {node_id: fingerprint_hex} for every node in nodes_resolved.
    """
    node_block_types = _extract_block_types(nodes)

    # Build adjacency: for each node, which nodes feed INTO it?
    incoming: dict[str, list[str]] = {nid: [] for nid in exec_order}
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if tgt in incoming and src in incoming:
            incoming[tgt].append(src)

    fingerprints: dict[str, str] = {}

    for node_id in exec_order:
        if node_id not in nodes_resolved:
            continue

        resolved_config, _config_sources = nodes_resolved[node_id]
        block_type = node_block_types.get(node_id, "unknown")
        block_version = registry.get_block_version(block_type)

        # Collect fingerprints of all upstream nodes
        upstream_fps: list[str] = []
        for parent_id in incoming.get(node_id, []):
            if parent_id in fingerprints:
                upstream_fps.append(fingerprints[parent_id])

        # Build the hash input: block_type | block_version | config_json | upstream_chain
        config_json = json.dumps(resolved_config, sort_keys=True, default=str)
        upstream_chain = ":".join(sorted(upstream_fps))

        hash_input = (
            f"{block_type}|{block_version}|{config_json}|{upstream_chain}"
        )

        fingerprints[node_id] = hashlib.sha256(hash_input.encode()).hexdigest()

    return fingerprints
