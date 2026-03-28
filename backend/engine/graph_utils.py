"""
Graph Utilities — canonical graph algorithms for the unified planner.

Provides topological sort (Kahn's), loop/cycle detection (Tarjan's SCC),
independent subgraph discovery (Union-Find), and an orchestrating
``plan_execution_order`` that composes the primitives correctly.

All functions accept the same node/edge dict format used throughout
Blueprint's pipeline engine.

Determinism guarantee
---------------------
Every function in this module produces identical output given identical input,
regardless of dict iteration order or platform.  This is achieved by:

1. Sorting node ID lists before any traversal.
2. Sorting adjacency lists before passing them to DFS / BFS.
3. Sorting SCC member lists in the output.

This means the planner can hash the output for cache keys and get
reproducible plan_hash values across runs.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass
from typing import Any

from .planner_models import LoopBoundary


# ---------------------------------------------------------------------------
# Topological Sort (Kahn's algorithm)
# ---------------------------------------------------------------------------

def topological_sort(
    nodes: list[dict],
    edges: list[dict],
    loop_back_edges: set[tuple[str, str]] | None = None,
) -> list[str]:
    """Return node IDs in topological (execution) order using Kahn's algorithm.

    Parameters
    ----------
    nodes : list[dict]
        Each dict must contain an ``"id"`` key.
    edges : list[dict]
        Each dict must contain ``"source"`` and ``"target"`` keys.
    loop_back_edges : set of (source, target) tuples, optional
        Edges to exclude from the DAG (e.g. feedback edges in loops).
        Excluding these allows the rest of the graph to be sorted as a DAG.

    Returns
    -------
    list[str]
        Node IDs in a deterministic topological order.

    Raises
    ------
    ValueError
        If the graph (after excluding *loop_back_edges*) still contains a cycle.
    """
    if loop_back_edges is None:
        loop_back_edges = set()

    in_degree: dict[str, int] = {n["id"]: 0 for n in nodes}
    adj: dict[str, list[str]] = {n["id"]: [] for n in nodes}

    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if (src, tgt) in loop_back_edges:
            continue
        if src in adj and tgt in in_degree:
            adj[src].append(tgt)
            in_degree[tgt] += 1

    # Seed the queue with zero-in-degree nodes in sorted order for determinism
    queue = collections.deque(
        nid for nid, deg in sorted(in_degree.items()) if deg == 0
    )
    order: list[str] = []

    while queue:
        nid = queue.popleft()
        order.append(nid)
        # Process neighbours in sorted order so tie-breaking is deterministic
        for neighbor in sorted(adj.get(nid, [])):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(in_degree):
        remaining = set(in_degree) - set(order)
        raise ValueError(
            f"Graph contains a cycle (after excluding loop back-edges). "
            f"Nodes involved: {sorted(remaining)}"
        )

    return order


# ---------------------------------------------------------------------------
# Loop / Cycle Detection (Tarjan's SCC — fully deterministic)
# ---------------------------------------------------------------------------

def _tarjan_scc(
    node_ids: list[str],
    adj: dict[str, list[str]],
) -> list[list[str]]:
    """Iterative Tarjan's algorithm returning strongly connected components.

    Determinism contract:
    - ``node_ids`` MUST be pre-sorted by the caller.
    - ``adj`` values MUST be pre-sorted lists by the caller.
    These two preconditions guarantee that the DFS visits nodes and
    neighbours in a fixed lexicographic order, making the resulting
    SCC list fully deterministic.

    Returns SCCs with members sorted lexicographically.  SCCs themselves
    are returned in the order they are completed (reverse topological
    order of the condensation DAG), which is also deterministic given
    the sorted inputs.
    """
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    index_map: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    result: list[list[str]] = []

    for node in node_ids:
        if node in index_map:
            continue

        # Iterative DFS using an explicit work stack.
        # Each frame is (node, iterator_over_sorted_neighbours).
        work: list[tuple[str, Any]] = []
        work.append((node, iter(adj.get(node, []))))
        index_map[node] = lowlink[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack.add(node)

        while work:
            v, neighbours = work[-1]
            pushed = False
            for w in neighbours:
                if w not in index_map:
                    # Tree edge — push w
                    index_map[w] = lowlink[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(adj.get(w, []))))
                    pushed = True
                    break
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], index_map[w])

            if pushed:
                continue

            # All neighbours visited — check if v is SCC root
            if lowlink[v] == index_map[v]:
                scc: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    scc.append(w)
                    if w == v:
                        break
                # Sort members for deterministic output
                scc.sort()
                result.append(scc)

            # Pop frame and propagate lowlink to parent
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[v])

    return result


def detect_loops(
    nodes: list[dict],
    edges: list[dict],
) -> tuple[list[LoopBoundary], list[list[str]]]:
    """Detect valid loops and illegal cycles in the pipeline graph.

    Uses Tarjan's SCC algorithm.  For each SCC with >1 node:

    - If exactly one node has ``block_type == "loop_controller"``, it is
      treated as a valid loop.  A :class:`LoopBoundary` is created with:

      * ``body_node_ids`` — SCC nodes minus the controller (sorted).
      * ``feedback_edges`` — **all** edges from body nodes back to the
        controller.  A loop body may branch (e.g. text path + metrics
        path) with multiple paths converging back; every such edge must
        be captured so ``topological_sort`` can exclude all of them.
      * ``max_iterations`` — from controller config (default 100).

    - Otherwise it is classified as an illegal cycle.

    Returns
    -------
    (valid_loops, illegal_cycles)
        ``valid_loops`` is a list of :class:`LoopBoundary`, sorted by
        ``controller_node_id`` for determinism.
        ``illegal_cycles`` is a list of sorted lists of node IDs,
        sorted by first element for determinism.
    """
    node_map: dict[str, dict] = {n["id"]: n for n in nodes}
    node_ids = sorted(node_map.keys())

    # Build adjacency with sorted neighbour lists for deterministic Tarjan's
    adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in adj and tgt in adj:
            adj[src].append(tgt)
    for nid in adj:
        adj[nid] = sorted(adj[nid])

    sccs = _tarjan_scc(node_ids, adj)

    valid_loops: list[LoopBoundary] = []
    illegal_cycles: list[list[str]] = []

    for scc in sccs:
        if len(scc) <= 1:
            continue  # Not a cycle

        # Identify loop controllers in this SCC
        scc_set = set(scc)
        controllers = []
        for nid in scc:  # scc is already sorted by _tarjan_scc
            node = node_map[nid]
            block_type = node.get("data", {}).get("type", node.get("type", ""))
            if block_type == "loop_controller":
                controllers.append(nid)

        if len(controllers) != 1:
            # No controller or multiple controllers → illegal cycle
            illegal_cycles.append(scc)  # already sorted
            continue

        controller_id = controllers[0]
        body_ids = sorted(nid for nid in scc if nid != controller_id)

        # Collect ALL feedback edges: every edge from a body node back to
        # the controller.  A branching loop body may produce multiple such
        # edges (e.g. text output + metrics output both feeding back).
        # Sorted by (source, target) for determinism.
        feedback_edges: list[tuple[str, str]] = []
        for edge in edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            if tgt == controller_id and src in scc_set and src != controller_id:
                feedback_edges.append((src, tgt))
        feedback_edges.sort()

        if not feedback_edges:
            # Shouldn't happen in a valid SCC, but be defensive
            illegal_cycles.append(scc)
            continue

        # Extract max_iterations from controller config
        controller_node = node_map[controller_id]
        controller_config = controller_node.get("data", {}).get("config", {})
        max_iterations = controller_config.get("iterations", 100)

        valid_loops.append(
            LoopBoundary(
                controller_node_id=controller_id,
                body_node_ids=tuple(body_ids),
                feedback_edges=tuple(feedback_edges),
                max_iterations=max_iterations,
            )
        )

    # Sort outputs for determinism
    valid_loops.sort(key=lambda lb: lb.controller_node_id)
    illegal_cycles.sort(key=lambda c: c[0] if c else "")

    return valid_loops, illegal_cycles


# ---------------------------------------------------------------------------
# Orchestrator — single entry point for the planner
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExecutionOrderResult:
    """Result of ``plan_execution_order``: everything the planner needs
    to build an ``ExecutionPlan`` without calling low-level graph functions.
    """

    execution_order: tuple[str, ...]
    loops: tuple[LoopBoundary, ...]
    illegal_cycles: tuple[tuple[str, ...], ...]
    feedback_edges: frozenset[tuple[str, str]]


def plan_execution_order(
    nodes: list[dict],
    edges: list[dict],
) -> ExecutionOrderResult:
    """Orchestrate loop detection and topological sort in the correct order.

    This is the **single entry point** that the planner (prompt 1.5) should
    call.  It:

    1. Runs ``detect_loops`` to find valid loops and illegal cycles via
       Tarjan's SCC.
    2. Collects **all** feedback edges from every valid loop.
    3. Passes those feedback edges to ``topological_sort`` so the rest of
       the graph can be sorted as a DAG.
    4. Returns the execution order, loops, illegal cycles, and the set of
       feedback edges (so the planner can annotate ``ResolvedNode.in_loop``
       and build ``LoopBoundary`` objects).

    If there are illegal cycles, ``topological_sort`` will still be
    attempted (with valid-loop feedback edges excluded).  If the residual
    graph is still cyclic (because the illegal cycles remain), a
    ``ValueError`` will propagate — the planner should catch it and
    report the illegal cycles to the user.

    Parameters
    ----------
    nodes : list[dict]
        Pipeline nodes (each with ``"id"`` and ``"data"`` keys).
    edges : list[dict]
        Pipeline edges (each with ``"source"`` and ``"target"`` keys).

    Returns
    -------
    ExecutionOrderResult
    """
    valid_loops, illegal_cycles = detect_loops(nodes, edges)

    # Collect all feedback edges from all valid loops
    all_feedback_edges: set[tuple[str, str]] = set()
    for loop in valid_loops:
        for fe in loop.feedback_edges:
            all_feedback_edges.add(fe)

    order = topological_sort(nodes, edges, loop_back_edges=all_feedback_edges)

    return ExecutionOrderResult(
        execution_order=tuple(order),
        loops=tuple(valid_loops),
        illegal_cycles=tuple(tuple(c) for c in illegal_cycles),
        feedback_edges=frozenset(all_feedback_edges),
    )


# ---------------------------------------------------------------------------
# Independent Subgraph Discovery (Union-Find / Disjoint Set)
# ---------------------------------------------------------------------------

class _UnionFind:
    """Simple Union-Find (disjoint set) with path compression and union by rank."""

    __slots__ = ("parent", "rank")

    def __init__(self, elements: list[str]) -> None:
        self.parent: dict[str, str] = {e: e for e in elements}
        self.rank: dict[str, int] = {e: 0 for e in elements}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path compression
            x = self.parent[x]
        return x

    def union(self, x: str, y: str) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        # Union by rank
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1


def find_independent_subgraphs(
    nodes: list[dict],
    edges: list[dict],
) -> list[list[str]]:
    """Partition the graph into independent (disconnected) subgraphs.

    Uses Union-Find.  Returns a list of groups, where each group is a sorted
    list of node IDs.  Groups are sorted by their first element for
    deterministic output.
    """
    node_ids = [n["id"] for n in nodes]
    if not node_ids:
        return []

    uf = _UnionFind(node_ids)

    node_set = set(node_ids)
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in node_set and tgt in node_set:
            uf.union(src, tgt)

    groups: dict[str, list[str]] = {}
    for nid in node_ids:
        root = uf.find(nid)
        groups.setdefault(root, []).append(nid)

    # Sort each group internally and sort groups by first element
    result = [sorted(g) for g in groups.values()]
    result.sort(key=lambda g: g[0])
    return result
