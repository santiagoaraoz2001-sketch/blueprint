"""Tests for backend.engine.graph_utils — topological sort, loop detection, subgraphs,
and the plan_execution_order orchestrator.

Test organisation mirrors the three risks resolved in this module:

1. **Determinism** — Tarjan's SCC and topo sort produce identical output
   regardless of input dict iteration order or edge insertion order.
2. **Orchestration** — ``plan_execution_order`` correctly wires detect_loops
   into topological_sort so callers never have to do it manually.
3. **Multi-feedback** — Loops with multiple feedback edges (branching loop
   bodies) are fully captured, and all such edges are excluded from the DAG.
"""

import pytest

from backend.engine.graph_utils import (
    ExecutionOrderResult,
    detect_loops,
    find_independent_subgraphs,
    plan_execution_order,
    topological_sort,
)
from backend.engine.planner_models import LoopBoundary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(nid: str, block_type: str = "generic", config: dict | None = None) -> dict:
    """Create a minimal node dict matching Blueprint's pipeline format."""
    return {
        "id": nid,
        "data": {
            "type": block_type,
            "config": config or {},
        },
    }


def _edge(src: str, tgt: str) -> dict:
    return {"source": src, "target": tgt}


# ---------------------------------------------------------------------------
# Topological Sort
# ---------------------------------------------------------------------------

class TestTopologicalSort:
    def test_simple_dag(self):
        """A -> B -> C should produce [A, B, C]."""
        nodes = [_node("A"), _node("B"), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C")]
        order = topological_sort(nodes, edges)
        assert order == ["A", "B", "C"]

    def test_branching_dag(self):
        """A -> [B, C] -> D: A first, D last, B and C in the middle."""
        nodes = [_node("A"), _node("B"), _node("C"), _node("D")]
        edges = [
            _edge("A", "B"),
            _edge("A", "C"),
            _edge("B", "D"),
            _edge("C", "D"),
        ]
        order = topological_sort(nodes, edges)
        assert order[0] == "A"
        assert order[-1] == "D"
        assert set(order[1:3]) == {"B", "C"}

    def test_single_node(self):
        nodes = [_node("X")]
        order = topological_sort(nodes, [])
        assert order == ["X"]

    def test_no_nodes(self):
        order = topological_sort([], [])
        assert order == []

    def test_diamond_dag(self):
        """A -> B, A -> C, B -> D, C -> D."""
        nodes = [_node("A"), _node("B"), _node("C"), _node("D")]
        edges = [
            _edge("A", "B"),
            _edge("A", "C"),
            _edge("B", "D"),
            _edge("C", "D"),
        ]
        order = topological_sort(nodes, edges)
        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")

    def test_loop_back_edges_excluded(self):
        """With a back-edge excluded, the graph is a valid DAG."""
        nodes = [_node("A"), _node("B"), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C"), _edge("C", "A")]
        order = topological_sort(nodes, edges, loop_back_edges={("C", "A")})
        assert order == ["A", "B", "C"]

    def test_cycle_raises_value_error(self):
        """A true cycle (no back-edge exclusion) raises ValueError."""
        nodes = [_node("A"), _node("B"), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C"), _edge("C", "A")]
        with pytest.raises(ValueError, match="cycle"):
            topological_sort(nodes, edges)

    def test_disconnected_nodes_all_returned(self):
        """Disconnected nodes still appear in the output."""
        nodes = [_node("A"), _node("B"), _node("C")]
        edges = [_edge("A", "B")]
        order = topological_sort(nodes, edges)
        assert set(order) == {"A", "B", "C"}
        assert order.index("A") < order.index("B")

    def test_multiple_back_edges_excluded(self):
        """Multiple loop back-edges can be excluded simultaneously."""
        # Two separate loops sharing no nodes
        nodes = [_node(x) for x in "ABCDE"]
        edges = [
            _edge("A", "B"), _edge("B", "A"),  # loop 1
            _edge("C", "D"), _edge("D", "E"), _edge("E", "C"),  # loop 2
        ]
        order = topological_sort(
            nodes, edges,
            loop_back_edges={("B", "A"), ("E", "C")},
        )
        assert set(order) == {"A", "B", "C", "D", "E"}
        assert order.index("A") < order.index("B")
        assert order.index("C") < order.index("D")
        assert order.index("D") < order.index("E")


# ---------------------------------------------------------------------------
# Determinism (Risk 1)
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Verify that output is identical regardless of input ordering."""

    def test_topo_sort_deterministic_across_node_orders(self):
        """Topo sort gives the same result whether nodes are given A-Z or Z-A."""
        edges = [_edge("A", "B"), _edge("A", "C"), _edge("B", "D"), _edge("C", "D")]
        nodes_fwd = [_node("A"), _node("B"), _node("C"), _node("D")]
        nodes_rev = list(reversed(nodes_fwd))
        assert topological_sort(nodes_fwd, edges) == topological_sort(nodes_rev, edges)

    def test_topo_sort_deterministic_across_edge_orders(self):
        """Topo sort gives the same result regardless of edge insertion order."""
        nodes = [_node("A"), _node("B"), _node("C"), _node("D")]
        edges_v1 = [_edge("A", "B"), _edge("A", "C"), _edge("B", "D"), _edge("C", "D")]
        edges_v2 = [_edge("C", "D"), _edge("A", "C"), _edge("B", "D"), _edge("A", "B")]
        assert topological_sort(nodes, edges_v1) == topological_sort(nodes, edges_v2)

    def test_detect_loops_deterministic_across_node_orders(self):
        """detect_loops gives the same LoopBoundary regardless of node order."""
        edges = [_edge("ctrl", "B"), _edge("B", "C"), _edge("C", "ctrl")]
        nodes_v1 = [
            _node("ctrl", block_type="loop_controller", config={"iterations": 5}),
            _node("B"),
            _node("C"),
        ]
        nodes_v2 = [_node("C"), nodes_v1[0], _node("B")]
        loops_v1, _ = detect_loops(nodes_v1, edges)
        loops_v2, _ = detect_loops(nodes_v2, edges)
        assert loops_v1 == loops_v2

    def test_detect_loops_deterministic_across_edge_orders(self):
        """detect_loops gives the same result regardless of edge order."""
        nodes = [
            _node("ctrl", block_type="loop_controller"),
            _node("B"),
        ]
        edges_v1 = [_edge("ctrl", "B"), _edge("B", "ctrl")]
        edges_v2 = [_edge("B", "ctrl"), _edge("ctrl", "B")]
        loops_v1, _ = detect_loops(nodes, edges_v1)
        loops_v2, _ = detect_loops(nodes, edges_v2)
        assert loops_v1 == loops_v2

    def test_scc_members_sorted(self):
        """SCC body_node_ids are always sorted regardless of discovery order."""
        nodes = [
            _node("ctrl", block_type="loop_controller"),
            _node("Z"),
            _node("A"),
            _node("M"),
        ]
        # Z -> A -> M -> ctrl -> Z (all in SCC with ctrl)
        edges = [
            _edge("ctrl", "Z"),
            _edge("Z", "A"),
            _edge("A", "M"),
            _edge("M", "ctrl"),
        ]
        loops, _ = detect_loops(nodes, edges)
        assert len(loops) == 1
        assert loops[0].body_node_ids == ("A", "M", "Z")  # sorted

    def test_plan_execution_order_deterministic(self):
        """Full orchestrator produces identical results across input orderings."""
        ctrl = _node("ctrl", block_type="loop_controller", config={"iterations": 3})
        nodes_v1 = [_node("start"), ctrl, _node("body"), _node("end")]
        nodes_v2 = [_node("end"), _node("body"), ctrl, _node("start")]
        edges = [
            _edge("start", "ctrl"),
            _edge("ctrl", "body"),
            _edge("body", "ctrl"),
            _edge("ctrl", "end"),
        ]
        r1 = plan_execution_order(nodes_v1, edges)
        r2 = plan_execution_order(nodes_v2, edges)
        assert r1.execution_order == r2.execution_order
        assert r1.loops == r2.loops
        assert r1.feedback_edges == r2.feedback_edges


# ---------------------------------------------------------------------------
# Loop / Cycle Detection
# ---------------------------------------------------------------------------

class TestDetectLoops:
    def test_valid_loop(self):
        """A -> loop_controller -> B -> loop_controller forms a valid loop."""
        nodes = [
            _node("A"),
            _node("loop_controller", block_type="loop_controller", config={"iterations": 50}),
            _node("B"),
        ]
        edges = [
            _edge("A", "loop_controller"),
            _edge("loop_controller", "B"),
            _edge("B", "loop_controller"),
        ]
        valid, illegal = detect_loops(nodes, edges)
        assert len(valid) == 1
        assert len(illegal) == 0

        loop = valid[0]
        assert loop.controller_node_id == "loop_controller"
        assert "B" in loop.body_node_ids
        assert loop.feedback_edges == (("B", "loop_controller"),)
        assert loop.max_iterations == 50

    def test_illegal_cycle_no_controller(self):
        """A -> B -> C -> A with no loop_controller is illegal."""
        nodes = [_node("A"), _node("B"), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C"), _edge("C", "A")]
        valid, illegal = detect_loops(nodes, edges)
        assert len(valid) == 0
        assert len(illegal) == 1
        assert set(illegal[0]) == {"A", "B", "C"}

    def test_no_cycles(self):
        """A pure DAG has no loops or cycles."""
        nodes = [_node("A"), _node("B"), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C")]
        valid, illegal = detect_loops(nodes, edges)
        assert len(valid) == 0
        assert len(illegal) == 0

    def test_default_max_iterations(self):
        """Without explicit iterations config, default to 100."""
        nodes = [
            _node("ctrl", block_type="loop_controller"),
            _node("body"),
        ]
        edges = [_edge("ctrl", "body"), _edge("body", "ctrl")]
        valid, _ = detect_loops(nodes, edges)
        assert len(valid) == 1
        assert valid[0].max_iterations == 100

    def test_multiple_controllers_in_scc_is_illegal(self):
        """An SCC with 2 loop controllers is an illegal cycle."""
        nodes = [
            _node("ctrl1", block_type="loop_controller"),
            _node("ctrl2", block_type="loop_controller"),
            _node("body"),
        ]
        edges = [
            _edge("ctrl1", "body"),
            _edge("body", "ctrl2"),
            _edge("ctrl2", "ctrl1"),
        ]
        valid, illegal = detect_loops(nodes, edges)
        assert len(valid) == 0
        assert len(illegal) == 1


# ---------------------------------------------------------------------------
# Multi-Feedback Edges (Risk 3)
# ---------------------------------------------------------------------------

class TestMultiFeedbackEdges:
    """Verify that branching loop bodies with multiple feedback paths
    are fully captured."""

    def test_two_feedback_edges(self):
        """Loop body branches: ctrl -> B1, ctrl -> B2, both feed back to ctrl."""
        nodes = [
            _node("ctrl", block_type="loop_controller", config={"iterations": 20}),
            _node("B1"),
            _node("B2"),
        ]
        edges = [
            _edge("ctrl", "B1"),
            _edge("ctrl", "B2"),
            _edge("B1", "ctrl"),
            _edge("B2", "ctrl"),
        ]
        valid, illegal = detect_loops(nodes, edges)
        assert len(valid) == 1
        assert len(illegal) == 0

        loop = valid[0]
        assert loop.controller_node_id == "ctrl"
        assert set(loop.body_node_ids) == {"B1", "B2"}
        # Both feedback edges captured
        assert len(loop.feedback_edges) == 2
        assert ("B1", "ctrl") in loop.feedback_edges
        assert ("B2", "ctrl") in loop.feedback_edges
        assert loop.max_iterations == 20

    def test_three_feedback_edges_complex_body(self):
        """Complex loop: ctrl -> A -> B -> ctrl, ctrl -> A -> C -> ctrl, ctrl -> D -> ctrl."""
        nodes = [
            _node("ctrl", block_type="loop_controller"),
            _node("A"),
            _node("B"),
            _node("C"),
            _node("D"),
        ]
        edges = [
            _edge("ctrl", "A"),
            _edge("A", "B"),
            _edge("B", "ctrl"),   # feedback 1
            _edge("A", "C"),
            _edge("C", "ctrl"),   # feedback 2
            _edge("ctrl", "D"),
            _edge("D", "ctrl"),   # feedback 3
        ]
        valid, illegal = detect_loops(nodes, edges)
        assert len(valid) == 1
        loop = valid[0]
        assert len(loop.feedback_edges) == 3
        feedback_sources = {fe[0] for fe in loop.feedback_edges}
        assert feedback_sources == {"B", "C", "D"}

    def test_feedback_edges_are_sorted(self):
        """Feedback edges are sorted by (source, target) for determinism."""
        nodes = [
            _node("ctrl", block_type="loop_controller"),
            _node("Z"),
            _node("A"),
        ]
        edges = [
            _edge("ctrl", "Z"),
            _edge("ctrl", "A"),
            _edge("Z", "ctrl"),
            _edge("A", "ctrl"),
        ]
        valid, _ = detect_loops(nodes, edges)
        assert valid[0].feedback_edges == (("A", "ctrl"), ("Z", "ctrl"))

    def test_multi_feedback_excluded_from_topo_sort_via_orchestrator(self):
        """plan_execution_order excludes ALL feedback edges, not just one."""
        nodes = [
            _node("start"),
            _node("ctrl", block_type="loop_controller"),
            _node("B1"),
            _node("B2"),
            _node("end"),
        ]
        edges = [
            _edge("start", "ctrl"),
            _edge("ctrl", "B1"),
            _edge("ctrl", "B2"),
            _edge("B1", "ctrl"),  # feedback 1
            _edge("B2", "ctrl"),  # feedback 2
            _edge("ctrl", "end"),
        ]
        result = plan_execution_order(nodes, edges)
        # Both feedback edges excluded
        assert ("B1", "ctrl") in result.feedback_edges
        assert ("B2", "ctrl") in result.feedback_edges
        assert len(result.feedback_edges) == 2
        # Topo sort succeeded (would fail if any feedback edge remained)
        assert "start" in result.execution_order
        assert "end" in result.execution_order
        # start before ctrl, ctrl before end
        order = list(result.execution_order)
        assert order.index("start") < order.index("ctrl")
        assert order.index("ctrl") < order.index("end")


# ---------------------------------------------------------------------------
# plan_execution_order (Orchestrator — Risk 2)
# ---------------------------------------------------------------------------

class TestPlanExecutionOrder:
    def test_simple_dag(self):
        """Pure DAG: no loops, no illegal cycles."""
        nodes = [_node("A"), _node("B"), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C")]
        result = plan_execution_order(nodes, edges)
        assert result.execution_order == ("A", "B", "C")
        assert result.loops == ()
        assert result.illegal_cycles == ()
        assert result.feedback_edges == frozenset()

    def test_with_valid_loop(self):
        """DAG + one valid loop: order excludes feedback, loop is returned."""
        nodes = [
            _node("start"),
            _node("ctrl", block_type="loop_controller", config={"iterations": 5}),
            _node("body"),
            _node("end"),
        ]
        edges = [
            _edge("start", "ctrl"),
            _edge("ctrl", "body"),
            _edge("body", "ctrl"),  # feedback
            _edge("ctrl", "end"),
        ]
        result = plan_execution_order(nodes, edges)
        assert len(result.loops) == 1
        assert result.loops[0].controller_node_id == "ctrl"
        assert result.loops[0].feedback_edges == (("body", "ctrl"),)
        assert result.feedback_edges == frozenset({("body", "ctrl")})
        # Execution order is valid
        order = list(result.execution_order)
        assert order.index("start") < order.index("ctrl")
        assert order.index("ctrl") < order.index("end")
        assert len(result.illegal_cycles) == 0

    def test_illegal_cycle_propagates_valueerror(self):
        """Illegal cycle (no loop controller) makes topological_sort raise."""
        nodes = [_node("A"), _node("B"), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C"), _edge("C", "A")]
        with pytest.raises(ValueError, match="cycle"):
            plan_execution_order(nodes, edges)

    def test_mixed_valid_loop_and_illegal_cycle(self):
        """One valid loop + one illegal cycle: detect both, topo sort fails on residual cycle."""
        nodes = [
            _node("ctrl", block_type="loop_controller"),
            _node("body"),
            _node("X"),
            _node("Y"),
            _node("Z"),
        ]
        edges = [
            # Valid loop
            _edge("ctrl", "body"),
            _edge("body", "ctrl"),
            # Illegal cycle (no controller)
            _edge("X", "Y"),
            _edge("Y", "Z"),
            _edge("Z", "X"),
        ]
        # The illegal cycle causes topo sort to fail even though the
        # valid loop's feedback edge is excluded
        with pytest.raises(ValueError, match="cycle"):
            plan_execution_order(nodes, edges)

    def test_result_is_frozen(self):
        """ExecutionOrderResult is immutable."""
        nodes = [_node("A"), _node("B")]
        edges = [_edge("A", "B")]
        result = plan_execution_order(nodes, edges)
        with pytest.raises(AttributeError):
            result.execution_order = ("B", "A")  # type: ignore[misc]

    def test_empty_graph(self):
        result = plan_execution_order([], [])
        assert result.execution_order == ()
        assert result.loops == ()
        assert result.illegal_cycles == ()
        assert result.feedback_edges == frozenset()

    def test_two_independent_loops(self):
        """Two separate loops: both detected, both feedback edges excluded."""
        nodes = [
            _node("ctrl1", block_type="loop_controller"),
            _node("b1"),
            _node("ctrl2", block_type="loop_controller"),
            _node("b2"),
        ]
        edges = [
            _edge("ctrl1", "b1"), _edge("b1", "ctrl1"),
            _edge("ctrl2", "b2"), _edge("b2", "ctrl2"),
        ]
        result = plan_execution_order(nodes, edges)
        assert len(result.loops) == 2
        assert len(result.feedback_edges) == 2
        assert ("b1", "ctrl1") in result.feedback_edges
        assert ("b2", "ctrl2") in result.feedback_edges
        # Both loops' controllers appear in execution order
        assert "ctrl1" in result.execution_order
        assert "ctrl2" in result.execution_order


# ---------------------------------------------------------------------------
# Independent Subgraphs
# ---------------------------------------------------------------------------

class TestFindIndependentSubgraphs:
    def test_two_disconnected_subgraphs(self):
        """[A->B] + [C->D] are two independent subgraphs."""
        nodes = [_node("A"), _node("B"), _node("C"), _node("D")]
        edges = [_edge("A", "B"), _edge("C", "D")]
        groups = find_independent_subgraphs(nodes, edges)
        assert len(groups) == 2
        group_sets = [set(g) for g in groups]
        assert {"A", "B"} in group_sets
        assert {"C", "D"} in group_sets

    def test_single_connected_graph(self):
        """A->B->C is one subgraph."""
        nodes = [_node("A"), _node("B"), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C")]
        groups = find_independent_subgraphs(nodes, edges)
        assert len(groups) == 1
        assert set(groups[0]) == {"A", "B", "C"}

    def test_all_isolated_nodes(self):
        """Three isolated nodes form three subgraphs."""
        nodes = [_node("A"), _node("B"), _node("C")]
        groups = find_independent_subgraphs(nodes, [])
        assert len(groups) == 3

    def test_empty_graph(self):
        groups = find_independent_subgraphs([], [])
        assert groups == []

    def test_three_subgraphs(self):
        """[A->B], [C], [D->E->F] form three subgraphs."""
        nodes = [_node("A"), _node("B"), _node("C"), _node("D"), _node("E"), _node("F")]
        edges = [_edge("A", "B"), _edge("D", "E"), _edge("E", "F")]
        groups = find_independent_subgraphs(nodes, edges)
        assert len(groups) == 3
        group_sets = [set(g) for g in groups]
        assert {"A", "B"} in group_sets
        assert {"C"} in group_sets
        assert {"D", "E", "F"} in group_sets

    def test_groups_are_sorted(self):
        """Each group is sorted and groups are sorted by first element."""
        nodes = [_node("Z"), _node("Y"), _node("A"), _node("B")]
        edges = [_edge("Z", "Y"), _edge("B", "A")]
        groups = find_independent_subgraphs(nodes, edges)
        assert len(groups) == 2
        for g in groups:
            assert g == sorted(g)
        assert groups[0][0] < groups[1][0]
