"""Tests for the GraphPlanner assembly (prompt 1.5)."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Any, Optional

from backend.engine.planner import GraphPlanner
from backend.engine.planner_models import (
    ExecutionPlan,
    LoopBoundary,
    ResolvedNode,
    PlannerResult,
)
from backend.engine.graph_utils import (
    detect_loops,
    topological_sort,
    plan_execution_order,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(nid: str, block_type: str = "test_block", category: str = "data", config: dict = None):
    """Create a minimal pipeline node dict."""
    return {
        "id": nid,
        "type": "default",
        "data": {
            "type": block_type,
            "label": f"Node {nid}",
            "category": category,
            "config": config or {},
        },
    }


def _loop_controller_node(nid: str, config: dict = None):
    """Create a loop_controller node."""
    cfg = {"iterations": 10}
    if config:
        cfg.update(config)
    return _node(nid, block_type="loop_controller", category="flow", config=cfg)


def _edge(src: str, tgt: str, src_handle: str = "output", tgt_handle: str = "input"):
    """Create a pipeline edge dict."""
    return {
        "source": src,
        "target": tgt,
        "sourceHandle": src_handle,
        "targetHandle": tgt_handle,
    }


class _MockRegistry:
    """Minimal registry mock for planner tests."""

    def __init__(self, known_types: set[str] | None = None, version: str = "1.0.0"):
        self._known = known_types
        self._version = version

    def get(self, block_type: str):
        if self._known is not None and block_type not in self._known:
            return None
        return {"type": block_type, "inputs": [], "outputs": [], "config": {}}

    def get_block_version(self, block_type: str) -> str:
        return self._version

    def get_block_schema_defaults(self, block_type: str) -> dict[str, Any]:
        return {}

    def get_block_info(self, block_type: str) -> Optional[dict]:
        schema = self.get(block_type)
        if schema is None:
            return None
        return {"type": block_type, "category": "data", "path": "/tmp/blocks/" + block_type}

    def get_category(self, block_type: str) -> str:
        return "data"

    def validate_connection(self, src_type, src_port, dst_type, dst_port):
        return {"valid": True}

    def is_port_compatible(self, src_type: str, tgt_type: str) -> bool:
        return True


class _MockRegistryWithInputs(_MockRegistry):
    """Registry that returns blocks with required inputs."""

    def __init__(self, inputs_schema: list | None = None):
        super().__init__()
        self._inputs = inputs_schema or []

    def get(self, block_type: str):
        return {"type": block_type, "inputs": self._inputs, "outputs": [], "config": {}}


# ---------------------------------------------------------------------------
# GraphPlanner core tests
# ---------------------------------------------------------------------------

class TestGraphPlanner:
    """Tests for the GraphPlanner.plan() method."""

    def test_plan_simple_dag(self):
        """3-block linear DAG: verify correct order."""
        nodes = [_node("A"), _node("B"), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C")]

        planner = GraphPlanner(registry=_MockRegistry())
        result = planner.plan(nodes, edges)

        assert result.is_valid, f"Errors: {result.errors}"
        assert result.plan is not None
        order = list(result.plan.execution_order)
        assert order == ["A", "B", "C"]
        assert "A" in result.plan.nodes
        assert "B" in result.plan.nodes
        assert "C" in result.plan.nodes
        assert result.plan.plan_hash

    def test_plan_branching(self):
        """Fan-out/fan-in: verify both branches come before merge node."""
        nodes = [_node("src"), _node("left"), _node("right"), _node("merge")]
        edges = [
            _edge("src", "left"),
            _edge("src", "right"),
            _edge("left", "merge"),
            _edge("right", "merge"),
        ]

        planner = GraphPlanner(registry=_MockRegistry())
        result = planner.plan(nodes, edges)

        assert result.is_valid
        order = list(result.plan.execution_order)
        assert order.index("left") < order.index("merge")
        assert order.index("right") < order.index("merge")

    def test_plan_loop(self):
        """Valid loop: verify LoopBoundary is created."""
        nodes = [
            _node("pre"),
            _loop_controller_node("ctrl"),
            _node("body"),
            _node("post"),
        ]
        edges = [
            _edge("pre", "ctrl"),
            _edge("ctrl", "body"),
            _edge("body", "ctrl"),  # feedback
            _edge("ctrl", "post"),
        ]

        planner = GraphPlanner(
            registry=_MockRegistry({"test_block", "loop_controller"}),
        )
        result = planner.plan(nodes, edges)

        assert result.is_valid, f"Errors: {result.errors}"
        assert len(result.plan.loops) == 1
        loop = result.plan.loops[0]
        assert loop.controller_node_id == "ctrl"
        assert "body" in loop.body_node_ids
        # Verify loop nodes are marked in_loop
        assert result.plan.nodes["body"].in_loop is True
        assert result.plan.nodes["ctrl"].in_loop is True

    def test_plan_illegal_cycle(self):
        """Cycle without controller: verify is_valid=False with specific error."""
        nodes = [_node("A"), _node("B"), _node("C")]
        edges = [
            _edge("A", "B"),
            _edge("B", "C"),
            _edge("C", "A"),
        ]

        planner = GraphPlanner(registry=_MockRegistry())
        result = planner.plan(nodes, edges)

        assert not result.is_valid
        assert len(result.errors) >= 1
        assert any("cycle" in e.lower() for e in result.errors)

    def test_plan_unknown_block(self):
        """Nonexistent block_type: verify error."""
        nodes = [_node("A", block_type="nonexistent_block_xyz")]
        edges = []

        planner = GraphPlanner(
            registry=_MockRegistry(known_types=set()),
        )
        result = planner.plan(nodes, edges)

        assert not result.is_valid
        assert any("nonexistent_block_xyz" in e for e in result.errors)

    def test_plan_disconnected_required_port(self):
        """Required input not connected: verify error."""
        registry = _MockRegistryWithInputs(
            inputs_schema=[{"id": "data", "required": True}],
        )

        nodes = [_node("A"), _node("B")]
        edges = []  # Nothing connected

        planner = GraphPlanner(registry=registry)
        result = planner.plan(nodes, edges)

        assert not result.is_valid
        assert any("Required input port" in e for e in result.errors)

    def test_plan_empty_pipeline(self):
        """Empty pipeline produces valid empty plan."""
        planner = GraphPlanner(registry=_MockRegistry())
        result = planner.plan([], [])

        assert result.is_valid
        assert result.plan is not None
        assert len(result.plan.execution_order) == 0

    def test_plan_produces_fingerprints(self):
        """All planned nodes should have cache fingerprints."""
        nodes = [_node("A"), _node("B")]
        edges = [_edge("A", "B")]

        planner = GraphPlanner(registry=_MockRegistry())
        result = planner.plan(nodes, edges)

        assert result.is_valid
        for nid, rn in result.plan.nodes.items():
            assert rn.cache_fingerprint, f"Node {nid} missing fingerprint"

    def test_plan_invalid_edge_references(self):
        """Edges referencing non-existent nodes produce errors."""
        nodes = [_node("A")]
        edges = [_edge("A", "NONEXISTENT")]

        planner = GraphPlanner(registry=_MockRegistry())
        result = planner.plan(nodes, edges)

        assert not result.is_valid
        assert any("NONEXISTENT" in e for e in result.errors)

    def test_plan_independent_subgraphs(self):
        """Disconnected components are detected as independent subgraphs."""
        nodes = [_node("A"), _node("B"), _node("C"), _node("D")]
        edges = [_edge("A", "B"), _edge("C", "D")]  # Two disconnected pairs

        planner = GraphPlanner(registry=_MockRegistry())
        result = planner.plan(nodes, edges)

        assert result.is_valid
        assert len(result.plan.independent_subgraphs) == 2


# ---------------------------------------------------------------------------
# Single-node SCC correctness
# ---------------------------------------------------------------------------

class TestSingleNodeSCC:
    """Verify nodes downstream of a cycle are NOT treated as cyclic."""

    def test_downstream_of_loop_not_cyclic(self):
        """A node after a loop controller is NOT part of the loop SCC."""
        nodes = [
            _node("pre"),
            _loop_controller_node("ctrl"),
            _node("body"),
            _node("post"),
        ]
        edges = [
            _edge("pre", "ctrl"),
            _edge("ctrl", "body"),
            _edge("body", "ctrl"),
            _edge("ctrl", "post"),
        ]
        valid_loops, illegal_cycles = detect_loops(nodes, edges)
        assert len(valid_loops) == 1
        assert "post" not in valid_loops[0].body_node_ids
        assert len(illegal_cycles) == 0

    def test_topological_sort_includes_downstream(self):
        """Topological sort with loops should include downstream nodes."""
        nodes = [
            _loop_controller_node("ctrl"),
            _node("body"),
            _node("post"),
        ]
        edges = [
            _edge("ctrl", "body"),
            _edge("body", "ctrl"),
            _edge("ctrl", "post"),
        ]
        result = plan_execution_order(nodes, edges)
        assert "post" in result.execution_order
        order = list(result.execution_order)
        assert order.index("ctrl") < order.index("post")


# ---------------------------------------------------------------------------
# PlannerResult / ExecutionPlan model tests
# ---------------------------------------------------------------------------

class TestPlannerModels:
    def test_execution_plan_is_frozen(self):
        plan = ExecutionPlan(
            execution_order=("A", "B"),
            nodes={},
            loops=(),
            independent_subgraphs=(),
            plan_hash="abc123",
            warnings=(),
        )
        with pytest.raises(AttributeError):
            plan.plan_hash = "modified"

    def test_resolved_node_is_frozen(self):
        rn = ResolvedNode(
            node_id="A",
            block_type="test",
            block_version="1.0.0",
            resolved_config={},
            config_sources={},
            cache_fingerprint="abc",
            cache_eligible=True,
            in_loop=False,
            loop_id=None,
        )
        with pytest.raises(AttributeError):
            rn.block_type = "changed"
