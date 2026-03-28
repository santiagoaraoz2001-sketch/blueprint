"""
Kill-switch tests — validates safety guards that block dangerous operations
on pipelines with loops, custom code, or stale caches.

Covers:
  1. Partial rerun rejected for loop graphs (HTTP 400)
  2. Export rejected for loop graphs (HTTP 400)
  3. Export rejected for custom code blocks (HTTP 400)
  4. Cache rejected when config has changed (re-execution)
  5. Cache accepted when config is identical (cache hit)
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from backend.engine.graph_utils import (
    contains_loop_or_cycle,
    validate_exportable,
    is_cache_valid,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(nid: str, block_type: str = "loader", config: dict | None = None,
          label: str = "", category: str = "data") -> dict:
    """Create a minimal pipeline node."""
    return {
        "id": nid,
        "type": "blockNode",
        "data": {
            "type": block_type,
            "label": label or nid,
            "config": config or {},
            "category": category,
        },
        "position": {"x": 0, "y": 0},
    }


def _edge(src: str, tgt: str) -> dict:
    return {"source": src, "target": tgt, "sourceHandle": "output", "targetHandle": "input"}


def _definition(nodes: list[dict], edges: list[dict]) -> dict:
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Unit tests: contains_loop_or_cycle
# ---------------------------------------------------------------------------

class TestContainsLoopOrCycle:

    def test_simple_dag_returns_false(self):
        nodes = [_node("A"), _node("B"), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C")]
        assert contains_loop_or_cycle(nodes, edges) is False

    def test_loop_controller_block_returns_true(self):
        nodes = [_node("A"), _node("L", block_type="loop_controller"), _node("B")]
        edges = [_edge("A", "L"), _edge("L", "B")]
        assert contains_loop_or_cycle(nodes, edges) is True

    def test_cycle_without_loop_controller_returns_true(self):
        nodes = [_node("A"), _node("B"), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C"), _edge("C", "A")]
        assert contains_loop_or_cycle(nodes, edges) is True

    def test_empty_pipeline(self):
        assert contains_loop_or_cycle([], []) is False

    def test_single_node_no_edges(self):
        assert contains_loop_or_cycle([_node("A")], []) is False


# ---------------------------------------------------------------------------
# Unit tests: validate_exportable
# ---------------------------------------------------------------------------

class TestValidateExportable:

    def test_simple_dag_is_exportable(self):
        nodes = [_node("A"), _node("B")]
        edges = [_edge("A", "B")]
        assert validate_exportable(nodes, edges) == []

    def test_loop_controller_blocks_export(self):
        nodes = [_node("A"), _node("L", block_type="loop_controller")]
        edges = [_edge("A", "L")]
        reasons = validate_exportable(nodes, edges)
        assert len(reasons) >= 1
        assert any("loop" in r.lower() for r in reasons)

    def test_python_runner_blocks_export(self):
        nodes = [_node("A"), _node("P", block_type="python_runner")]
        edges = [_edge("A", "P")]
        reasons = validate_exportable(nodes, edges)
        assert len(reasons) >= 1
        assert any("python_runner" in r for r in reasons)

    def test_cycle_blocks_export(self):
        nodes = [_node("A"), _node("B")]
        edges = [_edge("A", "B"), _edge("B", "A")]
        reasons = validate_exportable(nodes, edges)
        assert len(reasons) >= 1
        assert any("loop" in r.lower() or "cycle" in r.lower() for r in reasons)


# ---------------------------------------------------------------------------
# Unit tests: is_cache_valid
# ---------------------------------------------------------------------------

class TestIsCacheValid:

    def _mock_db_with_run(self, status="complete", config=None, node_id="A"):
        """Create a mock DB session that returns a Run with given properties."""
        mock_run = MagicMock()
        mock_run.status = status
        mock_run.started_at = datetime.now(timezone.utc)
        mock_run.config_snapshot = _definition(
            [_node(node_id, config=config or {"lr": 0.01})],
            [],
        )

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = mock_run

        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        return mock_db, mock_run

    def test_cache_accepted_for_identical_config(self):
        """Config matches, run completed -> cache valid."""
        db, _ = self._mock_db_with_run(status="complete", config={"lr": 0.01})
        result = is_cache_valid("A", "pipeline-1", {"lr": 0.01}, db)
        assert result is True

    def test_cache_rejected_for_config_change(self):
        """Config changed -> cache invalid."""
        db, _ = self._mock_db_with_run(status="complete", config={"lr": 0.01})
        result = is_cache_valid("A", "pipeline-1", {"lr": 0.05}, db)
        assert result is False

    def test_cache_rejected_for_failed_run(self):
        """Previous run failed -> cache invalid."""
        db, _ = self._mock_db_with_run(status="failed", config={"lr": 0.01})
        result = is_cache_valid("A", "pipeline-1", {"lr": 0.01}, db)
        assert result is False

    def test_cache_rejected_for_cancelled_run(self):
        """Previous run cancelled -> cache invalid."""
        db, _ = self._mock_db_with_run(status="cancelled", config={"lr": 0.01})
        result = is_cache_valid("A", "pipeline-1", {"lr": 0.01}, db)
        assert result is False

    def test_cache_rejected_when_no_previous_run(self):
        """No previous run -> cache invalid."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.first.return_value = None

        mock_db = MagicMock()
        mock_db.query.return_value = mock_query

        result = is_cache_valid("A", "pipeline-1", {"lr": 0.01}, mock_db)
        assert result is False

    def test_cache_rejected_for_version_mismatch(self):
        """Block version changed since last run -> cache invalid."""
        db, mock_run = self._mock_db_with_run(status="complete", config={"lr": 0.01})
        # Inject block_version into snapshot
        mock_run.config_snapshot["nodes"][0]["data"]["block_version"] = "1.0.0"

        # Mock _find_block_module and load_block_schema to return version 2.0.0
        with patch("backend.engine.graph_utils._find_block_module") as mock_find, \
             patch("backend.engine.graph_utils.load_block_schema") as mock_schema:
            mock_find.return_value = "/fake/path"
            mock_schema.return_value = {"version": "2.0.0"}
            result = is_cache_valid("A", "pipeline-1", {"lr": 0.01}, db)
            assert result is False

    def test_cache_accepted_for_matching_version(self):
        """Block version matches between runs -> cache valid."""
        db, mock_run = self._mock_db_with_run(status="complete", config={"lr": 0.01})
        mock_run.config_snapshot["nodes"][0]["data"]["block_version"] = "1.0.0"

        with patch("backend.engine.graph_utils._find_block_module") as mock_find, \
             patch("backend.engine.graph_utils.load_block_schema") as mock_schema:
            mock_find.return_value = "/fake/path"
            mock_schema.return_value = {"version": "1.0.0"}
            result = is_cache_valid("A", "pipeline-1", {"lr": 0.01}, db)
            assert result is True


# ---------------------------------------------------------------------------
# Integration tests: Endpoints
# ---------------------------------------------------------------------------

class TestPartialRerunRejectedForLoopGraph:
    """
    test_partial_rerun_rejected_for_loop_graph:
    Create a fixture with loop_controller, attempt partial rerun, assert 400.
    """

    def _setup(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        return TestClient(app)

    def test_partial_rerun_rejected_for_loop_graph(self):
        """POST /execute-from returns 400 when pipeline has loop_controller."""
        client = self._setup()

        definition = _definition(
            nodes=[
                _node("A", block_type="loader"),
                _node("L", block_type="loop_controller"),
                _node("B", block_type="loader"),
            ],
            edges=[_edge("A", "L"), _edge("L", "B"), _edge("B", "L")],
        )

        # Mock pipeline and run lookups
        mock_pipeline = MagicMock()
        mock_pipeline.id = "test-pipeline"
        mock_pipeline.definition = definition
        mock_pipeline.project_id = None

        with patch("backend.routers.execution.Pipeline") as MockPipeline, \
             patch("backend.routers.execution.Run") as MockRun:
            # Pipeline.query().filter().first() returns our mock
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.first.return_value = mock_pipeline
            MockPipeline.__tablename__ = "blueprint_pipelines"

            # Patch get_db to return a mock session
            mock_db = MagicMock()
            mock_db.query.return_value = mock_query

            from backend.database import get_db
            from backend.main import app

            app.dependency_overrides[get_db] = lambda: mock_db
            try:
                resp = client.post(
                    "/api/pipelines/test-pipeline/execute-from",
                    json={
                        "source_run_id": "run-1",
                        "start_node_id": "B",
                    },
                )
                assert resp.status_code == 400
                detail = resp.json()["detail"]
                assert detail["error"] == "partial_rerun_unsupported"
            finally:
                app.dependency_overrides.clear()


class TestPartialRerunRejectedForCycle:
    """Partial rerun rejected for raw graph cycles (no loop_controller)."""

    def test_partial_rerun_rejected_for_cycle(self):
        """POST /execute-from returns 400 when pipeline has a cycle."""
        from fastapi.testclient import TestClient
        from backend.main import app

        definition = _definition(
            nodes=[
                _node("A", block_type="loader"),
                _node("B", block_type="loader"),
                _node("C", block_type="loader"),
            ],
            edges=[_edge("A", "B"), _edge("B", "C"), _edge("C", "A")],
        )

        mock_pipeline = MagicMock()
        mock_pipeline.id = "test-pipeline"
        mock_pipeline.definition = definition
        mock_pipeline.project_id = None

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_pipeline
        mock_db.query.return_value = mock_query

        from backend.database import get_db

        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            client = TestClient(app)
            resp = client.post(
                "/api/pipelines/test-pipeline/execute-from",
                json={
                    "source_run_id": "run-1",
                    "start_node_id": "B",
                },
            )
            assert resp.status_code == 400
            detail = resp.json()["detail"]
            assert detail["error"] == "partial_rerun_unsupported"
        finally:
            app.dependency_overrides.clear()


class TestExportRejectedForLoopGraph:
    """
    test_export_rejected_for_loop_graph:
    Pipeline with loop_controller -> compile returns 400.
    """

    def test_export_rejected_for_loop_graph(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        definition = _definition(
            nodes=[
                _node("A", block_type="loader"),
                _node("L", block_type="loop_controller"),
            ],
            edges=[_edge("A", "L")],
        )

        mock_pipeline = MagicMock()
        mock_pipeline.id = "test-pipeline"
        mock_pipeline.name = "Test"
        mock_pipeline.definition = definition

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_pipeline
        mock_db.query.return_value = mock_query

        from backend.database import get_db

        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            client = TestClient(app)
            resp = client.get("/api/pipelines/test-pipeline/compile")
            assert resp.status_code == 400
            detail = resp.json()["detail"]
            assert detail["error"] == "export_unsupported"
            assert len(detail["reasons"]) >= 1
        finally:
            app.dependency_overrides.clear()


class TestExportRejectedForCustomBlock:
    """
    test_export_rejected_for_custom_block:
    Pipeline with python_runner -> compile returns 400.
    """

    def test_export_rejected_for_custom_block(self):
        from fastapi.testclient import TestClient
        from backend.main import app

        definition = _definition(
            nodes=[
                _node("A", block_type="loader"),
                _node("P", block_type="python_runner"),
            ],
            edges=[_edge("A", "P")],
        )

        mock_pipeline = MagicMock()
        mock_pipeline.id = "test-pipeline"
        mock_pipeline.name = "Test"
        mock_pipeline.definition = definition

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_pipeline
        mock_db.query.return_value = mock_query

        from backend.database import get_db

        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            client = TestClient(app)
            resp = client.get("/api/pipelines/test-pipeline/compile")
            assert resp.status_code == 400
            detail = resp.json()["detail"]
            assert detail["error"] == "export_unsupported"
            assert any("python_runner" in r for r in detail["reasons"])
        finally:
            app.dependency_overrides.clear()


class TestCacheRejectedForConfigChange:
    """
    test_cache_rejected_for_config_change:
    Execute, change config, attempt partial rerun, verify re-execution.
    """

    def test_cache_rejected_for_config_change(self):
        """is_cache_valid returns False when config has changed."""
        db, _ = TestIsCacheValid()._mock_db_with_run(
            status="complete", config={"lr": 0.01}
        )
        assert is_cache_valid("A", "pipeline-1", {"lr": 0.05}, db) is False


class TestCacheAcceptedForIdenticalConfig:
    """
    test_cache_accepted_for_identical_config:
    Execute, attempt partial rerun with same config, verify cache hit.
    """

    def test_cache_accepted_for_identical_config(self):
        """is_cache_valid returns True when config matches and run completed."""
        db, _ = TestIsCacheValid()._mock_db_with_run(
            status="complete", config={"lr": 0.01}
        )
        assert is_cache_valid("A", "pipeline-1", {"lr": 0.01}, db) is True
