"""
Composite Block — a block that contains and executes a sub-pipeline.

A CompositeBlock wraps multiple child blocks into a single canvas node.
When executed, it runs its internal sub-pipeline using the same executor
logic (topological sort, validation, metrics).

Use cases:
- Multi-agent debate (3 LLM instances + voting logic)
- RAG pipeline (retrieve + rerank + generate)
- Train-and-evaluate (training block + eval block as one unit)
"""

import logging
import traceback
from pathlib import Path
from typing import Any, Callable

from ..block_sdk.context import CompositeBlockContext
from ..block_sdk.exceptions import BlockError
from .block_registry import resolve_output_handle
from .schema_validator import load_block_schema, validate_config

logger = logging.getLogger(__name__)

# Guard against infinite composite nesting
MAX_COMPOSITE_DEPTH = 5


def _topological_sort_sub(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Topological sort for sub-pipeline nodes.

    Raises BlockError if the sub-pipeline contains a cycle.
    """
    in_degree: dict[str, int] = {n["id"]: 0 for n in nodes}
    adj: dict[str, list[str]] = {n["id"]: [] for n in nodes}

    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in adj and tgt in in_degree:
            adj[src].append(tgt)
            in_degree[tgt] += 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    order = []

    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for neighbor in adj.get(nid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(nodes):
        visited = set(order)
        cycle_nodes = [n["id"] for n in nodes if n["id"] not in visited]
        raise BlockError(
            f"Composite sub-pipeline contains a cycle involving: {cycle_nodes}",
            recoverable=False,
        )

    return order


def execute_sub_pipeline(
    sub_definition: dict,
    run_dir: str,
    run_id: str,
    parent_node_id: str,
    parent_inputs: dict[str, Any],
    progress_cb: Callable | None,
    message_cb: Callable | None,
    metric_cb: Callable | None,
    find_block_fn: Callable,
    load_and_run_fn: Callable,
    resolve_secrets_fn: Callable,
    depth: int = 0,
) -> tuple[dict[str, Any], dict[str, dict]]:
    """Execute a composite block's sub-pipeline.

    Args:
        sub_definition: {"nodes": [...], "edges": [...]} from CompositeBlockContext.
        run_dir: Parent block's run directory (sub-blocks get subdirs within it).
        run_id: The parent pipeline's run ID.
        parent_node_id: The composite block's node ID (for prefixing metrics).
        parent_inputs: The parent block's inputs, injected into root child blocks.
        progress_cb: Progress callback from the parent executor.
        message_cb: Message callback from the parent executor.
        metric_cb: Metric callback from the parent executor.
        find_block_fn: Function to locate a block module by type.
        load_and_run_fn: Function to load and run a block.
        resolve_secrets_fn: Function to resolve $secret: references in config.
        depth: Current composite nesting depth (for recursion guard).

    Returns:
        (merged_outputs, merged_fingerprints) tuple.
        merged_outputs: keyed by "{child_id}.{output_name}", plus
            the last child's outputs without prefix for convenience.
        merged_fingerprints: keyed by "{parent_node_id}.{child_id}".
    """
    if depth >= MAX_COMPOSITE_DEPTH:
        raise BlockError(
            f"Composite nesting depth exceeded maximum of {MAX_COMPOSITE_DEPTH}. "
            "Check for recursive composite definitions.",
            recoverable=False,
        )

    nodes = sub_definition.get("nodes", [])
    edges = sub_definition.get("edges", [])

    if not nodes:
        return {}, {}

    order = _topological_sort_sub(nodes, edges)
    node_map = {n["id"]: n for n in nodes}
    child_outputs: dict[str, dict[str, Any]] = {}
    merged_outputs: dict[str, Any] = {}
    merged_fingerprints: dict[str, dict] = {}
    total_children = len(order)

    # Pre-compute which child blocks have no upstream edges (root nodes).
    # These receive the parent's inputs as a fallback.
    targets_with_edges = {e.get("target") for e in edges}

    logger.info(
        "Composite %s: executing %d child blocks (depth=%d)",
        parent_node_id, total_children, depth,
    )

    for child_idx, child_id in enumerate(order):
        child_node = node_map.get(child_id)
        if not child_node:
            continue

        child_data = child_node.get("data", {})
        child_type = child_data.get("type", "")
        child_config = dict(child_data.get("config", {}))

        # Gather inputs from upstream child edges
        child_inputs: dict[str, Any] = {}
        _multi_counts: dict[str, int] = {}
        for edge in edges:
            if edge.get("target") == child_id:
                src_id = edge.get("source", "")
                src_handle = edge.get("sourceHandle", "")
                tgt_handle = edge.get("targetHandle", "")
                # Resolve aliased output handle IDs from renamed ports
                if src_id in child_outputs and src_handle not in child_outputs[src_id]:
                    src_node = node_map.get(src_id)
                    if src_node:
                        src_type = src_node.get("data", {}).get("type", src_node.get("type", ""))
                        src_handle = resolve_output_handle(src_type, src_handle)
                if src_id in child_outputs and src_handle in child_outputs[src_id]:
                    value = child_outputs[src_id][src_handle]
                    _multi_counts[tgt_handle] = _multi_counts.get(tgt_handle, 0) + 1
                    if tgt_handle in child_inputs:
                        if not isinstance(child_inputs[tgt_handle], list) or _multi_counts[tgt_handle] == 2:
                            child_inputs[tgt_handle] = [child_inputs[tgt_handle], value]
                        else:
                            child_inputs[tgt_handle].append(value)
                    else:
                        child_inputs[tgt_handle] = value

        # Inject parent inputs into root child blocks (those without upstream edges)
        # as a fallback — child-wired inputs take priority.
        if child_id not in targets_with_edges and parent_inputs:
            for key, value in parent_inputs.items():
                if key not in child_inputs:
                    child_inputs[key] = value

        # Find block module
        block_dir = find_block_fn(child_type)
        if not block_dir:
            raise BlockError(
                f"Composite child block type '{child_type}' (id='{child_id}') not found. "
                f"Ensure the block is installed in blocks/*/.",
                recoverable=False,
            )

        # Sub-block run directory: {parent_run_dir}/sub_{child_id}
        child_run_dir = str(Path(run_dir) / f"sub_{child_id}")

        # Resolve $secret: references in child config
        try:
            child_config = resolve_secrets_fn(child_config)
        except Exception as e:
            raise BlockError(
                f"Composite child '{child_id}' ({child_type}): secret resolution failed: {e}",
                recoverable=False,
            ) from e

        # Wrap callbacks to prefix child info for traceability
        def child_message_cb(msg, explicit_severity=None, _cid=child_id):
            if message_cb:
                message_cb(f"[{_cid}] {msg}", explicit_severity)

        def child_metric_cb(name, value, step, _cid=child_id):
            if metric_cb:
                metric_cb(f"composite_child.{_cid}.{name}", value, step)

        def child_progress_cb(current, total, _cidx=child_idx):
            if progress_cb:
                child_frac = current / total if total > 0 else 0
                overall_current = _cidx + child_frac
                progress_cb(
                    int(overall_current * 100 / total_children),
                    100,
                )

        if message_cb:
            message_cb(
                f"[composite] Running child {child_idx + 1}/{total_children}: "
                f"{child_id} ({child_type})"
            )

        # Validate child config (type coercion, defaults, bounds).
        # We intentionally skip input validation for composite children:
        # root nodes may not have all required inputs wired (they get data
        # via config instead), and the child block handles this gracefully.
        # Pass inputs= so connected ports satisfy mandatory config fields.
        block_schema = load_block_schema(block_dir)
        if block_schema:
            child_config = validate_config(block_schema, child_config, inputs=child_inputs)

        # Detect if child is itself a composite block (for nested composites).
        is_child_composite = block_schema.get("composite", False) if block_schema else False
        child_context_cls = CompositeBlockContext if is_child_composite else None

        # Execute child block
        child_node_id = f"{parent_node_id}.{child_id}"
        try:
            outputs, fingerprints = load_and_run_fn(
                block_dir, child_config, child_inputs, child_run_dir,
                run_id, child_node_id,
                child_progress_cb, child_message_cb, child_metric_cb,
                context_cls=child_context_cls,
                _composite_depth=depth + 1,
            )
        except BlockError:
            # Re-raise BlockErrors directly — they already have good messages
            raise
        except Exception as e:
            raise BlockError(
                f"Composite child '{child_id}' ({child_type}) failed: {e}",
                details=traceback.format_exc(),
                recoverable=False,
            ) from e

        child_outputs[child_id] = outputs

        # Collect fingerprints from child blocks
        if fingerprints:
            merged_fingerprints[child_node_id] = fingerprints

        # Merge into final outputs with prefix
        for key, val in outputs.items():
            merged_outputs[f"{child_id}.{key}"] = val

        if message_cb:
            output_keys = list(outputs.keys())
            message_cb(
                f"[composite] Child {child_id} completed "
                f"(outputs: {output_keys})"
            )

    # Also expose the last child's outputs without prefix for convenience.
    # This makes it easy to wire a composite block's output to the final
    # child's output (e.g. the judge's response in a debate).
    if order and order[-1] in child_outputs:
        last_outputs = child_outputs[order[-1]]
        for key, val in last_outputs.items():
            merged_outputs[key] = val

    logger.info(
        "Composite %s: all %d children completed, %d outputs",
        parent_node_id, total_children, len(merged_outputs),
    )

    return merged_outputs, merged_fingerprints
