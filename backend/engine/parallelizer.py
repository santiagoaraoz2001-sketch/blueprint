"""Parallel execution planner — analyse a pipeline DAG and schedule
independent branches to run concurrently based on hardware capabilities.

The planner works in two passes:

1. **DAG analysis** — topological sort, then group nodes into *levels*
   where every node in a level is independent of nodes in the same level.
2. **Resource-aware scheduling** — given hardware capabilities (cores,
   GPU count, memory) cap the concurrency per level so we don't OOM.

The planner produces a *schedule*: a list of stages, each stage being a
list of node IDs that can execute in parallel.

Usage
-----
>>> schedule = build_schedule(nodes, edges, hardware_profile)
>>> for stage in schedule:
...     # run nodes in `stage` concurrently
...     await asyncio.gather(*[run_node(nid) for nid in stage])
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Stage = list[str]  # node-IDs that can run in the same stage
Schedule = list[Stage]

# Category → rough estimate of memory needed per block (GB)
_MEMORY_COST: dict[str, float] = {
    "training": 8.0,
    "inference": 4.0,
    "evaluation": 4.0,
    "merge": 6.0,
    "agents": 2.0,
    "data": 1.0,
    "output": 0.5,
    "flow": 0.1,
}

# Category → whether the block typically wants a GPU
_GPU_INTENSIVE: set[str] = {"training", "inference", "evaluation", "merge"}


# ---------------------------------------------------------------------------
# DAG helpers
# ---------------------------------------------------------------------------

def _compute_levels(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> list[Stage]:
    """BFS-based level assignment (Kahn's algorithm variant).

    Returns a list of *stages* where each stage contains node-IDs whose
    dependencies have already been satisfied by earlier stages.
    """
    node_ids = [n["id"] for n in nodes]
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
    children: dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in in_degree and tgt in in_degree:
            children[src].append(tgt)
            in_degree[tgt] += 1

    # Roots — nodes with no incoming edges
    queue: deque[tuple[str, int]] = deque()
    for nid in node_ids:
        if in_degree[nid] == 0:
            queue.append((nid, 0))

    level_map: dict[str, int] = {}

    while queue:
        nid, level = queue.popleft()
        level_map[nid] = level
        for child in children[nid]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append((child, level + 1))

    # Group by level
    max_level = max(level_map.values(), default=0)
    stages: list[Stage] = [[] for _ in range(max_level + 1)]
    for nid, lvl in level_map.items():
        stages[lvl].append(nid)

    return stages


def _node_category(node: dict[str, Any]) -> str:
    """Extract the category string from a pipeline node."""
    return (node.get("data") or {}).get("category", "flow")


def _node_memory_cost(node: dict[str, Any]) -> float:
    """Estimate memory cost of a single node."""
    cat = _node_category(node)
    return _MEMORY_COST.get(cat, 1.0)


def _node_needs_gpu(node: dict[str, Any]) -> bool:
    cat = _node_category(node)
    return cat in _GPU_INTENSIVE


# ---------------------------------------------------------------------------
# Resource-aware scheduling
# ---------------------------------------------------------------------------

def _partition_stage(
    stage_node_ids: list[str],
    node_map: dict[str, dict[str, Any]],
    *,
    available_memory_gb: float,
    gpu_slots: int,
    max_concurrency: int,
) -> list[Stage]:
    """Split a single level into sub-stages so resource limits aren't exceeded.

    We use a simple greedy bin-packing:
    * Walk through nodes in the stage.
    * Accumulate memory cost; if adding a node would exceed the budget or
      gpu slot limit or the max concurrency, start a new sub-stage.

    Returns one or more sub-stages.
    """
    if not stage_node_ids:
        return []

    sub_stages: list[Stage] = []
    current: Stage = []
    current_mem = 0.0
    current_gpu = 0

    for nid in stage_node_ids:
        node = node_map.get(nid)
        if node is None:
            continue

        mem = _node_memory_cost(node)
        gpu = 1 if _node_needs_gpu(node) else 0

        # Check if adding this node would overflow resources
        would_exceed_mem = (current_mem + mem) > available_memory_gb
        would_exceed_gpu = gpu_slots > 0 and (current_gpu + gpu) > gpu_slots
        would_exceed_conc = len(current) >= max_concurrency

        if current and (would_exceed_mem or would_exceed_gpu or would_exceed_conc):
            sub_stages.append(current)
            current = []
            current_mem = 0.0
            current_gpu = 0

        current.append(nid)
        current_mem += mem
        current_gpu += gpu

    if current:
        sub_stages.append(current)

    return sub_stages


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_schedule(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    hardware_profile: dict[str, Any] | None = None,
) -> Schedule:
    """Build a resource-aware parallel schedule for a pipeline.

    Parameters
    ----------
    nodes : list[dict]
        ReactFlow node dicts (must have ``id`` and ``data``).
    edges : list[dict]
        ReactFlow edge dicts (``source`` / ``target``).
    hardware_profile : dict, optional
        Output of ``get_hardware_profile()`` from :mod:`backend.utils.hardware`.
        If *None*, a conservative default is assumed.

    Returns
    -------
    Schedule
        A list of stages.  Each stage is a list of node IDs that can be
        executed concurrently.
    """
    if not nodes:
        return []

    # --- resolve hardware constraints ------------------------------------
    hw = hardware_profile or {}
    ram_gb = (hw.get("ram") or {}).get("total_gb", 16)
    gpus = hw.get("gpu") or []
    cpu_threads = (hw.get("cpu") or {}).get("threads", 4)

    max_vram = max((g.get("vram_gb", 0) for g in gpus), default=0)
    available_memory = max(max_vram, ram_gb * 0.7)  # unified memory heuristic
    gpu_count = sum(1 for g in gpus if g.get("type") in ("metal", "cuda", "rocm"))

    # Keep concurrency reasonable: at most threads/2 but at least 1
    max_concurrency = max(1, min(cpu_threads // 2, 8))

    # --- compute level-based stages then partition them ------------------
    node_map = {n["id"]: n for n in nodes}
    raw_stages = _compute_levels(nodes, edges)

    schedule: Schedule = []
    for stage_ids in raw_stages:
        sub_stages = _partition_stage(
            stage_ids,
            node_map,
            available_memory_gb=available_memory,
            gpu_slots=gpu_count or 1,
            max_concurrency=max_concurrency,
        )
        schedule.extend(sub_stages)

    return schedule


def explain_schedule(
    schedule: Schedule,
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return a human-readable summary of a schedule for the frontend.

    Each entry includes:
    * ``stage`` — 0-based stage index
    * ``node_ids`` — list of node IDs in this stage
    * ``labels`` — list of human-readable labels
    * ``parallel`` — whether the stage runs >1 node concurrently
    """
    node_map = {n["id"]: n for n in nodes}
    result = []
    for idx, stage in enumerate(schedule):
        labels = []
        for nid in stage:
            n = node_map.get(nid)
            if n:
                labels.append((n.get("data") or {}).get("label", nid))
            else:
                labels.append(nid)
        result.append({
            "stage": idx,
            "node_ids": stage,
            "labels": labels,
            "parallel": len(stage) > 1,
        })
    return result
