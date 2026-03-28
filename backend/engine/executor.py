"""
Pipeline Execution Engine.

Takes a pipeline graph (nodes + edges), topologically sorts blocks,
and executes them sequentially, passing outputs between blocks.
"""

import asyncio
import collections
import json
import os
import random
import re
import sys
import threading
import time
import traceback
import uuid
import importlib.util
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Single source of truth for block aliases — shared with subprocess worker
from .block_aliases import SAFE_BLOCK_TYPE, BLOCK_ALIASES, CONFIG_MIGRATIONS

from sqlalchemy.orm import Session

from ..config import ARTIFACTS_DIR, BUILTIN_BLOCKS_DIR, BLOCKS_DIR, CUSTOM_BLOCKS_DIR, MAX_PARALLEL_BLOCKS
from ..database import SessionLocal
from ..models.run import Run, LiveRun
from ..block_sdk.context import BlockContext
from ..block_sdk.exceptions import BlockError, BlockInputError, BlockConfigError, BlockTimeoutError
from .composite import CompositeBlockContext, execute_sub_pipeline
from ..routers.events import publish_event
from ..utils.secrets import get_secret
from ..utils.redact import scrub_traceback
from .block_registry import resolve_output_handle
from .schema_validator import load_block_schema, validate_inputs, validate_config
from .runtime_prep import prepare_node_runtime, PreparedNode, apply_multi_input_policy
from ..utils.structured_logger import (
    log_run_start, log_run_complete, log_run_failed,
    log_block_start, log_block_complete, log_block_failed,
)
from .config_resolver import resolve_configs, inject_workspace_file_paths
from .fingerprint import compute_fingerprints
from .block_registry import BlockRegistryService
from .metrics_schema import create_metric
from .artifact_registry import register_block_artifacts
from .artifacts import ArtifactStore
from ..models.artifact import ArtifactRecord
from .subprocess_runner import SubprocessBlockRunner
from .worker_tracker import track_worker, untrack_worker
from ..models.execution_decision import ExecutionDecision

# Ensure the repo root is on sys.path so blocks can do cross-block imports
# like `from blocks.inference._inference_utils import ...`.
# Done at module level (once at import time) to avoid TOCTOU races when
# _load_and_run_block is called from multiple threads.
_blocks_parent = str(BUILTIN_BLOCKS_DIR.parent)
if _blocks_parent not in sys.path:
    sys.path.insert(0, _blocks_parent)

# Cancel events: threading.Event per run_id, protected by lock for thread safety
_cancel_events: dict[str, threading.Event] = {}
_cancel_lock = threading.Lock()

# ── Debug / breakpoint infrastructure ──
_debug_lock = threading.Lock()
_debug_resume_events: dict[str, threading.Event] = {}
_debug_step_flags: dict[str, bool] = {}  # True = pause after NEXT node too
_debug_abort_flags: dict[str, bool] = {}  # True = abort run

# Concurrency semaphore: limits *actively executing* (non-paused) pipeline runs.
# When a run pauses at a breakpoint it releases a slot so other runs can proceed.
# The thread pool itself is sized larger (see execution.py) to hold paused threads.
MAX_ACTIVE_RUNS = int(os.environ.get("BLUEPRINT_MAX_ACTIVE_RUNS", "4"))
_active_run_semaphore = threading.Semaphore(MAX_ACTIVE_RUNS)

# Maximum time (seconds) a breakpoint pause blocks before auto-aborting.
# Prevents indefinitely blocked threads when a user walks away.
# Override via BLUEPRINT_BREAKPOINT_TIMEOUT env var.
BREAKPOINT_PAUSE_TIMEOUT_S = int(os.environ.get("BLUEPRINT_BREAKPOINT_TIMEOUT", "1800"))  # 30 min


def request_cancel(run_id: str):
    """Signal a running pipeline to cancel. Called from the cancel endpoint."""
    with _cancel_lock:
        event = _cancel_events.get(run_id)
        if event:
            event.set()


def debug_action(run_id: str, action: str):
    """Handle a debug action: resume, step, or abort.

    Called from the debug API endpoint while execution is paused at a breakpoint.
    """
    with _debug_lock:
        resume_event = _debug_resume_events.get(run_id)
        if not resume_event:
            return False

        if action == "resume":
            _debug_step_flags[run_id] = False
            resume_event.set()
        elif action == "step":
            _debug_step_flags[run_id] = True
            resume_event.set()
        elif action == "abort":
            _debug_abort_flags[run_id] = True
            resume_event.set()
        else:
            return False
        return True


class BreakpointAbort(Exception):
    """Raised when a breakpoint pause results in an abort or timeout."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _pause_at_breakpoint(
    run_id: str,
    node_id: str,
    idx: int,
    total: int,
    order: list[str],
    outputs: dict[str, dict[str, Any]],
    *,
    conditional: bool = False,
):
    """Shared breakpoint pause logic used by both the main loop and _execute_loop.

    Emits a ``breakpoint_hit`` SSE event, releases the active-run semaphore so
    other pipelines can proceed, blocks until a debug action arrives (or timeout
    expires), then re-acquires the semaphore.

    Raises ``BreakpointAbort`` if the user chose *abort* or the timeout expired.
    """
    # Build a truncated outputs preview for the SSE event
    outputs_preview: dict[str, dict] = {}
    for cid, couts in outputs.items():
        safe: dict[str, Any] = {}
        for k, v in couts.items():
            try:
                json.dumps(v)
                safe[k] = v if not isinstance(v, str) or len(v) < 500 else v[:500] + "..."
            except Exception:
                safe[k] = str(v)[:500]
        outputs_preview[cid] = safe

    completed_nodes = [nid for nid in order[:idx + (1 if conditional else 0)] if nid in outputs]

    try:
        publish_event(run_id, "breakpoint_hit", {
            "node_id": node_id,
            "completed_nodes": completed_nodes,
            "outputs_preview": outputs_preview,
            "index": idx,
            "total": total,
            "conditional": conditional,
        })
    except Exception:
        pass

    # Release the active-run semaphore while paused so other pipelines can run.
    _active_run_semaphore.release()

    try:
        with _debug_lock:
            resume_event = _debug_resume_events.get(run_id)

        if resume_event:
            resume_event.clear()
            # Block with a timeout — prevents indefinitely stuck threads
            signalled = resume_event.wait(timeout=BREAKPOINT_PAUSE_TIMEOUT_S)

            if not signalled:
                # Timeout expired — treat as auto-abort
                with _debug_lock:
                    _debug_abort_flags[run_id] = True

        # Check if abort was requested (by user action or timeout)
        with _debug_lock:
            if _debug_abort_flags.get(run_id, False):
                _debug_abort_flags[run_id] = False
                timed_out = not signalled if resume_event else False
                reason = (
                    f"Breakpoint pause timed out after {BREAKPOINT_PAUSE_TIMEOUT_S}s"
                    if timed_out
                    else "Aborted at breakpoint"
                )
                raise BreakpointAbort(reason)
    finally:
        # Re-acquire the semaphore before resuming active execution
        _active_run_semaphore.acquire()


def evaluate_breakpoint_condition(condition: dict, outputs: dict) -> bool:
    """Evaluate a declarative breakpoint condition against block outputs.

    Condition format: {field: str, op: str, value: number}
    Operators: gt, lt, gte, lte, eq, neq

    Returns True if the condition is met (breakpoint should fire).
    Returns True on evaluation errors (fail-open: pause on error).
    """
    if not condition or not isinstance(condition, dict):
        return True  # No condition = always pause

    field = condition.get("field", "")
    op = condition.get("op", "")
    threshold = condition.get("value")

    if not field or not op or threshold is None:
        return True  # Malformed condition = always pause

    # Look up the field in the block outputs
    actual_value = outputs.get(field)

    # If the field is nested in a dict output, try a single level of nesting
    if actual_value is None:
        for v in outputs.values():
            if isinstance(v, dict) and field in v:
                actual_value = v[field]
                break

    if actual_value is None:
        return True  # Field not found = pause (fail-open)

    try:
        actual_value = float(actual_value)
        threshold = float(threshold)
    except (TypeError, ValueError):
        return True  # Non-numeric = pause (fail-open)

    ops = {
        "gt": lambda a, b: a > b,
        "lt": lambda a, b: a < b,
        "gte": lambda a, b: a >= b,
        "lte": lambda a, b: a <= b,
        "eq": lambda a, b: a == b,
        "neq": lambda a, b: a != b,
    }
    comparator = ops.get(op)
    if not comparator:
        return True  # Unknown op = pause (fail-open)

    return comparator(actual_value, threshold)


def _infer_severity(msg: object) -> str:
    """Infer log severity from a message's text prefix.

    Used as a fallback when the block does not provide an explicit severity
    via ``ctx.log_message(msg, severity="...")``.

    Recognized prefixes (case-insensitive):
        [ERROR], ERROR:  → "error"
        [WARN], [WARNING], WARNING:  → "warn"
        [DEBUG]  → "debug"
        everything else  → "info"
    """
    if not isinstance(msg, str):
        return "info"
    lower = msg.lower()
    if lower.startswith("[error]") or lower.startswith("error:"):
        return "error"
    if lower.startswith(("[warn]", "[warning]", "warning:")):
        return "warn"
    if lower.startswith("[debug]"):
        return "debug"
    return "info"


def _topological_sort(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Topological sort of pipeline DAG. Returns node IDs in execution order."""
    in_degree: dict[str, int] = {n["id"]: 0 for n in nodes}
    adj: dict[str, list[str]] = {n["id"]: [] for n in nodes}

    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in adj and tgt in in_degree:
            adj[src].append(tgt)
            in_degree[tgt] += 1

    queue = collections.deque(nid for nid, deg in in_degree.items() if deg == 0)
    order: list[str] = []

    while queue:
        nid = queue.popleft()
        order.append(nid)
        for neighbor in adj.get(nid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return order


# Maximum loop iterations to prevent infinite loops from misconfiguration
MAX_LOOP_ITERATIONS = 10_000


@dataclass
class LoopDefinition:
    """Describes a valid loop subgraph in the pipeline."""
    controller_id: str
    body_node_ids: list[str] = field(default_factory=list)
    feedback_edges: list[dict] = field(default_factory=list)
    entry_edges: list[dict] = field(default_factory=list)


def _detect_loops(
    nodes: list[dict], edges: list[dict]
) -> list[LoopDefinition]:
    """Identify valid loop subgraphs in the pipeline.

    Uses Kahn's algorithm to find cyclic nodes, then Kosaraju's algorithm
    to find strongly connected components (SCCs).  Each SCC must contain
    exactly one loop_controller node.

    This approach is fully iterative (no recursion-limit risk), correctly
    handles multiple paths through the same controller, and naturally
    unions all body nodes from overlapping cycles.

    Returns a list of LoopDefinition.
    Raises ValueError if a cycle has zero or 2+ loop_controller nodes.
    """
    node_map = {n["id"]: n for n in nodes}
    if not node_map:
        return []

    adjacency: dict[str, list[str]] = {nid: [] for nid in node_map}
    reverse_adj: dict[str, list[str]] = {nid: [] for nid in node_map}
    in_degree: dict[str, int] = {nid: 0 for nid in node_map}

    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in adjacency and tgt in adjacency:
            adjacency[src].append(tgt)
            reverse_adj[tgt].append(src)
            in_degree[tgt] += 1

    # ── Step 1: Kahn's algorithm to find nodes involved in cycles ──
    kahn_deg = dict(in_degree)
    queue = collections.deque(nid for nid, d in kahn_deg.items() if d == 0)
    acyclic: set[str] = set()
    while queue:
        n = queue.popleft()
        acyclic.add(n)
        for nb in adjacency.get(n, []):
            kahn_deg[nb] -= 1
            if kahn_deg[nb] == 0:
                queue.append(nb)

    cyclic_nodes = set(node_map.keys()) - acyclic
    if not cyclic_nodes:
        return []

    # ── Step 2: Kosaraju's SCC (iterative) among cyclic nodes ──
    # Phase A: DFS on forward graph → finish order
    visited: set[str] = set()
    finish_order: list[str] = []
    for start in sorted(cyclic_nodes):
        if start in visited:
            continue
        stack: list[tuple[str, bool]] = [(start, False)]
        while stack:
            node, processed = stack.pop()
            if processed:
                finish_order.append(node)
                continue
            if node in visited:
                continue
            visited.add(node)
            stack.append((node, True))
            for nb in adjacency.get(node, []):
                if nb in cyclic_nodes and nb not in visited:
                    stack.append((nb, False))

    # Phase B: DFS on reverse graph in reverse finish order → SCCs
    visited = set()
    sccs: list[list[str]] = []
    for node in reversed(finish_order):
        if node in visited:
            continue
        component: list[str] = []
        stack_b: list[str] = [node]
        while stack_b:
            n = stack_b.pop()
            if n in visited:
                continue
            visited.add(n)
            component.append(n)
            for nb in reverse_adj.get(n, []):
                if nb in cyclic_nodes and nb not in visited:
                    stack_b.append(nb)
        sccs.append(component)

    # ── Step 2b: Filter stuck-downstream nodes ──
    # Kahn's residual includes nodes whose in-degree never reached 0 because
    # a cyclic predecessor was never processed — but they may NOT be in any
    # actual cycle. Kosaraju correctly places them in single-node SCCs.
    # A single-node SCC with no self-loop edge is NOT a real cycle — discard it.
    def _has_self_loop(nid: str) -> bool:
        return any(
            e.get("source") == nid and e.get("target") == nid
            for e in edges
        )

    sccs = [scc for scc in sccs if len(scc) > 1 or _has_self_loop(scc[0])]

    if not sccs:
        return []

    # ── Step 3: Validate each SCC and build LoopDefinitions ──
    def _is_loop_controller(nid: str) -> bool:
        n = node_map.get(nid, {})
        return n.get("data", {}).get("type", "") == "loop_controller"

    loops: list[LoopDefinition] = []
    for scc in sccs:
        controllers = [n for n in scc if _is_loop_controller(n)]
        if len(controllers) != 1:
            if len(controllers) == 0:
                raise ValueError(
                    "Pipeline contains a cycle that doesn't pass through "
                    "a Loop Controller block."
                )
            else:
                raise ValueError(
                    f"Pipeline cycle contains {len(controllers)} Loop Controller "
                    f"blocks; exactly 1 is required per cycle."
                )

        controller_id = controllers[0]
        body_nodes_set = set(scc) - {controller_id}

        # Topo-sort body nodes (edges within body only, no feedback edges)
        body_adj: dict[str, list[str]] = {n: [] for n in body_nodes_set}
        body_in_deg: dict[str, int] = {n: 0 for n in body_nodes_set}
        for edge in edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            if src in body_nodes_set and tgt in body_nodes_set:
                body_adj[src].append(tgt)
                body_in_deg[tgt] += 1

        queue = collections.deque(sorted(n for n, d in body_in_deg.items() if d == 0))
        body_order: list[str] = []
        while queue:
            n = queue.popleft()
            body_order.append(n)
            for nb in body_adj.get(n, []):
                body_in_deg[nb] -= 1
                if body_in_deg[nb] == 0:
                    queue.append(nb)
        # Safety: append any unreached nodes (possible in complex topologies)
        for n in sorted(body_nodes_set):
            if n not in body_order:
                body_order.append(n)

        # Collect ALL entry edges (controller → body) and feedback edges (body → controller)
        entry_edges = [
            e for e in edges
            if e.get("source") == controller_id and e.get("target") in body_nodes_set
        ]
        feedback_edges = [
            e for e in edges
            if e.get("target") == controller_id and e.get("source") in body_nodes_set
        ]

        loops.append(LoopDefinition(
            controller_id=controller_id,
            body_node_ids=body_order,
            feedback_edges=feedback_edges,
            entry_edges=entry_edges,
        ))

    return loops


def _topological_sort_with_loops(
    nodes: list[dict], edges: list[dict], loops: list[LoopDefinition]
) -> list[str]:
    """Sort pipeline with loop awareness.

    1. Remove ALL feedback edges (body → controller) to break cycles
    2. Topological sort the resulting DAG
    3. Return execution order (loop bodies handled separately by _execute_loop)
    """
    if not loops:
        return _topological_sort(nodes, edges)

    # Collect ALL feedback edges to exclude (there may be multiple per loop
    # when the loop body has branches that converge back to the controller)
    feedback_edge_keys: set[tuple[str, str, str, str]] = set()
    for loop_def in loops:
        for fe in loop_def.feedback_edges:
            feedback_edge_keys.add(
                (fe.get("source", ""), fe.get("target", ""),
                 fe.get("sourceHandle", ""), fe.get("targetHandle", ""))
            )

    non_feedback_edges = [
        e for e in edges
        if (e.get("source", ""), e.get("target", ""),
            e.get("sourceHandle", ""), e.get("targetHandle", ""))
        not in feedback_edge_keys
    ]

    return _topological_sort(nodes, non_feedback_edges)


def _find_block_module(block_type: str) -> Path | None:
    """Find the run.py for a given block type."""
    # Resolve aliases (e.g. model_prompt → llm_inference)
    block_type = BLOCK_ALIASES.get(block_type, block_type)
    # Validate block_type to prevent path traversal
    if not SAFE_BLOCK_TYPE.match(block_type):
        raise ValueError(f"Invalid block type: {block_type!r}")
    # Search built-in and user blocks (category/block_type/run.py structure)
    for base_dir in [BUILTIN_BLOCKS_DIR, BLOCKS_DIR]:
        if not base_dir.exists():
            continue
        for cat_dir in base_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            block_dir = cat_dir / block_type
            run_py = block_dir / "run.py"
            if run_py.exists():
                return block_dir
    # Search custom blocks (flat structure: custom_blocks/block_type/run.py)
    if CUSTOM_BLOCKS_DIR.exists():
        block_dir = CUSTOM_BLOCKS_DIR / block_type
        run_py = block_dir / "run.py"
        if run_py.exists():
            return block_dir
    # Search plugin blocks (direct lookup per plugin, not a full scan)
    from ..plugins.registry import plugin_registry
    plugin_block = plugin_registry.find_block(block_type)
    if plugin_block is not None:
        return plugin_block
    return None


def _load_and_run_block(
    block_dir: Path,
    config: dict,
    inputs: dict[str, Any],
    run_dir: str,
    run_id: str,
    node_id: str,
    progress_cb=None,
    message_cb=None,
    metric_cb=None,
    context_cls=None,
    _composite_depth: int = 0,
    loop_metadata: dict | None = None,
) -> tuple[dict[str, Any], dict[str, dict]]:
    """Load a block's run.py and execute it. Returns (outputs, data_fingerprints).

    Args:
        context_cls: Optional BlockContext subclass to use (e.g. CompositeBlockContext).
            Defaults to BlockContext.
        _composite_depth: Current composite nesting depth (for recursion guard).
            Managed by execute_sub_pipeline; callers should not set this directly.
        loop_metadata: Optional dict of loop iteration info (set by _execute_loop).
    """
    run_py = block_dir / "run.py"
    spec = importlib.util.spec_from_file_location(f"block_{node_id}", str(run_py))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load block module from {run_py}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "run"):
        raise RuntimeError(f"Block {block_dir.name} missing run() function")

    cls = context_cls or BlockContext
    ctx = cls(
        run_dir=run_dir,
        block_dir=str(block_dir),
        config=config,
        inputs=inputs,
        progress_callback=progress_cb,
        message_callback=message_cb,
        metric_callback=metric_cb,
        loop_metadata=loop_metadata,
    )

    module.run(ctx)

    outputs = ctx.get_outputs()
    fingerprints = ctx.get_data_fingerprints()

    # If this is a composite block and it defined a sub-pipeline, execute it
    if isinstance(ctx, CompositeBlockContext) and ctx.has_sub_pipeline():
        sub_definition = ctx.get_sub_pipeline()
        sub_outputs, sub_fingerprints = execute_sub_pipeline(
            sub_definition=sub_definition,
            run_dir=run_dir,
            run_id=run_id,
            parent_node_id=node_id,
            parent_inputs=inputs,
            progress_cb=progress_cb,
            message_cb=message_cb,
            metric_cb=metric_cb,
            find_block_fn=_find_block_module,
            load_and_run_fn=_load_and_run_block,
            resolve_secrets_fn=_resolve_secrets,
            depth=_composite_depth,
        )
        outputs.update(sub_outputs)
        fingerprints.update(sub_fingerprints)

    return outputs, fingerprints


def _load_and_run_block_with_timeout(
    block_dir: Path,
    config: dict,
    inputs: dict[str, Any],
    run_dir: str,
    run_id: str,
    node_id: str,
    progress_cb=None,
    message_cb=None,
    metric_cb=None,
    timeout_seconds=None,
    context_cls=None,
    loop_metadata: dict | None = None,
) -> tuple[dict[str, Any], dict[str, dict]]:
    """Wrapper that enforces a timeout on block execution.

    Args:
        timeout_seconds: Maximum execution time. None means no timeout.
            Caller should read this from the block schema to avoid redundant I/O.
        context_cls: Optional BlockContext subclass (e.g. CompositeBlockContext).
        loop_metadata: Optional dict of loop iteration info.

    Returns:
        (outputs, data_fingerprints) tuple from _load_and_run_block.
    """
    if timeout_seconds is None:
        # No timeout configured, run directly (no thread overhead)
        return _load_and_run_block(
            block_dir, config, inputs, run_dir,
            run_id, node_id, progress_cb, message_cb, metric_cb,
            context_cls=context_cls,
            _composite_depth=0,
            loop_metadata=loop_metadata,
        )

    result: list[tuple[dict, dict]] = []
    error = [None]

    def target():
        try:
            result.append(
                _load_and_run_block(
                    block_dir, config, inputs, run_dir,
                    run_id, node_id, progress_cb, message_cb, metric_cb,
                    context_cls=context_cls,
                    _composite_depth=0,
                    loop_metadata=loop_metadata,
                )
            )
        except Exception as e:
            error[0] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        # Thread keeps running (Python can't force-kill threads), but daemon=True
        # ensures it won't block process exit. The cancel event mechanism will
        # terminate it on the next progress_cb call if the block cooperates.
        raise BlockTimeoutError(
            timeout_seconds,
            f"Block '{block_dir.name}' exceeded {timeout_seconds}s timeout",
        )

    if error[0]:
        raise error[0]

    return result[0]


# Module-level subprocess runner (reused across all runs)
_subprocess_runner = SubprocessBlockRunner()


def _run_block_subprocess(
    block_type: str,
    config: dict,
    inputs: dict[str, Any],
    run_id: str,
    node_id: str,
    timeout_seconds: int | None = None,
    progress_cb=None,
    message_cb=None,
) -> tuple[dict[str, Any], dict[str, dict]]:
    """Execute a block in an isolated subprocess.

    Returns (outputs, data_fingerprints). The subprocess writes fingerprints
    to a JSON file which the runner reads back after completion.
    """
    def _progress_forwarder(percent: float, message: str):
        if progress_cb and percent >= 0:
            total = 100
            current = int(percent * total)
            try:
                progress_cb(current, total)
            except Exception:
                pass
        if message_cb and message and not message.startswith("Progress:"):
            try:
                message_cb(message)
            except Exception:
                pass

    outputs, fingerprints = _subprocess_runner.run_block(
        block_type=block_type,
        config=config,
        inputs=inputs,
        timeout_seconds=timeout_seconds or 3600,
        progress_callback=_progress_forwarder,
        run_id=run_id,
        node_id=node_id,
    )

    return outputs, fingerprints


def _resolve_secrets(config: dict) -> dict:
    """Replace $secret:<name> references in config values with actual secrets."""
    resolved = {}
    for key, value in config.items():
        if isinstance(value, str) and value.startswith('$secret:'):
            secret_name = value[len('$secret:'):]
            secret_value = get_secret(secret_name)
            if secret_value is None:
                raise ValueError(f"Secret '{secret_name}' not found for config key '{key}'")
            resolved[key] = secret_value
        elif isinstance(value, dict):
            resolved[key] = _resolve_secrets(value)
        else:
            resolved[key] = value
    return resolved


# ── Memory Pressure Circuit Breaker ──────────────────────────────────
# Default 90%. Applies to BOTH psutil system RAM and MLX Metal footprint.
MEMORY_PRESSURE_THRESHOLD = float(
    os.environ.get("BLUEPRINT_MEMORY_THRESHOLD", "90")
)


def _check_memory_pressure() -> tuple[bool, float]:
    """Check memory pressure from two independent sources.

    1. psutil: standard OS-level virtual memory percentage.
    2. mlx.core.metal: active + cache allocations as a percentage of
       total system RAM.  On Apple Silicon, Metal allocates from the
       same unified pool but psutil doesn't reflect GPU-side pressure
       until the kernel is already paging to swap.  Querying the Metal
       allocator directly catches sudden multi-GB spikes (e.g. large
       batch inference) before the OS enters a death spiral.

    Triggers if EITHER source exceeds MEMORY_PRESSURE_THRESHOLD.
    Returns (is_critical, worst_percent).  Fail-open: returns (False, 0.0)
    if neither psutil nor mlx is available.
    """
    system_pct = 0.0
    mlx_pct = 0.0
    has_any = False

    # Source 1: OS-level memory pressure
    try:
        import psutil
        system_pct = psutil.virtual_memory().percent
        has_any = True
    except ImportError:
        pass

    # Source 2: MLX Metal allocator (Apple Silicon GPU-side)
    try:
        import mlx.core.metal as metal
        active = metal.get_active_memory()   # bytes currently held by tensors
        cache = metal.get_cache_memory()     # bytes in allocator cache (reserved)
        metal_bytes = active + cache
        # Denominator: total physical RAM — the unified pool ceiling.
        import psutil as _ps
        total_ram = _ps.virtual_memory().total
        mlx_pct = round(metal_bytes / total_ram * 100, 1) if total_ram > 0 else 0.0
        has_any = True
    except (ImportError, AttributeError):
        # mlx not installed, or running on non-Apple-Silicon hardware
        pass

    if not has_any:
        return False, 0.0

    worst = round(max(system_pct, mlx_pct), 1)
    return worst >= MEMORY_PRESSURE_THRESHOLD, worst


def _check_cancelled(run_id: str) -> bool:
    """Check if a run has been cancelled."""
    with _cancel_lock:
        event = _cancel_events.get(run_id)
    return event is not None and event.is_set()


def _collect_system_metrics() -> dict | None:
    """Collect CPU/memory/GPU metrics. Returns None if psutil unavailable."""
    try:
        import psutil
    except ImportError:
        return None
    metrics: dict[str, float] = {
        "cpu_pct": psutil.cpu_percent(interval=None),
        "mem_pct": psutil.virtual_memory().percent,
        "mem_gb": round(psutil.virtual_memory().used / (1024 ** 3), 2),
    }
    # GPU memory via nvidia-smi (optional)
    try:
        import subprocess  # noqa: S404 — lazy import; nvidia-smi may not exist
        result = subprocess.run(  # noqa: S603, S607
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            used, total = result.stdout.strip().split(",")
            metrics["gpu_mem_pct"] = round(float(used) / float(total) * 100, 1)
    except Exception:
        pass
    return metrics


def _safe_commit(db: Session):
    """Commit without raising — log and continue on failure."""
    try:
        db.commit()
    except Exception:
        db.rollback()


def _record_decision(
    db: Session,
    run_id: str,
    node_id: str,
    decision: str,
    reason: str,
    cache_fingerprint: str | None = None,
    plan_hash: str | None = None,
) -> None:
    """Write an ExecutionDecision record. Best-effort — never raises."""
    try:
        record = ExecutionDecision(
            id=str(uuid.uuid4()),
            run_id=run_id,
            node_id=node_id,
            decision=decision,
            reason=reason,
            cache_fingerprint=cache_fingerprint,
            plan_hash=plan_hash,
            timestamp=datetime.now(timezone.utc),
        )
        db.add(record)
        _safe_commit(db)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def _start_heartbeat(run_id: str, interval: float = 30.0):
    """Start a background thread that updates last_heartbeat every `interval` seconds.

    Uses its own DB session to avoid thread-safety issues with the executor's session.
    """
    stop_event = threading.Event()

    def heartbeat():
        hb_session = SessionLocal()
        try:
            while not stop_event.is_set():
                stop_event.wait(interval)
                if stop_event.is_set():
                    break
                try:
                    run = hb_session.query(Run).filter(Run.id == run_id).first()
                    if run and run.status == "running":
                        run.last_heartbeat = datetime.now(timezone.utc)
                        hb_session.commit()
                except Exception:
                    try:
                        hb_session.rollback()
                    except Exception:
                        pass
        finally:
            hb_session.close()

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    return stop_event


def _safe_int(value: Any, default: int) -> int:
    """Safely coerce a config value to int."""
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    return default


def _safe_float(value: Any, default: float) -> float:
    """Safely coerce a config value to float."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    return default


def _safe_bool(value: Any, default: bool) -> bool:
    """Safely coerce a config value to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    if isinstance(value, (int, float)):
        return bool(value)
    return default


# ── Artifact Cache Integration ────────────────────────────────────────
# Module-level ArtifactStore instance, reused across all runs.
_artifact_store = ArtifactStore(base_path=Path(ARTIFACTS_DIR))

# Logger for artifact cache (best-effort, never crashes execution)
import logging as _logging
_artifact_cache_logger = _logging.getLogger("blueprint.artifact_cache")


def _infer_port_data_type(port_id: str, value: Any, block_schema: dict | None) -> str:
    """Infer the data_type for an output port.

    1. Check block_schema outputs for a declared data_type
    2. Fall back to heuristic type detection from the value
    """
    if block_schema:
        for output_def in block_schema.get("outputs", []):
            if isinstance(output_def, dict) and output_def.get("id") == port_id:
                return output_def.get("data_type", "text")

    # Heuristic fallback
    if isinstance(value, str):
        return "text"
    if isinstance(value, dict):
        # Dicts with numeric values look like metrics
        if value and all(isinstance(v, (int, float)) for v in value.values()):
            return "metrics"
        return "config"
    if isinstance(value, list):
        return "dataset"
    if isinstance(value, bytes):
        return "artifact"
    return "text"


def _is_json_serializable(value: Any) -> bool:
    """Quick check if a value can be serialized as JSON."""
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError, OverflowError):
        return False


def _cache_block_outputs(
    node_id: str,
    run_id: str,
    node_outputs: dict[str, Any],
    block_schema: dict | None,
    db: Session,
) -> None:
    """Store each output port as a cached artifact with SHA-256 verification.

    Best-effort: logs warnings on failure, never raises.
    Skips values that are not serializable by the artifact cache.
    Persists ArtifactRecord rows in the DB for later retrieval.
    """
    if not node_outputs:
        return

    records: list[ArtifactRecord] = []
    for port_id, value in node_outputs.items():
        try:
            data_type = _infer_port_data_type(port_id, value, block_schema)

            # Skip non-serializable values for non-raw types
            if data_type != "artifact" and not _is_json_serializable(value):
                # Fall back to text serialization of the string representation
                data_type = "text"
                value = str(value)

            manifest = _artifact_store.store(
                node_id=node_id,
                port_id=port_id,
                run_id=run_id,
                data=value,
                data_type=data_type,
            )
            records.append(ArtifactRecord.from_manifest(manifest))
        except Exception as exc:
            _artifact_cache_logger.debug(
                "Artifact cache: skipped port %s/%s: %s", node_id, port_id, exc
            )

    if records:
        try:
            for record in records:
                db.add(record)
            db.flush()  # flush within the existing transaction, committed by caller
        except Exception as exc:
            _artifact_cache_logger.warning(
                "Artifact cache: DB flush failed for node %s: %s", node_id, exc
            )
            try:
                db.rollback()
            except Exception:
                pass


@dataclass
class _BodyBlockInfo:
    """Pre-computed per-body-block metadata (computed once, reused each iteration)."""
    node_id: str
    block_type: str
    category: str
    block_dir: Path
    schema: dict | None
    config: dict
    timeout_seconds: int | None
    is_composite: bool
    context_cls: type | None
    run_dir: str
    # Edges targeting this body node (pre-filtered for faster input gathering)
    incoming_edges: list[dict] = field(default_factory=list)


async def _execute_loop(
    loop: LoopDefinition,
    node_map: dict[str, dict],
    edges: list[dict],
    outputs: dict[str, dict[str, Any]],
    all_metrics: dict[str, Any],
    all_fingerprints: dict[str, dict],
    run_id: str,
    pipeline_id: str,
    resolved_configs: dict,
    metrics_file,
    metrics_log_buffer: list[dict],
    start_time: float,
    db: Session,
    live: LiveRun,
    breakpoints: dict[str, dict | bool] | None = None,
):
    """Execute a loop body repeatedly.

    1. Read seed input and config from the loop_controller node
    2. Pre-compute per-body-block metadata (block_dir, schema, config, etc.)
    3. For each iteration:
       a. Build loop_metadata dict
       b. Execute body blocks with proper SSE events (started/output/completed)
       c. Collect output from last body block
       d. Feed back to controller (via feedback port)
       e. Check stop condition
       f. Emit node_iteration SSE event
    4. After all iterations, controller emits final accumulated output
    """
    controller_node = node_map[loop.controller_id]
    controller_data = controller_node.get("data", {})
    controller_config = resolved_configs.get(
        loop.controller_id,
        controller_data.get("config", {}),
    )
    controller_config = {k: v for k, v in controller_config.items() if k != "_inherited"}

    # Parse controller config with safe type coercion
    iterations = min(
        _safe_int(controller_config.get("iterations", 10), 10),
        MAX_LOOP_ITERATIONS,
    )
    stop_metric = str(controller_config.get("stop_metric", "") or "")
    stop_threshold = _safe_float(controller_config.get("stop_threshold", 0), 0.0)
    stop_direction = str(controller_config.get("stop_direction", "above") or "above")
    context_management = str(controller_config.get("context_management", "clear") or "clear")
    file_mode = str(controller_config.get("file_mode", "append") or "append")
    seed_mode = str(controller_config.get("seed_mode", "increment") or "increment")
    base_seed = _safe_int(controller_config.get("base_seed", 42), 42)
    accumulate_results = _safe_bool(controller_config.get("accumulate_results", True), True)
    prompt_variation = str(controller_config.get("prompt_variation", "") or "")
    iteration_delay_ms = _safe_int(controller_config.get("iteration_delay_ms", 0), 0)

    # ── Pre-compute per-body-block metadata (done once, reused every iteration) ──
    body_block_infos: list[_BodyBlockInfo] = []
    for body_node_id in loop.body_node_ids:
        body_node = node_map.get(body_node_id)
        if not body_node:
            continue

        body_data = body_node.get("data", {})
        body_type = body_data.get("type", "")
        body_config = resolved_configs.get(
            body_node_id, body_data.get("config", {}),
        )
        body_config = {k: v for k, v in body_config.items() if k != "_inherited"}

        category = body_data.get("category", "flow")

        # Pre-filter edges targeting this body node
        incoming_edges = [e for e in edges if e.get("target") == body_node_id]

        # Build placeholder inputs from connected edges so validate_config
        # knows which mandatory config fields are satisfied by connections
        placeholder_inputs: dict[str, Any] = {}
        for edge in incoming_edges:
            tgt_handle = edge.get("targetHandle", "")
            if tgt_handle:
                placeholder_inputs[tgt_handle] = True  # non-None placeholder

        prepared = prepare_node_runtime(
            node_id=body_node_id,
            block_type=body_type,
            config=body_config,
            node_inputs=placeholder_inputs,
            run_id=run_id,
            find_block_fn=_find_block_module,
            resolve_secrets_fn=_resolve_secrets,
            block_aliases=BLOCK_ALIASES,
            safe_block_type_re=SAFE_BLOCK_TYPE,
        )

        # Embed block version into config_snapshot for cache validation
        if prepared.block_version:
            body_data["block_version"] = prepared.block_version

        body_block_infos.append(_BodyBlockInfo(
            node_id=body_node_id,
            block_type=body_type,
            category=category,
            block_dir=prepared.block_dir,
            schema=prepared.block_schema,
            config=prepared.cleaned_config,
            timeout_seconds=prepared.timeout_seconds,
            is_composite=prepared.is_composite,
            context_cls=prepared.context_cls,
            run_dir=prepared.run_dir,
            incoming_edges=incoming_edges,
        ))

    # ── Iteration loop ──
    accumulated: list[Any] = []
    previous_output: Any = None
    last_iteration = 0

    for i in range(iterations):
        last_iteration = i

        # Check cancellation
        if _check_cancelled(run_id):
            break

        # Memory pressure circuit breaker (inside loop)
        is_critical, mem_pct = _check_memory_pressure()
        if is_critical:
            raise BlockError(
                f"Execution halted: Out of Memory Protection triggered. "
                f"{mem_pct}% of unified memory in use "
                f"(threshold: {MEMORY_PRESSURE_THRESHOLD}%).",
                recoverable=False,
            )

        # Compute iteration seed
        if seed_mode == "fixed":
            seed = base_seed
        elif seed_mode == "increment":
            seed = base_seed + i
        else:  # random
            seed = random.randint(0, 2**31)

        # Render prompt variation template
        variation = ""
        if prompt_variation:
            try:
                variation = prompt_variation.replace("{{iteration}}", str(i))
                variation = variation.replace("{{total}}", str(iterations))
                variation = variation.replace("{{seed}}", str(seed))
                if previous_output:
                    variation = variation.replace(
                        "{{previous_output}}", str(previous_output)[:1000]
                    )
            except Exception:
                variation = prompt_variation

        # Build loop metadata
        loop_metadata = {
            "iteration": i,
            "total_iterations": iterations,
            "file_mode": file_mode,
            "context_management": context_management,
            "seed": seed,
            "previous_output": str(previous_output)[:2000] if previous_output else None,
            "accumulated_data": list(accumulated) if accumulate_results else None,
            "prompt_variation": variation or None,
        }

        # Execute each body block with loop_metadata
        for info in body_block_infos:
            if _check_cancelled(run_id):
                break

            # Memory pressure circuit breaker (loop body)
            is_critical, mem_pct = _check_memory_pressure()
            if is_critical:
                raise BlockError(
                    f"Execution halted: Out of Memory Protection triggered. "
                    f"{mem_pct}% of unified memory in use "
                    f"(threshold: {MEMORY_PRESSURE_THRESHOLD}%).",
                    recoverable=False,
                )

            _nid = info.node_id
            _block_type = info.block_type
            _category = info.category

            # Emit node_started for body block
            started_event = {
                "node_id": _nid,
                "block_type": _block_type,
                "category": _category,
                "iteration": i,
            }
            try:
                publish_event(run_id, "node_started", started_event)
            except Exception:
                pass
            metrics_log_buffer.append({"type": "node_started", "timestamp": time.time(), **started_event})
            metrics_file.write(json.dumps({"type": "node_started", "timestamp": time.time(), **started_event}) + "\n")
            metrics_file.flush()

            body_block_start = time.time()

            # ── Loop body breakpoint check (pre-execution) ──
            if breakpoints:
                bp_info_loop = breakpoints.get(_nid)
                should_pause_loop = False
                if bp_info_loop is True:
                    should_pause_loop = True
                else:
                    with _debug_lock:
                        if _debug_step_flags.get(run_id, False):
                            should_pause_loop = True
                            _debug_step_flags[run_id] = False

                if should_pause_loop:
                    # Use body_node_ids as the order for the preview
                    loop_order = [loop.controller_id] + loop.body_node_ids
                    _pause_at_breakpoint(
                        run_id, _nid, i, iterations,
                        loop_order, outputs, conditional=False,
                    )
                    # BreakpointAbort propagates up to the caller

            # Gather inputs from upstream edges (including controller outputs)
            node_inputs: dict[str, Any] = {}
            _multi_counts: dict[str, int] = {}
            for edge in info.incoming_edges:
                src_id = edge.get("source", "")
                src_handle = edge.get("sourceHandle", "")
                tgt_handle = edge.get("targetHandle", "")
                if src_id in outputs and src_handle in outputs[src_id]:
                    value = outputs[src_id][src_handle]
                    _multi_counts[tgt_handle] = _multi_counts.get(tgt_handle, 0) + 1
                    if tgt_handle in node_inputs:
                        # Convert single value to list on second connection
                        if _multi_counts[tgt_handle] == 2:
                            node_inputs[tgt_handle] = [node_inputs[tgt_handle], value]
                        else:
                            # Already a list from 3rd connection onward
                            node_inputs[tgt_handle].append(value)
                    else:
                        node_inputs[tgt_handle] = value

            # Validate inputs each iteration (inputs may change across iterations)
            if info.schema:
                validate_inputs(info.schema, node_inputs)

            # Build callbacks with default-arg capture to avoid closure pitfalls
            def progress_cb(current, total, __nid=_nid):
                if _check_cancelled(run_id):
                    raise InterruptedError("Run cancelled by user")
                try:
                    publish_event(run_id, "node_progress", {
                        "node_id": __nid,
                        "progress": current / total if total > 0 else 0,
                    })
                except Exception:
                    pass

            def message_cb(msg, explicit_severity=None, __nid=_nid):
                if explicit_severity:
                    severity = explicit_severity
                else:
                    severity = _infer_severity(msg)
                try:
                    publish_event(run_id, "node_log", {
                        "node_id": __nid, "message": msg, "severity": severity,
                    })
                except Exception:
                    pass

            def metric_cb(name, value, step, __nid=_nid, __type=_block_type, __cat=_category):
                metric_event_obj = create_metric(
                    node_id=__nid, name=name, value=value,
                    category=__cat, step=step,
                )
                event_dict = metric_event_obj.to_dict()
                all_metrics[f"{__type}.{name}"] = value
                try:
                    publish_event(run_id, "metric", event_dict)
                except Exception:
                    pass
                metrics_file.write(json.dumps(event_dict) + "\n")
                metrics_file.flush()
                metrics_log_buffer.append(event_dict)

            # Execute block with loop_metadata injected into context
            node_outputs, data_fingerprints = _load_and_run_block_with_timeout(
                info.block_dir, info.config, node_inputs, info.run_dir,
                run_id, _nid, progress_cb, message_cb, metric_cb,
                timeout_seconds=info.timeout_seconds,
                context_cls=info.context_cls,
                loop_metadata=loop_metadata,
            )
            outputs[_nid] = node_outputs
            if data_fingerprints:
                all_fingerprints[_nid] = data_fingerprints

            # Cache loop body outputs as typed artifacts (best-effort)
            _cache_block_outputs(_nid, run_id, node_outputs, info.schema, db)

            # Register artifacts produced by this loop body block (best-effort)
            try:
                register_block_artifacts(
                    pipeline_id=pipeline_id,
                    run_id=run_id,
                    node_id=_nid,
                    block_type=_block_type,
                    outputs=node_outputs,
                    run_dir=info.run_dir,
                )
            except Exception:
                pass

            # Emit node_output for body block
            safe_outputs = {}
            for k, v in node_outputs.items():
                try:
                    json.dumps(v)
                    safe_outputs[k] = v if not isinstance(v, str) or len(v) < 200 else v[:200] + '...'
                except Exception:
                    safe_outputs[k] = str(v)[:200]
            try:
                publish_event(run_id, "node_output", {"node_id": _nid, "outputs": safe_outputs})
            except Exception:
                pass

            # Emit node_completed for body block
            body_duration_ms = round((time.time() - body_block_start) * 1000)
            completed_event = {"node_id": _nid, "iteration": i, "duration_ms": body_duration_ms}
            try:
                publish_event(run_id, "node_completed", completed_event)
            except Exception:
                pass
            metrics_log_buffer.append({"type": "node_completed", "timestamp": time.time(), **completed_event})
            metrics_file.write(json.dumps({"type": "node_completed", "timestamp": time.time(), **completed_event}) + "\n")
            metrics_file.flush()

            log_block_complete(run_id, _nid, _block_type, time.time() - body_block_start)

            # ── Loop body conditional breakpoint check (post-execution) ──
            if breakpoints:
                bp_info_loop_post = breakpoints.get(_nid)
                if isinstance(bp_info_loop_post, dict):
                    loop_node_outs = outputs.get(_nid, {})
                    if evaluate_breakpoint_condition(bp_info_loop_post, loop_node_outs):
                        loop_order = [loop.controller_id] + loop.body_node_ids
                        _pause_at_breakpoint(
                            run_id, _nid, i, iterations,
                            loop_order, outputs, conditional=True,
                        )
                        # BreakpointAbort propagates up to the caller

        # Update LiveRun progress during loop
        live.block_progress = (i + 1) / iterations
        _safe_commit(db)

        # Collect output from last body block
        if body_block_infos:
            last_body_id = body_block_infos[-1].node_id
            last_body_output = outputs.get(last_body_id, {})
            # Use first output value as the feedback value
            if last_body_output:
                first_key = next(iter(last_body_output))
                previous_output = last_body_output[first_key]
            else:
                previous_output = None
            if accumulate_results:
                accumulated.append(previous_output)

        # Emit SSE event
        try:
            publish_event(run_id, "node_iteration", {
                "node_id": loop.controller_id,
                "iteration": i,
                "total": iterations,
                "body_output_preview": str(previous_output)[:200] if previous_output else "",
            })
        except Exception:
            pass

        # Check stop condition
        if stop_metric and body_block_infos:
            last_body_id = body_block_infos[-1].node_id
            # Look for metric from the last body block
            metric_value = None
            for mkey, mval in all_metrics.items():
                if mkey.endswith(f".{stop_metric}"):
                    metric_value = mval
                    break
            if metric_value is None:
                # Also check block-level outputs for metrics
                last_outputs = outputs.get(last_body_id, {})
                if "metrics" in last_outputs and isinstance(last_outputs["metrics"], dict):
                    metric_value = last_outputs["metrics"].get(stop_metric)

            if metric_value is not None:
                try:
                    metric_value = float(metric_value)
                except (ValueError, TypeError):
                    metric_value = None

            if metric_value is not None:
                if stop_direction == "above" and metric_value > stop_threshold:
                    try:
                        publish_event(run_id, "node_log", {
                            "node_id": loop.controller_id,
                            "message": f"Early stop: {stop_metric}={metric_value} > {stop_threshold}",
                            "severity": "info",
                        })
                    except Exception:
                        pass
                    break
                elif stop_direction == "below" and metric_value < stop_threshold:
                    try:
                        publish_event(run_id, "node_log", {
                            "node_id": loop.controller_id,
                            "message": f"Early stop: {stop_metric}={metric_value} < {stop_threshold}",
                            "severity": "info",
                        })
                    except Exception:
                        pass
                    break

        # Iteration delay
        if iteration_delay_ms > 0:
            await asyncio.sleep(iteration_delay_ms / 1000.0)

    # Final output from controller
    controller_output = accumulated if accumulate_results else previous_output
    outputs[loop.controller_id] = {
        "result": controller_output,
        "metrics": {
            "iterations_completed": last_iteration + 1,
            "total_planned": iterations,
            "early_stopped": last_iteration + 1 < iterations,
        },
    }


async def execute_pipeline(
    pipeline_id: str,
    run_id: str,
    definition: dict,
    db: Session,
    *,
    project_id: str | None = None,
):
    """Execute a full pipeline. Called in a background thread."""
    from .config_merge import merge_workspace_config

    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    # Merge config from all scopes: global workspace → project → pipeline definition
    workspace_config = merge_workspace_config(
        definition_config=definition.get("workspace_config") or None,
        project_id=project_id,
        db=db,
    ) or None

    if not nodes:
        # Create a completed Run record so clients don't get a 404
        empty_run = Run(
            id=run_id,
            pipeline_id=pipeline_id,
            status="complete",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            duration_seconds=0,
            config_snapshot=definition,
            outputs_snapshot={},
            metrics={},
            metrics_log=[],
        )
        db.add(empty_run)
        db.commit()
        return

    # Register cancel event for this run
    with _cancel_lock:
        _cancel_events[run_id] = threading.Event()

    # Register debug state for breakpoint support
    with _debug_lock:
        _debug_resume_events[run_id] = threading.Event()
        _debug_step_flags[run_id] = False
        _debug_abort_flags[run_id] = False

    # Build breakpoint lookup from node data
    breakpoints: dict[str, dict | bool] = {}
    for n in nodes:
        nd = n.get("data", {})
        if nd.get("breakpoint"):
            condition = nd.get("breakpoint_condition")
            breakpoints[n["id"]] = condition if condition else True

    run = Run(
        id=run_id,
        pipeline_id=pipeline_id,
        project_id=project_id,
        status="running",
        started_at=datetime.now(timezone.utc),
        last_heartbeat=datetime.now(timezone.utc),
        config_snapshot=definition,
    )
    db.add(run)

    live = LiveRun(
        run_id=run_id,
        pipeline_name="",
        total_blocks=len(nodes),
        status="running",
    )
    db.add(live)
    db.commit()

    log_run_start(run_id, pipeline_id, len(nodes))

    # Acquire the active-run semaphore — limits concurrent active execution.
    # Released in finally (or temporarily during breakpoint pauses).
    _active_run_semaphore.acquire()

    # Start continuous heartbeat thread (every 30s, own DB session)
    heartbeat_stop = _start_heartbeat(run_id)

    node_map = {n["id"]: n for n in nodes}
    outputs: dict[str, dict[str, Any]] = {}
    all_metrics: dict[str, Any] = {}
    all_fingerprints: dict[str, dict] = {}

    # --- Layer 1: JSONL file failsafe (opened here so finally can close it) ---
    metrics_dir = ARTIFACTS_DIR / run_id
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics_file = open(metrics_dir / "metrics.jsonl", "a")  # noqa: SIM115 — closed in finally

    # --- Layer 2: In-memory buffer for SQLite checkpoints ---
    metrics_log_buffer: list[dict] = []
    last_checkpoint_time = time.time()
    CHECKPOINT_INTERVAL = 60  # seconds

    # --- System metrics publisher ---
    system_metrics_stop = threading.Event()

    def _system_metrics_loop():
        while not system_metrics_stop.is_set():
            system_metrics_stop.wait(10)
            if system_metrics_stop.is_set():
                break
            sm = _collect_system_metrics()
            if sm is None:
                continue
            event_data = {"type": "system_metric", "timestamp": time.time(), **sm}
            # Layer 1: JSONL
            try:
                metrics_file.write(json.dumps(event_data) + "\n")
                metrics_file.flush()
            except Exception:
                pass
            # Layer 2: buffer
            metrics_log_buffer.append(event_data)
            # SSE (crash-safe — must never kill the metrics loop)
            try:
                publish_event(run_id, "system_metric", event_data)
            except Exception:
                pass

    system_thread = threading.Thread(target=_system_metrics_loop, daemon=True)
    system_thread.start()

    start_time = time.time()

    try:
        # Detect loops and perform loop-aware topological sort
        # (inside try/finally so heartbeat is always cleaned up on failure)
        loops = _detect_loops(nodes, edges)
        order = _topological_sort_with_loops(nodes, edges, loops)

        # Build lookup: which nodes are loop body nodes (skip in main loop)
        loop_body_node_ids: set[str] = set()
        loop_controller_ids: set[str] = set()
        loop_by_controller: dict[str, LoopDefinition] = {}
        for loop_def in loops:
            loop_controller_ids.add(loop_def.controller_id)
            loop_body_node_ids.update(loop_def.body_node_ids)
            loop_by_controller[loop_def.controller_id] = loop_def

        # Resolve config inheritance across the DAG
        _registry = BlockRegistryService()
        _resolved_tuples = resolve_configs(
            nodes, edges, order,
            workspace_config=workspace_config,
            registry=_registry,
        )
        # Post-resolution: auto-fill file_path fields from workspace settings
        inject_workspace_file_paths(_resolved_tuples, nodes, _registry)

        # Compute deterministic Merkle-chain config fingerprints
        config_fps = compute_fingerprints(
            _resolved_tuples, order, edges, _registry, nodes,
        )
        run.config_fingerprints = config_fps

        # Extract just the config dicts for backward-compat with downstream code
        resolved_configs = {
            nid: cfg for nid, (cfg, _src) in _resolved_tuples.items()
        }

        # Compute plan hash for decision log
        import hashlib as _hashlib
        _plan_hasher = _hashlib.sha256()
        for _nid in order:
            _plan_hasher.update(_nid.encode())
            _plan_hasher.update(config_fps.get(_nid, "").encode())
        _plan_hash = _plan_hasher.hexdigest()[:16]

        for idx, node_id in enumerate(order):
            node = node_map.get(node_id)
            if not node:
                continue

            # Skip visual grouping nodes
            if node.get("type") == "groupNode":
                _record_decision(db, run_id, node_id, "skipped", "Visual-only groupNode", plan_hash=_plan_hash)
                continue

            # Skip loop body nodes — they are executed by _execute_loop
            if node_id in loop_body_node_ids:
                _record_decision(
                    db, run_id, node_id, "skipped",
                    "Loop body node — executed by loop controller",
                    cache_fingerprint=config_fps.get(node_id),
                    plan_hash=_plan_hash,
                )
                continue

            # Check for cancellation before each block
            if _check_cancelled(run_id):
                run.status = "cancelled"
                run.error_message = "Cancelled by user"
                run.finished_at = datetime.now(timezone.utc)
                run.duration_seconds = time.time() - start_time
                run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                run.data_fingerprints = all_fingerprints
                live.status = "cancelled"
                db.commit()
                try:
                    publish_event(run_id, "run_cancelled", {
                        "run_id": run_id,
                        "duration": run.duration_seconds,
                        "completed_blocks": idx,
                    })
                except Exception:
                    pass
                return

            # Memory pressure circuit breaker
            is_critical, mem_pct = _check_memory_pressure()
            if is_critical:
                error_msg = (
                    f"Execution halted: Out of Memory Protection triggered. "
                    f"{mem_pct}% of unified memory in use "
                    f"(threshold: {MEMORY_PRESSURE_THRESHOLD}%)."
                )
                run.status = "failed"
                run.error_message = error_msg
                run.finished_at = datetime.now(timezone.utc)
                run.duration_seconds = time.time() - start_time
                run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                run.data_fingerprints = all_fingerprints
                live.status = "failed"
                db.commit()
                try:
                    publish_event(run_id, "run_failed", {
                        "run_id": run_id,
                        "error": error_msg,
                        "memory_percent": mem_pct,
                        "threshold": MEMORY_PRESSURE_THRESHOLD,
                    })
                except Exception:
                    pass
                log_run_failed(run_id, error_msg, node_id)
                return

            node_data = node.get("data", {})
            block_type = node_data.get("type", "")
            config = resolved_configs.get(node_id, node_data.get("config", {}))

            # Strip provenance metadata before passing config to blocks —
            # _inherited is for UI/debugging only, not for block consumption.
            config = {k: v for k, v in config.items() if k != "_inherited"}

            # Apply config migrations for aliased blocks
            original_type = block_type
            if original_type in CONFIG_MIGRATIONS:
                for mk, mv in CONFIG_MIGRATIONS[original_type].items():
                    if mk not in config:
                        config[mk] = mv

            # Update live run
            live.current_block = node_data.get("label", block_type)
            live.current_block_index = idx
            live.block_progress = 0.0
            live.overall_progress = idx / len(nodes)
            db.commit()

            category = node_data.get("category", "flow")

            # Record execution decision
            _node_fp = config_fps.get(node_id)
            if node_id in loop_controller_ids:
                _record_decision(
                    db, run_id, node_id, "execute",
                    f"Loop controller — executing loop body ({block_type})",
                    cache_fingerprint=_node_fp, plan_hash=_plan_hash,
                )
            else:
                _record_decision(
                    db, run_id, node_id, "execute",
                    f"Executing block {block_type} (step {idx + 1}/{len(nodes)})",
                    cache_fingerprint=_node_fp, plan_hash=_plan_hash,
                )

            started_event = {
                "node_id": node_id,
                "block_type": block_type,
                "category": category,
                "index": idx,
                "total": len(nodes),
            }
            try:
                publish_event(run_id, "node_started", started_event)
            except Exception:
                pass
            metrics_log_buffer.append({"type": "node_started", "timestamp": time.time(), **started_event})
            metrics_file.write(json.dumps({"type": "node_started", "timestamp": time.time(), **started_event}) + "\n")
            metrics_file.flush()

            log_block_start(run_id, node_id, block_type, idx, len(nodes))
            block_start_time = time.time()

            # ── Breakpoint check (pre-execution) ──
            # Unconditional breakpoints pause before execution.
            # Conditional breakpoints are checked after execution (see below).
            # Also pause here if "step" mode was set by a previous debug_action.
            should_pause_pre = False
            bp_info = breakpoints.get(node_id)
            if bp_info is True:
                should_pause_pre = True
            else:
                with _debug_lock:
                    if _debug_step_flags.get(run_id, False):
                        should_pause_pre = True
                        _debug_step_flags[run_id] = False

            if should_pause_pre:
                try:
                    _pause_at_breakpoint(
                        run_id, node_id, idx, len(nodes),
                        order, outputs, conditional=False,
                    )
                except BreakpointAbort as abort:
                    run.status = "cancelled"
                    run.error_message = abort.reason
                    run.finished_at = datetime.now(timezone.utc)
                    run.duration_seconds = time.time() - start_time
                    run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                    run.data_fingerprints = all_fingerprints
                    live.status = "cancelled"
                    db.commit()
                    try:
                        publish_event(run_id, "run_cancelled", {
                            "run_id": run_id,
                            "duration": run.duration_seconds,
                            "reason": "debug_abort",
                        })
                    except Exception:
                        pass
                    return

            # Handle loop_controller nodes: execute the full loop
            if node_id in loop_controller_ids:
                loop_def = loop_by_controller[node_id]
                try:
                    await _execute_loop(
                        loop=loop_def,
                        node_map=node_map,
                        edges=edges,
                        outputs=outputs,
                        all_metrics=all_metrics,
                        all_fingerprints=all_fingerprints,
                        run_id=run_id,
                        pipeline_id=pipeline_id,
                        resolved_configs=resolved_configs,
                        metrics_file=metrics_file,
                        metrics_log_buffer=metrics_log_buffer,
                        start_time=start_time,
                        db=db,
                        live=live,
                        breakpoints=breakpoints,
                    )
                except BreakpointAbort as abort:
                    run.status = "cancelled"
                    run.error_message = abort.reason
                    run.finished_at = datetime.now(timezone.utc)
                    run.duration_seconds = time.time() - start_time
                    run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                    run.data_fingerprints = all_fingerprints
                    live.status = "cancelled"
                    db.commit()
                    try:
                        publish_event(run_id, "run_cancelled", {
                            "run_id": run_id,
                            "duration": run.duration_seconds,
                            "reason": "debug_abort",
                        })
                    except Exception:
                        pass
                    return
                except InterruptedError:
                    run.status = "cancelled"
                    run.error_message = "Cancelled by user"
                    run.finished_at = datetime.now(timezone.utc)
                    run.duration_seconds = time.time() - start_time
                    run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                    run.data_fingerprints = all_fingerprints
                    live.status = "cancelled"
                    db.commit()
                    try:
                        publish_event(run_id, "run_cancelled", {
                            "run_id": run_id,
                            "duration": run.duration_seconds,
                        })
                    except Exception:
                        pass
                    return
                except BlockError as e:
                    log_block_failed(run_id, node_id, block_type, e.message)
                    error_payload = {
                        "node_id": node_id,
                        "error": e.message,
                        "error_type": type(e).__name__,
                        "recoverable": e.recoverable,
                        "details": e.details,
                    }
                    try:
                        publish_event(run_id, "node_failed", error_payload)
                    except Exception:
                        pass
                    run.status = "failed"
                    run.error_message = f"[{type(e).__name__}] {e.message}"
                    run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                    live.status = "failed"
                    db.commit()
                    log_run_failed(run_id, e.message, node_id)
                    return
                except Exception as e:
                    tb = traceback.format_exc()
                    log_block_failed(run_id, node_id, block_type, str(e), tb)
                    try:
                        publish_event(run_id, "node_failed", {"node_id": node_id, "error": str(e)})
                    except Exception:
                        pass
                    run.status = "failed"
                    run.error_message = scrub_traceback(f"Loop {block_type} failed: {str(e)}\n\n{tb}")
                    run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                    run.data_fingerprints = all_fingerprints
                    live.status = "failed"
                    db.commit()
                    _write_error_log(run_id, tb)
                    log_run_failed(run_id, str(e), node_id)
                    return

                # Loop completed — emit node_completed and continue
                node_outputs = outputs.get(node_id, {})
                run.last_heartbeat = datetime.now(timezone.utc)
                run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                db.commit()

                loop_duration_ms = round((time.time() - block_start_time) * 1000)
                log_block_complete(run_id, node_id, block_type, time.time() - block_start_time)
                completed_event = {"node_id": node_id, "index": idx, "duration_ms": loop_duration_ms}
                try:
                    publish_event(run_id, "node_completed", completed_event)
                except Exception:
                    pass
                metrics_log_buffer.append({"type": "node_completed", "timestamp": time.time(), **completed_event})
                metrics_file.write(json.dumps({"type": "node_completed", "timestamp": time.time(), **completed_event}) + "\n")
                metrics_file.flush()
                continue

            # Gather inputs from upstream edges
            # When multiple edges connect to the same target handle, collect values into a list
            node_inputs: dict[str, Any] = {}
            _multi_counts: dict[str, int] = {}
            for edge in edges:
                if edge.get("target") == node_id:
                    src_id = edge.get("source", "")
                    src_handle = edge.get("sourceHandle", "")
                    tgt_handle = edge.get("targetHandle", "")
                    # Resolve aliased output handle IDs from renamed ports
                    if src_id in outputs and src_handle not in outputs[src_id]:
                        src_node = node_map.get(src_id)
                        if src_node:
                            src_type = src_node.get("data", {}).get("type", src_node.get("type", ""))
                            src_handle = resolve_output_handle(src_type, src_handle)
                    if src_id in outputs and src_handle in outputs[src_id]:
                        value = outputs[src_id][src_handle]
                        _multi_counts[tgt_handle] = _multi_counts.get(tgt_handle, 0) + 1
                        if tgt_handle in node_inputs:
                            # Convert single value to list on second connection
                            if _multi_counts[tgt_handle] == 2:
                                node_inputs[tgt_handle] = [node_inputs[tgt_handle], value]
                            else:
                                # Already a list from 3rd connection onward
                                node_inputs[tgt_handle].append(value)
                        else:
                            node_inputs[tgt_handle] = value

            # --- Prepare node: resolve block dir, schema, validation, secrets ---
            try:
                prepared = prepare_node_runtime(
                    node_id=node_id,
                    block_type=block_type,
                    config=config,
                    node_inputs=node_inputs,
                    run_id=run_id,
                    find_block_fn=_find_block_module,
                    resolve_secrets_fn=_resolve_secrets,
                    block_aliases=BLOCK_ALIASES,
                    safe_block_type_re=SAFE_BLOCK_TYPE,
                )
            except RuntimeError:
                prepared = None

            if prepared:
                block_dir = prepared.block_dir
                block_schema = prepared.block_schema
                config = prepared.cleaned_config
                run_dir = prepared.run_dir
                timeout_seconds = prepared.timeout_seconds
                max_retries = prepared.max_retries
                context_cls = prepared.context_cls

                # Apply multi-input aggregation policy
                if block_schema and _multi_counts:
                    node_inputs = apply_multi_input_policy(
                        block_schema, node_inputs, _multi_counts,
                    )

                # Embed block version into config_snapshot for cache validation
                if prepared.block_version:
                    node_data["block_version"] = prepared.block_version

                # Progress commit throttling: commit at most every 2 seconds
                _last_progress_commit = time.time()

                def progress_cb(current, total):
                    nonlocal _last_progress_commit

                    # Check for cancellation in progress callback
                    if _check_cancelled(run_id):
                        raise InterruptedError("Run cancelled by user")

                    progress = current / total if total > 0 else 0
                    live.block_progress = progress
                    live.overall_progress = (idx + progress) / len(nodes)
                    elapsed = time.time() - start_time
                    if progress > 0:
                        live.eta_seconds = (elapsed / ((idx + progress) / len(nodes))) - elapsed

                    now = time.time()
                    if now - _last_progress_commit >= 2.0:
                        db.commit()
                        _last_progress_commit = now

                    try:
                        publish_event(run_id, "node_progress", {
                            "node_id": node_id,
                            "progress": progress,
                            "overall": live.overall_progress,
                            "eta": live.eta_seconds,
                        })
                    except Exception:
                        pass

                def message_cb(msg, explicit_severity=None):
                    if explicit_severity:
                        severity = explicit_severity
                    else:
                        severity = _infer_severity(msg)
                    try:
                        publish_event(run_id, "node_log", {
                            "node_id": node_id, "message": msg, "severity": severity,
                        })
                    except Exception:
                        pass

                def metric_cb(name, value, step):
                    metric_event_obj = create_metric(
                        node_id=node_id,
                        name=name,
                        value=value,
                        category=category,
                        step=step,
                    )
                    event_dict = metric_event_obj.to_dict()

                    all_metrics[f"{block_type}.{name}"] = value

                    try:
                        publish_event(run_id, "metric", event_dict)
                    except Exception:
                        pass
                    # Layer 1: JSONL
                    metrics_file.write(json.dumps(event_dict) + "\n")
                    metrics_file.flush()
                    # Layer 2: buffer
                    metrics_log_buffer.append(event_dict)

                # Check isolation mode from block schema
                isolation_mode = "inprocess"  # default
                if block_schema:
                    execution_cfg = block_schema.get("execution", {})
                    if isinstance(execution_cfg, dict):
                        isolation_mode = execution_cfg.get("isolation", "inprocess")

                # Guard: composite blocks cannot run in subprocess isolation.
                # Sub-pipeline execution requires in-process access to the
                # executor internals (_load_and_run_block, CompositeBlockContext).
                # Fall back gracefully with a warning instead of crashing.
                is_composite = block_schema.get("composite", False) if block_schema else False
                if isolation_mode == "subprocess" and is_composite:
                    import logging as _lg
                    _lg.getLogger("blueprint.executor").warning(
                        "Block '%s' (type=%s) declares execution.isolation=subprocess "
                        "but is also a composite block. Composite blocks require "
                        "in-process execution for sub-pipeline support. "
                        "Falling back to inprocess isolation.",
                        node_id, block_type,
                    )
                    isolation_mode = "inprocess"

                # --- Execute with retry + timeout ---
                try:
                    for attempt in range(max_retries + 1):
                        try:
                            if isolation_mode == "subprocess":
                                node_outputs, data_fingerprints = _run_block_subprocess(
                                    block_type, config, node_inputs,
                                    run_id, node_id,
                                    timeout_seconds=timeout_seconds,
                                    progress_cb=progress_cb,
                                    message_cb=message_cb,
                                )
                            else:
                                node_outputs, data_fingerprints = _load_and_run_block_with_timeout(
                                    block_dir, config, node_inputs, run_dir,
                                    run_id, node_id, progress_cb, message_cb, metric_cb,
                                    timeout_seconds=timeout_seconds,
                                    context_cls=context_cls,
                                )
                            outputs[node_id] = node_outputs
                            if data_fingerprints:
                                all_fingerprints[node_id] = data_fingerprints
                            break  # Success
                        except BlockError as e:
                            if not e.recoverable or attempt == max_retries:
                                raise
                            try:
                                publish_event(run_id, "node_retry", {
                                    "node_id": node_id,
                                    "block_type": block_type,
                                    "attempt": attempt + 1,
                                    "max_retries": max_retries,
                                    "error": e.message,
                                })
                            except Exception:
                                pass
                except InterruptedError:
                    # Cancellation via progress_cb
                    run.status = "cancelled"
                    run.error_message = "Cancelled by user"
                    run.finished_at = datetime.now(timezone.utc)
                    run.duration_seconds = time.time() - start_time
                    run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                    run.data_fingerprints = all_fingerprints
                    live.status = "cancelled"
                    db.commit()
                    try:
                        publish_event(run_id, "run_cancelled", {
                            "run_id": run_id,
                            "duration": run.duration_seconds,
                        })
                    except Exception:
                        pass
                    return
                except BlockError as e:
                    log_block_failed(run_id, node_id, block_type, e.message)
                    error_payload = {
                        "node_id": node_id,
                        "error": e.message,
                        "error_type": type(e).__name__,
                        "recoverable": e.recoverable,
                        "details": e.details,
                    }
                    if isinstance(e, BlockConfigError):
                        error_payload["config_field"] = e.field
                    try:
                        publish_event(run_id, "node_failed", error_payload)
                    except Exception:
                        pass
                    run.status = "failed"
                    run.error_message = f"[{type(e).__name__}] {e.message}"
                    if e.details:
                        run.error_message += f"\n\nDetails: {e.details}"
                    run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                    live.status = "failed"
                    db.commit()
                    log_run_failed(run_id, e.message, node_id)
                    return
                except Exception as e:
                    tb = traceback.format_exc()
                    # Classify the error for structured diagnostics
                    from .error_classifier import classify_error
                    classified = classify_error(e, block_type=block_type)
                    classified_msg = f"[{classified.title}] {classified.message}"
                    classified_action = classified.action

                    log_block_failed(run_id, node_id, block_type, str(e), tb)
                    try:
                        publish_event(run_id, "node_failed", {
                            "node_id": node_id,
                            "error": classified_msg,
                            "classified": classified.to_dict(),
                        })
                    except Exception:
                        pass
                    run.status = "failed"
                    run.error_message = scrub_traceback(f"{classified_msg}\nAction: {classified_action}\n\n{tb}")
                    run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                    run.data_fingerprints = all_fingerprints
                    live.status = "failed"
                    db.commit()
                    _write_error_log(run_id, tb)
                    log_run_failed(run_id, str(e), node_id)
                    return
            else:
                error_msg = f"Block type '{block_type}' not found. No run.py available."
                log_block_failed(run_id, node_id, block_type, error_msg)
                try:
                    publish_event(run_id, "node_failed", {"node_id": node_id, "error": f"Block type '{block_type}' not found"})
                except Exception:
                    pass
                run.status = "failed"
                run.error_message = error_msg
                run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                run.data_fingerprints = all_fingerprints
                live.status = "failed"
                db.commit()
                log_run_failed(run_id, error_msg, node_id)
                return

            # Cache block outputs as typed artifacts with SHA-256 verification (best-effort)
            _cache_block_outputs(node_id, run_id, node_outputs, block_schema, db)

            # Register artifacts produced by this block (best-effort, never crashes)
            artifact_ids: list[str] = []
            try:
                artifact_ids = register_block_artifacts(
                    pipeline_id=pipeline_id,
                    run_id=run_id,
                    node_id=node_id,
                    block_type=block_type,
                    outputs=node_outputs,
                    run_dir=run_dir,
                )
            except Exception:
                pass

            # Determine primary output data type from block schema for canvas indicators
            primary_output_type = None
            try:
                if block_schema and block_schema.get("outputs"):
                    primary_output_type = block_schema["outputs"][0].get("data_type")
            except Exception:
                pass

            # ── Conditional breakpoint check (post-execution) ──
            bp_info_post = breakpoints.get(node_id)
            if isinstance(bp_info_post, dict):
                node_outs = outputs.get(node_id, {})
                condition_met = evaluate_breakpoint_condition(bp_info_post, node_outs)
                if condition_met:
                    try:
                        _pause_at_breakpoint(
                            run_id, node_id, idx, len(nodes),
                            order, outputs, conditional=True,
                        )
                    except BreakpointAbort as abort:
                        run.status = "cancelled"
                        run.error_message = abort.reason
                        run.finished_at = datetime.now(timezone.utc)
                        run.duration_seconds = time.time() - start_time
                        run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                        run.data_fingerprints = all_fingerprints
                        live.status = "cancelled"
                        db.commit()
                        try:
                            publish_event(run_id, "run_cancelled", {
                                "run_id": run_id,
                                "duration": run.duration_seconds,
                                "reason": "debug_abort",
                            })
                        except Exception:
                            pass
                        return

            # Heartbeat after each block completes
            run.last_heartbeat = datetime.now(timezone.utc)
            # Save partial outputs after each block (preview-only, not authoritative)
            run.outputs_snapshot = _safe_outputs_snapshot(outputs)
            db.commit()

            # Publish outputs so frontend can display them
            safe_outputs = {}
            for k, v in node_outputs.items():
                try:
                    json.dumps(v)
                    safe_outputs[k] = v if not isinstance(v, str) or len(v) < 200 else v[:200] + '...'
                except Exception:
                    safe_outputs[k] = str(v)[:200]
            try:
                publish_event(run_id, "node_output", {"node_id": node_id, "outputs": safe_outputs})
            except Exception:
                pass

            log_block_complete(run_id, node_id, block_type, time.time() - block_start_time)

            block_duration_ms = round((time.time() - block_start_time) * 1000)
            completed_event = {
                "node_id": node_id,
                "index": idx,
                "primary_output_type": primary_output_type,
                "artifact_count": len(artifact_ids),
                "duration_ms": block_duration_ms,
            }
            try:
                publish_event(run_id, "node_completed", completed_event)
            except Exception:
                pass
            metrics_log_buffer.append({"type": "node_completed", "timestamp": time.time(), **completed_event})
            metrics_file.write(json.dumps({"type": "node_completed", "timestamp": time.time(), **completed_event}) + "\n")
            metrics_file.flush()

            # Layer 2: 60s checkpoint to SQLite
            now = time.time()
            if now - last_checkpoint_time >= CHECKPOINT_INTERVAL:
                run.metrics_log = list(metrics_log_buffer)
                _safe_commit(db)
                last_checkpoint_time = now

        # Pipeline complete
        run.status = "complete"
        run.finished_at = datetime.now(timezone.utc)
        run.duration_seconds = time.time() - start_time
        run.metrics = all_metrics
        run.outputs_snapshot = _safe_outputs_snapshot(outputs)
        run.metrics_log = list(metrics_log_buffer)
        run.data_fingerprints = all_fingerprints
        live.status = "complete"
        live.overall_progress = 1.0
        db.commit()

        # Auto-generate run export JSON (never crashes execution)
        try:
            from .run_export import generate_run_export
            export = generate_run_export(run, ARTIFACTS_DIR)
            export_path = ARTIFACTS_DIR / run_id / "run-export.json"
            export_path.parent.mkdir(parents=True, exist_ok=True)
            with open(export_path, "w") as f:
                json.dump(export, f, indent=2)
        except Exception:
            pass

        log_run_complete(run_id, run.duration_seconds, all_metrics)

        # Auto-lifecycle: update phase/project counters (never crashes execution)
        try:
            from ..services.project_lifecycle import on_run_completed
            on_run_completed(run_id, db)
        except Exception:
            pass

        try:
            publish_event(run_id, "run_completed", {
                "run_id": run_id,
                "duration": run.duration_seconds,
                "metrics": all_metrics,
            })
        except Exception:
            pass

    except Exception as e:
        tb = traceback.format_exc()
        run.status = "failed"
        run.error_message = scrub_traceback(f"{str(e)}\n\n{tb}")
        run.finished_at = datetime.now(timezone.utc)
        run.duration_seconds = time.time() - start_time
        run.outputs_snapshot = _safe_outputs_snapshot(outputs)
        run.metrics_log = list(metrics_log_buffer)
        run.data_fingerprints = all_fingerprints
        live.status = "failed"
        db.commit()
        _write_error_log(run_id, tb)
        log_run_failed(run_id, str(e))

        # Auto-lifecycle: update counts only on failure (never crashes execution)
        try:
            from ..services.project_lifecycle import on_run_failed
            on_run_failed(run_id, db)
        except Exception:
            pass

        try:
            publish_event(run_id, "run_failed", {"run_id": run_id, "error": str(e)})
        except Exception:
            pass
    finally:
        # Release the active-run semaphore
        _active_run_semaphore.release()
        # Clean up cancel event
        with _cancel_lock:
            _cancel_events.pop(run_id, None)
        # Clean up debug state
        with _debug_lock:
            _debug_resume_events.pop(run_id, None)
            _debug_step_flags.pop(run_id, None)
            _debug_abort_flags.pop(run_id, None)
        # Stop heartbeat thread
        heartbeat_stop.set()
        # Stop system metrics publisher
        system_metrics_stop.set()
        # Close JSONL file
        try:
            metrics_file.close()
        except Exception:
            pass


def _safe_outputs_snapshot(outputs: dict[str, dict[str, Any]]) -> dict:
    """Create a JSON-safe snapshot of outputs for persistence."""
    snapshot = {}
    for node_id, node_outputs in outputs.items():
        safe = {}
        for k, v in node_outputs.items():
            try:
                json.dumps(v)
                safe[k] = v if not isinstance(v, str) or len(v) < 500 else v[:500] + '...'
            except Exception:
                safe[k] = str(v)[:500]
        snapshot[node_id] = safe
    return snapshot


def _write_error_log(run_id: str, tb: str):
    """Write traceback to {ARTIFACTS_DIR}/{run_id}/error.log."""
    try:
        error_dir = ARTIFACTS_DIR / run_id
        error_dir.mkdir(parents=True, exist_ok=True)
        (error_dir / "error.log").write_text(scrub_traceback(tb))
    except Exception:
        pass
