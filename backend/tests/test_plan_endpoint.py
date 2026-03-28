"""Tests for the GET /api/pipelines/{id}/plan endpoint and ExecutionDecision model."""

import pytest
import uuid
from unittest.mock import patch, MagicMock
from typing import Any, Optional

from backend.engine.planner import GraphPlanner
from backend.engine.planner_models import PlannerResult, ExecutionPlan, ResolvedNode
from backend.models.execution_decision import ExecutionDecision


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(nid: str, block_type: str = "test_block", category: str = "data", config: dict = None):
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


def _edge(src: str, tgt: str, src_handle: str = "output", tgt_handle: str = "input"):
    return {
        "source": src,
        "target": tgt,
        "sourceHandle": src_handle,
        "targetHandle": tgt_handle,
    }


class _MockRegistry:
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
        return {"seed": 42, "temperature": 0.7}

    def get_block_info(self, block_type: str) -> Optional[dict]:
        schema = self.get(block_type)
        if schema is None:
            return None
        return {"type": block_type, "category": "data", "path": "/tmp/blocks/" + block_type}

    def validate_connection(self, *args, **kwargs):
        return {"valid": True}

    def is_port_compatible(self, *args, **kwargs):
        return True

    def get_file_path_fields(self, block_type: str):
        return []

    def list_all(self, category=None):
        return []


# ---------------------------------------------------------------------------
# Planner tests — verifying plan structure for the endpoint
# ---------------------------------------------------------------------------

class TestPlanEndpointData:
    """Verify that the planner produces the data we expose via the plan endpoint."""

    def test_plan_includes_config_sources(self):
        """Each node in the plan must have config_sources mapping."""
        nodes = [_node("A"), _node("B")]
        edges = [_edge("A", "B")]
        registry = _MockRegistry(known_types={"test_block"})
        planner = GraphPlanner(registry)
        result = planner.plan(nodes, edges)
        assert result.is_valid
        assert result.plan is not None
        for node_id, rn in result.plan.nodes.items():
            assert isinstance(rn.config_sources, dict)

    def test_plan_includes_cache_fingerprints(self):
        """Each node must have a non-empty cache_fingerprint."""
        nodes = [_node("A"), _node("B")]
        edges = [_edge("A", "B")]
        registry = _MockRegistry(known_types={"test_block"})
        planner = GraphPlanner(registry)
        result = planner.plan(nodes, edges)
        assert result.is_valid
        for node_id, rn in result.plan.nodes.items():
            assert len(rn.cache_fingerprint) > 0

    def test_plan_includes_cache_eligible(self):
        """Nodes not in a loop should be cache_eligible."""
        nodes = [_node("A"), _node("B")]
        edges = [_edge("A", "B")]
        registry = _MockRegistry(known_types={"test_block"})
        planner = GraphPlanner(registry)
        result = planner.plan(nodes, edges)
        assert result.is_valid
        for rn in result.plan.nodes.values():
            assert rn.cache_eligible is True

    def test_plan_node_resolved_config(self):
        """resolved_config should contain schema defaults."""
        nodes = [_node("A", config={"seed": 123})]
        edges = []
        registry = _MockRegistry(known_types={"test_block"})
        planner = GraphPlanner(registry)
        result = planner.plan(nodes, edges)
        assert result.is_valid
        rn = result.plan.nodes["A"]
        assert rn.resolved_config["seed"] == 123
        assert rn.config_sources["seed"] == "user"

    def test_plan_empty_pipeline(self):
        """Empty pipeline returns an empty plan without errors."""
        registry = _MockRegistry(known_types=set())
        planner = GraphPlanner(registry)
        result = planner.plan([], [])
        assert result.is_valid
        assert result.plan.plan_hash == "empty"

    def test_plan_invalid_block_type(self):
        """Unknown block types produce errors."""
        nodes = [_node("A", block_type="nonexistent")]
        edges = []
        registry = _MockRegistry(known_types={"test_block"})
        planner = GraphPlanner(registry)
        result = planner.plan(nodes, edges)
        assert not result.is_valid
        assert any("not found" in e for e in result.errors)

    def test_plan_hash_deterministic(self):
        """Same input produces the same plan hash."""
        nodes = [_node("A"), _node("B")]
        edges = [_edge("A", "B")]
        registry = _MockRegistry(known_types={"test_block"})
        planner = GraphPlanner(registry)
        r1 = planner.plan(nodes, edges)
        r2 = planner.plan(nodes, edges)
        assert r1.plan.plan_hash == r2.plan.plan_hash

    def test_workspace_config_changes_resolution(self):
        """Workspace config should override defaults in resolved_config."""
        nodes = [_node("A")]
        edges = []
        registry = _MockRegistry(known_types={"test_block"})
        planner = GraphPlanner(registry)
        result = planner.plan(nodes, edges, workspace_config={"seed": 999})
        assert result.is_valid
        rn = result.plan.nodes["A"]
        assert rn.resolved_config["seed"] == 999
        assert rn.config_sources["seed"] == "workspace"


# ---------------------------------------------------------------------------
# ExecutionDecision model tests
# ---------------------------------------------------------------------------

class TestExecutionDecisionModel:
    """Test the ExecutionDecision ORM model."""

    def test_model_columns(self):
        """Verify all required columns exist."""
        d = ExecutionDecision(
            id="test-id",
            run_id="run-1",
            node_id="node-1",
            decision="execute",
            reason="Test reason",
            cache_fingerprint="abc123",
            plan_hash="def456",
        )
        assert d.id == "test-id"
        assert d.run_id == "run-1"
        assert d.decision == "execute"
        assert d.reason == "Test reason"

    def test_tablename(self):
        assert ExecutionDecision.__tablename__ == "execution_decisions"

    def test_valid_decisions(self):
        """All expected decision values should be accepted."""
        for decision in ["execute", "cache_hit", "cache_invalidated", "skipped"]:
            d = ExecutionDecision(
                id=f"test-{decision}",
                run_id="run-1",
                node_id="node-1",
                decision=decision,
            )
            assert d.decision == decision


# ---------------------------------------------------------------------------
# Config inheritance source tests
# ---------------------------------------------------------------------------

class TestConfigSourceTracking:
    """Verify config_sources correctly identify value origins."""

    def test_user_override_tracked(self):
        """User-set values should be marked as 'user'."""
        nodes = [_node("A", config={"seed": 100})]
        registry = _MockRegistry(known_types={"test_block"})
        planner = GraphPlanner(registry)
        result = planner.plan(nodes, [])
        rn = result.plan.nodes["A"]
        assert rn.config_sources["seed"] == "user"

    def test_default_tracked(self):
        """Schema defaults should be marked as 'block_default'."""
        nodes = [_node("A")]  # No user config
        registry = _MockRegistry(known_types={"test_block"})
        planner = GraphPlanner(registry)
        result = planner.plan(nodes, [])
        rn = result.plan.nodes["A"]
        assert rn.config_sources.get("seed") == "block_default"
        assert rn.config_sources.get("temperature") == "block_default"

    def test_fingerprint_changes_with_config(self):
        """Changing config should change the fingerprint."""
        nodes_a = [_node("A", config={"seed": 1})]
        nodes_b = [_node("A", config={"seed": 2})]
        registry = _MockRegistry(known_types={"test_block"})
        planner = GraphPlanner(registry)
        r1 = planner.plan(nodes_a, [])
        r2 = planner.plan(nodes_b, [])
        assert r1.plan.nodes["A"].cache_fingerprint != r2.plan.nodes["A"].cache_fingerprint
