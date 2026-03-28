"""Tests for backend.engine.planner_models — immutability guarantees."""

import dataclasses
import pytest

from backend.engine.planner_models import (
    ExecutionPlan,
    LoopBoundary,
    PlannerResult,
    ResolvedNode,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_resolved_node(**overrides) -> ResolvedNode:
    defaults = dict(
        node_id="n1",
        block_type="llm_inference",
        block_version="1.0.0",
        resolved_config={"temperature": 0.7},
        config_sources={"temperature": "user"},
        cache_fingerprint="abc123",
        cache_eligible=True,
        in_loop=False,
        loop_id=None,
    )
    defaults.update(overrides)
    return ResolvedNode(**defaults)


def _make_execution_plan(**overrides) -> ExecutionPlan:
    node = _make_resolved_node()
    defaults = dict(
        execution_order=("n1",),
        nodes={"n1": node},
        loops=(),
        independent_subgraphs=(("n1",),),
        plan_hash="deadbeef",
        warnings=(),
    )
    defaults.update(overrides)
    return ExecutionPlan(**defaults)


# ---------------------------------------------------------------------------
# Immutability Tests
# ---------------------------------------------------------------------------

class TestResolvedNodeImmutability:
    def test_cannot_set_attribute(self):
        node = _make_resolved_node()
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.node_id = "n2"  # type: ignore[misc]

    def test_cannot_set_block_type(self):
        node = _make_resolved_node()
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.block_type = "other"  # type: ignore[misc]

    def test_cannot_set_cache_eligible(self):
        node = _make_resolved_node()
        with pytest.raises(dataclasses.FrozenInstanceError):
            node.cache_eligible = False  # type: ignore[misc]


class TestLoopBoundaryImmutability:
    def test_cannot_set_attribute(self):
        lb = LoopBoundary(
            controller_node_id="ctrl",
            body_node_ids=("b1", "b2"),
            feedback_edges=(("b2", "ctrl"),),
            max_iterations=50,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            lb.max_iterations = 999  # type: ignore[misc]

    def test_cannot_set_feedback_edges(self):
        lb = LoopBoundary(
            controller_node_id="ctrl",
            body_node_ids=("b1",),
            feedback_edges=(("b1", "ctrl"),),
            max_iterations=10,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            lb.feedback_edges = (("b1", "ctrl"), ("b2", "ctrl"))  # type: ignore[misc]

    def test_multiple_feedback_edges_stored(self):
        lb = LoopBoundary(
            controller_node_id="ctrl",
            body_node_ids=("b1", "b2"),
            feedback_edges=(("b1", "ctrl"), ("b2", "ctrl")),
            max_iterations=50,
        )
        assert len(lb.feedback_edges) == 2
        assert ("b1", "ctrl") in lb.feedback_edges
        assert ("b2", "ctrl") in lb.feedback_edges


class TestExecutionPlanImmutability:
    def test_cannot_set_execution_order(self):
        plan = _make_execution_plan()
        with pytest.raises(dataclasses.FrozenInstanceError):
            plan.execution_order = ("n2",)  # type: ignore[misc]

    def test_cannot_set_plan_hash(self):
        plan = _make_execution_plan()
        with pytest.raises(dataclasses.FrozenInstanceError):
            plan.plan_hash = "changed"  # type: ignore[misc]

    def test_cannot_set_warnings(self):
        plan = _make_execution_plan()
        with pytest.raises(dataclasses.FrozenInstanceError):
            plan.warnings = ("new warning",)  # type: ignore[misc]


class TestPlannerResultImmutability:
    def test_cannot_set_is_valid(self):
        result = PlannerResult(is_valid=True, errors=(), plan=None)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.is_valid = False  # type: ignore[misc]

    def test_cannot_set_plan(self):
        result = PlannerResult(is_valid=False, errors=("bad",), plan=None)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.plan = _make_execution_plan()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Construction / Value Tests
# ---------------------------------------------------------------------------

class TestResolvedNodeValues:
    def test_fields_accessible(self):
        node = _make_resolved_node(
            node_id="x",
            block_type="data_loader",
            in_loop=True,
            loop_id="loop1",
        )
        assert node.node_id == "x"
        assert node.block_type == "data_loader"
        assert node.in_loop is True
        assert node.loop_id == "loop1"

    def test_config_sources_mapping(self):
        node = _make_resolved_node(
            config_sources={"lr": "workspace", "epochs": "inherited:n0"},
        )
        assert node.config_sources["lr"] == "workspace"
        assert node.config_sources["epochs"] == "inherited:n0"


class TestExecutionPlanValues:
    def test_plan_hash_and_warnings(self):
        plan = _make_execution_plan(
            plan_hash="abc",
            warnings=("deprecated block",),
        )
        assert plan.plan_hash == "abc"
        assert plan.warnings == ("deprecated block",)

    def test_empty_plan(self):
        plan = ExecutionPlan(
            execution_order=(),
            nodes={},
            loops=(),
            independent_subgraphs=(),
            plan_hash="empty",
            warnings=(),
        )
        assert len(plan.execution_order) == 0
        assert len(plan.nodes) == 0


class TestPlannerResultValues:
    def test_valid_result_with_plan(self):
        plan = _make_execution_plan()
        result = PlannerResult(is_valid=True, errors=(), plan=plan)
        assert result.is_valid is True
        assert result.plan is not None
        assert result.plan.plan_hash == "deadbeef"

    def test_invalid_result_without_plan(self):
        result = PlannerResult(
            is_valid=False,
            errors=("cycle detected",),
            plan=None,
        )
        assert result.is_valid is False
        assert "cycle detected" in result.errors
        assert result.plan is None
