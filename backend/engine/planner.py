"""
GraphPlanner — the single entry point for pipeline validation and planning.

Takes raw pipeline nodes + edges, validates block types and connections,
detects loops, topologically sorts, resolves configs, and computes
fingerprints.  Produces a frozen ExecutionPlan consumed by the executor,
partial executor, and compiler.

No execution path may bypass the planner.
"""

from __future__ import annotations

import logging
from typing import Any

from .graph_utils import plan_execution_order, find_independent_subgraphs
from .config_resolver import resolve_configs
from .fingerprint import compute_fingerprints
from .planner_models import (
    ExecutionPlan,
    LoopBoundary,
    PlannerResult,
    ResolvedNode,
)

logger = logging.getLogger(__name__)

# These node types are visual-only and carry no block logic
_VISUAL_NODE_TYPES = {"groupNode", "stickyNote"}


class GraphPlanner:
    """Validates a pipeline graph and produces a frozen ExecutionPlan.

    Constructor Args:
        registry: A BlockRegistryService (or duck-type compatible object)
            that provides ``get()``, ``get_block_version()``,
            ``get_block_schema_defaults()``, ``validate_connection()``,
            and ``is_port_compatible()`` methods.
    """

    def __init__(self, registry):
        self._registry = registry

    def plan(
        self,
        nodes: list[dict],
        edges: list[dict],
        workspace_config: dict | None = None,
    ) -> PlannerResult:
        """Validate the pipeline and produce an ExecutionPlan.

        Steps (in order):
        1. Validate all block types exist in registry via registry.get()
        2. Validate all connections via registry.validate_connection()
        3. Call plan_execution_order() to detect loops and topologically sort
        4. Resolve configs with inheritance
        5. Compute cache fingerprints
        6. Check required input ports are connected
        7. Assemble frozen ExecutionPlan

        Returns PlannerResult with either a valid plan or accumulated errors.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not nodes:
            return PlannerResult(
                is_valid=True,
                errors=(),
                plan=ExecutionPlan(
                    execution_order=(),
                    nodes={},
                    loops=(),
                    independent_subgraphs=(),
                    plan_hash="empty",
                    warnings=(),
                ),
            )

        node_map = {n["id"]: n for n in nodes}
        node_ids = set(node_map.keys())

        # ── Step 1: Validate all block types exist ──
        for node in nodes:
            node_id = node["id"]
            if node.get("type") in _VISUAL_NODE_TYPES:
                continue
            node_data = node.get("data", {})
            block_type = node_data.get("type", "")
            if not block_type:
                continue
            schema = self._registry.get(block_type)
            if schema is None:
                errors.append(
                    f"Block type '{block_type}' (node '{node_id}') not found "
                    f"in registry. No run.py available."
                )

        # ── Step 2: Validate connections ──
        for edge in edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            if src not in node_ids:
                errors.append(f"Edge references non-existent source node '{src}'")
            if tgt not in node_ids:
                errors.append(f"Edge references non-existent target node '{tgt}'")

        # Port-type compatibility via registry
        for edge in edges:
            src_id = edge.get("source", "")
            tgt_id = edge.get("target", "")
            src_handle = edge.get("sourceHandle", "")
            tgt_handle = edge.get("targetHandle", "")
            src_node = node_map.get(src_id)
            tgt_node = node_map.get(tgt_id)
            if not src_node or not tgt_node:
                continue
            src_type = src_node.get("data", {}).get("type", "")
            tgt_type = tgt_node.get("data", {}).get("type", "")
            if not src_type or not tgt_type:
                continue
            try:
                result = self._registry.validate_connection(
                    src_type, src_handle, tgt_type, tgt_handle,
                )
                if not result.get("valid", True):
                    warnings.append(result.get("error", "Incompatible connection"))
            except Exception:
                pass  # Fail-open if registry doesn't support validation

        # ── Step 3: Detect loops and topological sort ──
        try:
            order_result = plan_execution_order(nodes, edges)
        except ValueError as exc:
            errors.append(str(exc))
            return PlannerResult(
                is_valid=False,
                errors=tuple(errors),
                plan=None,
            )

        if order_result.illegal_cycles:
            for cycle in order_result.illegal_cycles:
                errors.append(
                    f"Pipeline contains a cycle without a Loop Controller: "
                    f"nodes {list(cycle)}"
                )

        if errors:
            return PlannerResult(
                is_valid=False, errors=tuple(errors), plan=None,
            )

        exec_order = list(order_result.execution_order)

        # ── Step 4: Resolve configs ──
        resolved = resolve_configs(
            nodes, edges, exec_order,
            workspace_config=workspace_config,
            registry=self._registry,
        )

        # ── Step 5: Compute fingerprints ──
        fingerprints = compute_fingerprints(
            nodes_resolved=resolved,
            exec_order=exec_order,
            edges=edges,
            registry=self._registry,
            nodes=nodes,
        )

        # ── Step 6: Check required input ports ──
        connected_inputs: dict[str, set[str]] = {n["id"]: set() for n in nodes}
        for edge in edges:
            tgt = edge.get("target", "")
            tgt_handle = edge.get("targetHandle", "")
            if tgt in connected_inputs and tgt_handle:
                connected_inputs[tgt].add(tgt_handle)

        for node in nodes:
            node_id = node["id"]
            if node.get("type") in _VISUAL_NODE_TYPES:
                continue
            block_type = node.get("data", {}).get("type", "")
            schema = self._registry.get(block_type) if block_type else None
            if schema is None:
                continue
            # schema is a BlockSchema or dict-like with 'inputs'
            inputs_list = getattr(schema, "inputs", None)
            if inputs_list is None:
                inputs_list = schema.get("inputs", []) if isinstance(schema, dict) else []
            for inp in inputs_list:
                port_id = inp.get("id", "") if isinstance(inp, dict) else getattr(inp, "id", "")
                required = inp.get("required", False) if isinstance(inp, dict) else getattr(inp, "required", False)
                if required and port_id not in connected_inputs.get(node_id, set()):
                    label = node.get("data", {}).get("label", node_id)
                    errors.append(
                        f"Required input port '{port_id}' on block "
                        f"'{label}' is not connected"
                    )

        if errors:
            return PlannerResult(
                is_valid=False, errors=tuple(errors), plan=None,
            )

        # ── Step 7: Assemble ExecutionPlan ──
        # Build loop membership lookup
        loop_body_set: set[str] = set()
        loop_membership: dict[str, str] = {}
        for lb in order_result.loops:
            loop_membership[lb.controller_node_id] = lb.controller_node_id
            loop_body_set.update(lb.body_node_ids)
            for body_id in lb.body_node_ids:
                loop_membership[body_id] = lb.controller_node_id

        # Independent subgraphs
        subgraphs = find_independent_subgraphs(nodes, edges)

        # Build ResolvedNodes
        planned_nodes: dict[str, ResolvedNode] = {}
        for node_id in exec_order:
            node = node_map.get(node_id)
            if not node or node.get("type") in _VISUAL_NODE_TYPES:
                continue

            node_data = node.get("data", {})
            block_type = node_data.get("type", "")
            block_version = self._registry.get_block_version(block_type) if block_type else "0.0.0"

            resolved_config, config_sources = resolved.get(
                node_id, ({}, {}),
            )

            in_loop = node_id in loop_body_set or node_id in loop_membership
            loop_id = loop_membership.get(node_id)

            planned_nodes[node_id] = ResolvedNode(
                node_id=node_id,
                block_type=block_type,
                block_version=block_version,
                resolved_config=resolved_config,
                config_sources=config_sources,
                cache_fingerprint=fingerprints.get(node_id, ""),
                cache_eligible=not in_loop,
                in_loop=in_loop,
                loop_id=loop_id,
            )

        # Compute plan hash
        import hashlib
        import json
        hasher = hashlib.sha256()
        for nid in exec_order:
            rn = planned_nodes.get(nid)
            if rn is None:
                continue
            hasher.update(nid.encode())
            hasher.update(rn.block_type.encode())
            hasher.update(rn.block_version.encode())
            hasher.update(rn.cache_fingerprint.encode())
        plan_hash = hasher.hexdigest()[:16]

        plan = ExecutionPlan(
            execution_order=tuple(exec_order),
            nodes=planned_nodes,
            loops=order_result.loops,
            independent_subgraphs=tuple(tuple(sg) for sg in subgraphs),
            plan_hash=plan_hash,
            warnings=tuple(warnings),
        )

        return PlannerResult(
            is_valid=True,
            errors=(),
            plan=plan,
        )
