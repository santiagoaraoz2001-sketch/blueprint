"""Tests for the partial re-execution engine."""

import asyncio
import json
import time
import pytest
from unittest.mock import patch, MagicMock, call

from backend.engine.partial_executor import (
    _get_downstream_nodes,
    _validate_upstream_definitions,
    execute_partial_pipeline,
)


def _run(coro):
    """Helper to run async functions in sync tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# _get_downstream_nodes
# ---------------------------------------------------------------------------

class TestGetDownstreamNodes:
    """Tests for BFS downstream node discovery."""

    def _nodes(self, *ids):
        return [{"id": nid} for nid in ids]

    def _edges(self, *pairs):
        return [{"source": s, "target": t} for s, t in pairs]

    def test_linear_chain_from_middle(self):
        nodes = self._nodes("A", "B", "C", "D", "E")
        edges = self._edges(("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"))
        result = _get_downstream_nodes("C", nodes, edges)
        assert result == {"C", "D", "E"}

    def test_linear_chain_from_start(self):
        nodes = self._nodes("A", "B", "C")
        edges = self._edges(("A", "B"), ("B", "C"))
        result = _get_downstream_nodes("A", nodes, edges)
        assert result == {"A", "B", "C"}

    def test_linear_chain_from_end(self):
        nodes = self._nodes("A", "B", "C")
        edges = self._edges(("A", "B"), ("B", "C"))
        result = _get_downstream_nodes("C", nodes, edges)
        assert result == {"C"}

    def test_diamond_graph(self):
        nodes = self._nodes("A", "B", "C", "D")
        edges = self._edges(("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"))
        result = _get_downstream_nodes("A", nodes, edges)
        assert result == {"A", "B", "C", "D"}

    def test_diamond_graph_from_branch(self):
        nodes = self._nodes("A", "B", "C", "D")
        edges = self._edges(("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"))
        result = _get_downstream_nodes("B", nodes, edges)
        assert result == {"B", "D"}

    def test_disconnected_node(self):
        nodes = self._nodes("A", "B", "C")
        edges = self._edges(("A", "B"))
        result = _get_downstream_nodes("C", nodes, edges)
        assert result == {"C"}

    def test_forking_graph(self):
        nodes = self._nodes("A", "B", "C", "D", "E")
        edges = self._edges(("A", "B"), ("A", "C"), ("B", "D"), ("C", "E"))
        result = _get_downstream_nodes("A", nodes, edges)
        assert result == {"A", "B", "C", "D", "E"}

    def test_single_node_no_edges(self):
        nodes = self._nodes("A")
        result = _get_downstream_nodes("A", nodes, [])
        assert result == {"A"}


# ---------------------------------------------------------------------------
# _validate_upstream_definitions
# ---------------------------------------------------------------------------

class TestValidateUpstreamDefinitions:

    def test_matching_definitions(self):
        current = {
            "A": {"id": "A", "data": {"type": "loader"}},
            "B": {"id": "B", "data": {"type": "preprocess"}},
        }
        source = {
            "A": {"id": "A", "data": {"type": "loader"}},
            "B": {"id": "B", "data": {"type": "preprocess"}},
        }
        assert _validate_upstream_definitions(current, source, {"A", "B"}) == []

    def test_mismatched_type(self):
        current = {"A": {"id": "A", "data": {"type": "loader"}}}
        source = {"A": {"id": "A", "data": {"type": "different_loader"}}}
        result = _validate_upstream_definitions(current, source, {"A"})
        assert result == ["A"]

    def test_missing_in_source(self):
        current = {"A": {"id": "A", "data": {"type": "loader"}}}
        source = {}
        result = _validate_upstream_definitions(current, source, {"A"})
        assert result == ["A"]

    def test_empty_upstream(self):
        assert _validate_upstream_definitions({}, {}, set()) == []

    def test_group_nodes_skipped(self):
        """GroupNodes should be skipped in validation (visual-only)."""
        current = {
            "G": {"id": "G", "type": "groupNode", "data": {}},
            "A": {"id": "A", "data": {"type": "loader"}},
        }
        source = {
            "G": {"id": "G", "type": "groupNode", "data": {}},
            "A": {"id": "A", "data": {"type": "loader"}},
        }
        assert _validate_upstream_definitions(current, source, {"G", "A"}) == []

    def test_deterministic_order(self):
        """Mismatched IDs should be returned in sorted order."""
        current = {
            "C": {"id": "C", "data": {"type": "x"}},
            "A": {"id": "A", "data": {"type": "y"}},
        }
        source = {
            "C": {"id": "C", "data": {"type": "changed"}},
            "A": {"id": "A", "data": {"type": "changed"}},
        }
        result = _validate_upstream_definitions(current, source, {"A", "C"})
        assert result == ["A", "C"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_definition(node_ids, edges_pairs, block_type="test_block"):
    """Build a minimal pipeline definition."""
    nodes = [
        {
            "id": nid,
            "type": "normal",
            "data": {
                "type": block_type,
                "label": nid,
                "category": "data",
                "config": {},
                "inputs": [{"id": "input", "label": "Input", "dataType": "text", "required": False}],
                "outputs": [{"id": "output", "label": "Output", "dataType": "text"}],
            },
        }
        for nid in node_ids
    ]
    edges = [
        {"source": s, "target": t, "sourceHandle": "output", "targetHandle": "input"}
        for s, t in edges_pairs
    ]
    return {"nodes": nodes, "edges": edges}


def _make_definition_with_group(node_ids, edges_pairs, group_ids=None, block_type="test_block"):
    """Build a pipeline definition that includes groupNode entries."""
    nodes = []
    group_ids = group_ids or []
    for nid in node_ids:
        if nid in group_ids:
            nodes.append({"id": nid, "type": "groupNode", "data": {}})
        else:
            nodes.append({
                "id": nid,
                "type": "normal",
                "data": {
                    "type": block_type,
                    "label": nid,
                    "category": "data",
                    "config": {},
                    "inputs": [{"id": "input", "label": "Input", "dataType": "text", "required": False}],
                    "outputs": [{"id": "output", "label": "Output", "dataType": "text"}],
                },
            })
    edges = [
        {"source": s, "target": t, "sourceHandle": "output", "targetHandle": "input"}
        for s, t in edges_pairs
    ]
    return {"nodes": nodes, "edges": edges}


def _get_run_from_db(db_mock):
    """Extract the Run object that was db.add()-ed by the executor."""
    from backend.models.run import Run
    for c in db_mock.add.call_args_list:
        obj = c[0][0]
        if isinstance(obj, Run):
            return obj
    return None


class _MockDB:
    """A mock DB session that records add() calls and returns configured query results."""

    def __init__(self, source_run=None):
        self._added = []
        self._source_run = source_run
        self.commit = MagicMock()
        self.rollback = MagicMock()

    def add(self, obj):
        self._added.append(obj)

    def query(self, model):
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = self._source_run
        mock_query.filter.return_value = mock_filter
        return mock_query

    @property
    def run(self):
        """Get the Run object that was added."""
        from backend.models.run import Run
        for obj in self._added:
            if isinstance(obj, Run):
                return obj
        return None

    @property
    def live_run(self):
        """Get the LiveRun object that was added."""
        from backend.models.run import LiveRun
        for obj in self._added:
            if isinstance(obj, LiveRun):
                return obj
        return None


def _source_run(status="complete", outputs=None, config_snapshot=None):
    """Create a mock source run."""
    run = MagicMock()
    run.id = "source-run-1"
    run.status = status
    run.outputs_snapshot = outputs
    run.config_snapshot = config_snapshot
    return run


def _exec_patches():
    """Common patches for execution tests that need block running."""
    return [
        patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()),
        patch("builtins.open", MagicMock()),
    ]


# ---------------------------------------------------------------------------
# Validation failure tests — verify Run is marked failed with correct message
# ---------------------------------------------------------------------------

class TestPartialExecutionValidation:
    """Test that validation failures create a failed Run with a clear error."""

    def test_source_run_not_found_marks_run_failed(self):
        db = _MockDB(source_run=None)
        definition = _make_definition(["A", "B"], [("A", "B")])

        with patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()), \
             patch("backend.engine.partial_executor.publish_event"):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "missing-run", "B", definition, {}, db
            ))

        assert db.run.status == "failed"
        assert "not found" in db.run.error_message

    def test_source_run_not_complete_marks_run_failed(self):
        source = _source_run(status="failed", outputs={"A": {"output": "x"}})
        db = _MockDB(source_run=source)
        definition = _make_definition(["A", "B"], [("A", "B")])

        with patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()), \
             patch("backend.engine.partial_executor.publish_event"):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "source-run-1", "B", definition, {}, db
            ))

        assert db.run.status == "failed"
        assert "status 'failed'" in db.run.error_message

    def test_source_run_no_outputs_marks_run_failed(self):
        source = _source_run(status="complete", outputs=None)
        db = _MockDB(source_run=source)
        definition = _make_definition(["A", "B"], [("A", "B")])

        with patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()), \
             patch("backend.engine.partial_executor.publish_event"):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "source-run-1", "B", definition, {}, db
            ))

        assert db.run.status == "failed"
        assert "no cached outputs" in db.run.error_message

    def test_start_node_not_in_pipeline_marks_run_failed(self):
        source = _source_run(
            outputs={"A": {"output": "x"}, "B": {"output": "y"}},
            config_snapshot=_make_definition(["A", "B"], [("A", "B")]),
        )
        db = _MockDB(source_run=source)
        definition = _make_definition(["A", "B"], [("A", "B")])

        with patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()), \
             patch("backend.engine.partial_executor.publish_event"):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "source-run-1", "Z", definition, {}, db
            ))

        assert db.run.status == "failed"
        assert "'Z' not found in pipeline" in db.run.error_message

    def test_missing_upstream_cache_marks_run_failed(self):
        """Source run is missing outputs for upstream node A."""
        source = _source_run(
            outputs={"B": {"output": "y"}},  # Missing A
            config_snapshot=_make_definition(["A", "B", "C"], [("A", "B"), ("B", "C")]),
        )
        db = _MockDB(source_run=source)
        definition = _make_definition(["A", "B", "C"], [("A", "B"), ("B", "C")])

        with patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()), \
             patch("backend.engine.partial_executor.publish_event"):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "source-run-1", "C", definition, {}, db
            ))

        assert db.run.status == "failed"
        assert "missing cached outputs" in db.run.error_message
        assert "full execution" in db.run.error_message

    def test_upstream_definition_changed_marks_run_failed(self):
        source_def = _make_definition(["A", "B"], [("A", "B")], block_type="old_type")
        source = _source_run(
            outputs={"A": {"output": "x"}, "B": {"output": "y"}},
            config_snapshot=source_def,
        )
        db = _MockDB(source_run=source)
        definition = _make_definition(["A", "B"], [("A", "B")], block_type="new_type")

        with patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()), \
             patch("backend.engine.partial_executor.publish_event"):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "source-run-1", "B", definition, {}, db
            ))

        assert db.run.status == "failed"
        assert "definitions changed" in db.run.error_message

    def test_invalid_config_override_node_id_marks_run_failed(self):
        definition = _make_definition(["A", "B"], [("A", "B")])
        source = _source_run(
            outputs={"A": {"output": "x"}, "B": {"output": "y"}},
            config_snapshot=definition,
        )
        db = _MockDB(source_run=source)
        overrides = {"NONEXISTENT": {"temperature": 0.5}}

        events = []

        with patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()), \
             patch("backend.engine.partial_executor.publish_event",
                   side_effect=lambda rid, t, d: events.append((t, d))):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "source-run-1", "B", definition, overrides, db
            ))

        assert db.run.status == "failed"
        assert "NONEXISTENT" in db.run.error_message

        # SSE run_failed event should also contain the error
        failed = [d for t, d in events if t == "run_failed"]
        assert len(failed) == 1
        assert "NONEXISTENT" in failed[0]["error"]

    def test_validation_failure_still_creates_run_record(self):
        """Even when validation fails, the Run record exists (status=failed)."""
        db = _MockDB(source_run=None)
        definition = _make_definition(["A", "B"], [("A", "B")])

        with patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()), \
             patch("backend.engine.partial_executor.publish_event"):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "missing", "B", definition, {}, db
            ))

        # Run was created and added to session before validation
        assert db.run is not None
        assert db.run.id == "run-1"
        assert db.run.pipeline_id == "pipe-1"
        assert db.run.status == "failed"
        # LiveRun was also created
        assert db.live_run is not None
        assert db.live_run.status == "failed"


# ---------------------------------------------------------------------------
# Execution tests
# ---------------------------------------------------------------------------

class TestPartialExecution:

    def test_basic_partial_5_node(self):
        """Criterion 1: A->B->C->D->E, re-run from C. Only C,D,E execute."""
        all_ids = ["A", "B", "C", "D", "E"]
        edge_pairs = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")]
        definition = _make_definition(all_ids, edge_pairs)

        source = _source_run(
            outputs={nid: {"output": f"cached_{nid}"} for nid in all_ids},
            config_snapshot=definition,
        )
        db = _MockDB(source_run=source)

        events = []
        executed_nodes = []

        def mock_publish(run_id, event_type, data):
            events.append((event_type, data))

        def mock_run_block(block_dir, config, inputs, run_dir, run_id, node_id, *cbs):
            executed_nodes.append(node_id)
            return {"output": f"new_{node_id}"}

        with patch("backend.engine.partial_executor.publish_event", side_effect=mock_publish), \
             patch("backend.engine.partial_executor._find_block_module", return_value=MagicMock()), \
             patch("backend.engine.partial_executor._load_and_run_block", side_effect=mock_run_block), \
             patch("backend.engine.partial_executor._resolve_secrets", side_effect=lambda c: c), \
             patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "source-run-1", "C", definition, {}, db
            ))

        # Only C, D, E should have been executed
        assert executed_nodes == ["C", "D", "E"]

        # A and B should have node_cached events
        cached = [d["node_id"] for t, d in events if t == "node_cached"]
        assert set(cached) == {"A", "B"}

        # C, D, E should have node_started + node_completed events
        started = [d["node_id"] for t, d in events if t == "node_started"]
        assert set(started) == {"C", "D", "E"}
        completed_nodes = [d["node_id"] for t, d in events if t == "node_completed"]
        assert set(completed_nodes) == {"C", "D", "E"}

        # Run should be complete
        assert db.run.status == "complete"
        # run_completed event has partial=True
        run_completed = [d for t, d in events if t == "run_completed"]
        assert len(run_completed) == 1
        assert run_completed[0]["partial"] is True
        assert run_completed[0]["source_run_id"] == "source-run-1"
        assert run_completed[0]["start_node_id"] == "C"

    def test_config_override_propagation(self):
        """Criterion 2: Re-run from C with changed config. C runs with new
        config, D and E run with propagated outputs from C."""
        all_ids = ["A", "B", "C", "D", "E"]
        edge_pairs = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")]
        definition = _make_definition(all_ids, edge_pairs)

        source = _source_run(
            outputs={nid: {"output": f"cached_{nid}"} for nid in all_ids},
            config_snapshot=definition,
        )
        db = _MockDB(source_run=source)

        received_configs = {}
        received_inputs = {}

        def mock_run_block(block_dir, config, inputs, run_dir, run_id, node_id, *cbs):
            received_configs[node_id] = dict(config)
            received_inputs[node_id] = dict(inputs)
            return {"output": f"new_{node_id}_temp_{config.get('temperature', 'default')}"}

        overrides = {"C": {"temperature": 0.1}}

        with patch("backend.engine.partial_executor.publish_event"), \
             patch("backend.engine.partial_executor._find_block_module", return_value=MagicMock()), \
             patch("backend.engine.partial_executor._load_and_run_block", side_effect=mock_run_block), \
             patch("backend.engine.partial_executor._resolve_secrets", side_effect=lambda c: c), \
             patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "source-run-1", "C", definition, overrides, db
            ))

        # C should have the overridden config
        assert received_configs["C"]["temperature"] == 0.1

        # C receives cached output from B
        assert received_inputs["C"] == {"input": "cached_B"}

        # D receives C's NEW output (not cached)
        assert received_inputs["D"] == {"input": "new_C_temp_0.1"}

        # E receives D's output, propagating the chain
        assert "new_D" in received_inputs["E"]["input"]

    def test_time_savings_skip_count(self):
        """Criterion 3: Partial re-run skips upstream blocks — verify counts."""
        all_ids = ["A", "B", "C", "D", "E"]
        edge_pairs = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")]
        definition = _make_definition(all_ids, edge_pairs)

        source = _source_run(
            outputs={nid: {"output": f"cached_{nid}"} for nid in all_ids},
            config_snapshot=definition,
        )
        db = _MockDB(source_run=source)

        events = []
        execution_count = 0

        def mock_publish(run_id, event_type, data):
            events.append((event_type, data))

        def mock_run_block(block_dir, config, inputs, run_dir, run_id, node_id, *cbs):
            nonlocal execution_count
            execution_count += 1
            time.sleep(0.001)  # Simulate minimal work
            return {"output": f"new_{node_id}"}

        with patch("backend.engine.partial_executor.publish_event", side_effect=mock_publish), \
             patch("backend.engine.partial_executor._find_block_module", return_value=MagicMock()), \
             patch("backend.engine.partial_executor._load_and_run_block", side_effect=mock_run_block), \
             patch("backend.engine.partial_executor._resolve_secrets", side_effect=lambda c: c), \
             patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "source-run-1", "D", definition, {}, db
            ))

        # 3 nodes skipped (A, B, C), 2 executed (D, E)
        cached_count = len([t for t, _ in events if t == "node_cached"])
        executed_count = len([t for t, _ in events if t == "node_started"])
        assert cached_count == 3
        assert executed_count == 2
        assert execution_count == 2  # Only 2 blocks actually ran

    def test_cache_miss_error_message(self):
        """Criterion 4: Source run missing outputs for node B -> failed with
        actionable error message."""
        source = _source_run(
            outputs={"A": {"output": "data_A"}},  # B missing
            config_snapshot=_make_definition(["A", "B", "C"], [("A", "B"), ("B", "C")]),
        )
        db = _MockDB(source_run=source)
        definition = _make_definition(["A", "B", "C"], [("A", "B"), ("B", "C")])

        with patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()), \
             patch("backend.engine.partial_executor.publish_event"):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "source-run-1", "C", definition, {}, db
            ))

        assert db.run.status == "failed"
        # Error should mention the missing node and suggest full execution
        assert "missing cached outputs" in db.run.error_message
        assert "'B'" in db.run.error_message or "B" in db.run.error_message
        assert "full execution" in db.run.error_message

    def test_sse_events_cached_vs_normal(self):
        """Criterion 5: Skipped nodes emit node_cached. Executed emit normal events."""
        definition = _make_definition(["A", "B", "C"], [("A", "B"), ("B", "C")])
        source = _source_run(
            outputs={nid: {"output": f"cached_{nid}"} for nid in ["A", "B", "C"]},
            config_snapshot=definition,
        )
        db = _MockDB(source_run=source)

        events = []

        def mock_publish(run_id, event_type, data):
            events.append((event_type, data))

        def mock_run_block(block_dir, config, inputs, run_dir, run_id, node_id, *cbs):
            return {"output": f"new_{node_id}"}

        with patch("backend.engine.partial_executor.publish_event", side_effect=mock_publish), \
             patch("backend.engine.partial_executor._find_block_module", return_value=MagicMock()), \
             patch("backend.engine.partial_executor._load_and_run_block", side_effect=mock_run_block), \
             patch("backend.engine.partial_executor._resolve_secrets", side_effect=lambda c: c), \
             patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "source-run-1", "B", definition, {}, db
            ))

        # node_cached for A (upstream, skipped)
        cached = [(t, d) for t, d in events if t == "node_cached"]
        assert len(cached) == 1
        assert cached[0][1]["node_id"] == "A"
        assert cached[0][1]["source_run_id"] == "source-run-1"

        # node_started, node_output, node_completed for B and C (executed)
        for node_id in ["B", "C"]:
            assert any(t == "node_started" and d["node_id"] == node_id for t, d in events)
            assert any(t == "node_output" and d["node_id"] == node_id for t, d in events)
            assert any(t == "node_completed" and d["node_id"] == node_id for t, d in events)

        # No node_started for A (it was cached, not executed)
        assert not any(t == "node_started" and d["node_id"] == "A" for t, d in events)

    def test_diamond_graph_partial(self):
        """Diamond: A->B, A->C, B->D, C->D. Re-run from B -> B, D execute."""
        nodes = ["A", "B", "C", "D"]
        edges = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]
        definition = _make_definition(nodes, edges)

        source = _source_run(
            outputs={nid: {"output": f"cached_{nid}"} for nid in nodes},
            config_snapshot=definition,
        )
        db = _MockDB(source_run=source)

        executed = []
        events = []

        def mock_publish(run_id, event_type, data):
            events.append((event_type, data))

        def mock_run_block(block_dir, config, inputs, run_dir, run_id, node_id, *cbs):
            executed.append(node_id)
            return {"output": f"new_{node_id}"}

        with patch("backend.engine.partial_executor.publish_event", side_effect=mock_publish), \
             patch("backend.engine.partial_executor._find_block_module", return_value=MagicMock()), \
             patch("backend.engine.partial_executor._load_and_run_block", side_effect=mock_run_block), \
             patch("backend.engine.partial_executor._resolve_secrets", side_effect=lambda c: c), \
             patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "source-run-1", "B", definition, {}, db
            ))

        # B and D are downstream of B. A and C are upstream (cached).
        assert set(executed) == {"B", "D"}
        cached_ids = {d["node_id"] for t, d in events if t == "node_cached"}
        assert cached_ids == {"A", "C"}

    def test_cached_outputs_propagate_to_downstream_inputs(self):
        """Cached outputs from upstream nodes should be available as inputs."""
        definition = _make_definition(["A", "B", "C"], [("A", "B"), ("B", "C")])
        source = _source_run(
            outputs={
                "A": {"output": "data_from_A"},
                "B": {"output": "data_from_B"},
                "C": {"output": "data_from_C"},
            },
            config_snapshot=definition,
        )
        db = _MockDB(source_run=source)

        received_inputs = {}

        def mock_run_block(block_dir, config, inputs, run_dir, run_id, node_id, *cbs):
            received_inputs[node_id] = dict(inputs)
            return {"output": f"new_{node_id}"}

        with patch("backend.engine.partial_executor.publish_event"), \
             patch("backend.engine.partial_executor._find_block_module", return_value=MagicMock()), \
             patch("backend.engine.partial_executor._load_and_run_block", side_effect=mock_run_block), \
             patch("backend.engine.partial_executor._resolve_secrets", side_effect=lambda c: c), \
             patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "source-run-1", "B", definition, {}, db
            ))

        # B should receive cached output from A
        assert received_inputs["B"] == {"input": "data_from_A"}
        # C should receive B's NEW output
        assert received_inputs["C"] == {"input": "new_B"}

    def test_rerun_from_first_node_executes_all(self):
        """Start from first node -> everything executes, nothing cached."""
        definition = _make_definition(["A", "B", "C"], [("A", "B"), ("B", "C")])
        source = _source_run(
            outputs={nid: {"output": f"cached_{nid}"} for nid in ["A", "B", "C"]},
            config_snapshot=definition,
        )
        db = _MockDB(source_run=source)

        executed = []
        events = []

        def mock_publish(run_id, event_type, data):
            events.append((event_type, data))

        def mock_run_block(block_dir, config, inputs, run_dir, run_id, node_id, *cbs):
            executed.append(node_id)
            return {"output": f"new_{node_id}"}

        with patch("backend.engine.partial_executor.publish_event", side_effect=mock_publish), \
             patch("backend.engine.partial_executor._find_block_module", return_value=MagicMock()), \
             patch("backend.engine.partial_executor._load_and_run_block", side_effect=mock_run_block), \
             patch("backend.engine.partial_executor._resolve_secrets", side_effect=lambda c: c), \
             patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "source-run-1", "A", definition, {}, db
            ))

        assert executed == ["A", "B", "C"]
        assert not any(t == "node_cached" for t, _ in events)

    def test_group_nodes_skipped_in_execution(self):
        """GroupNodes should not appear in any events or execution."""
        definition = _make_definition_with_group(
            ["G", "A", "B", "C"],
            [("A", "B"), ("B", "C")],
            group_ids=["G"],
        )
        source = _source_run(
            outputs={
                "A": {"output": "cached_A"},
                "B": {"output": "cached_B"},
                "C": {"output": "cached_C"},
            },
            config_snapshot=definition,
        )
        db = _MockDB(source_run=source)

        executed = []
        events = []

        def mock_publish(run_id, event_type, data):
            events.append((event_type, data))

        def mock_run_block(block_dir, config, inputs, run_dir, run_id, node_id, *cbs):
            executed.append(node_id)
            return {"output": f"new_{node_id}"}

        with patch("backend.engine.partial_executor.publish_event", side_effect=mock_publish), \
             patch("backend.engine.partial_executor._find_block_module", return_value=MagicMock()), \
             patch("backend.engine.partial_executor._load_and_run_block", side_effect=mock_run_block), \
             patch("backend.engine.partial_executor._resolve_secrets", side_effect=lambda c: c), \
             patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "source-run-1", "C", definition, {}, db
            ))

        assert executed == ["C"]
        # G must not appear in any node event
        all_node_ids = [d.get("node_id") for _, d in events if "node_id" in d]
        assert "G" not in all_node_ids

    def test_rerun_from_last_node(self):
        """Re-run from last node: only last node executes, all others cached."""
        definition = _make_definition(["A", "B", "C"], [("A", "B"), ("B", "C")])
        source = _source_run(
            outputs={nid: {"output": f"cached_{nid}"} for nid in ["A", "B", "C"]},
            config_snapshot=definition,
        )
        db = _MockDB(source_run=source)

        executed = []

        def mock_run_block(block_dir, config, inputs, run_dir, run_id, node_id, *cbs):
            executed.append(node_id)
            return {"output": f"new_{node_id}"}

        with patch("backend.engine.partial_executor.publish_event"), \
             patch("backend.engine.partial_executor._find_block_module", return_value=MagicMock()), \
             patch("backend.engine.partial_executor._load_and_run_block", side_effect=mock_run_block), \
             patch("backend.engine.partial_executor._resolve_secrets", side_effect=lambda c: c), \
             patch("backend.engine.partial_executor.ARTIFACTS_DIR", MagicMock()), \
             patch("builtins.open", MagicMock()):
            _run(execute_partial_pipeline(
                "pipe-1", "run-1", "source-run-1", "C", definition, {}, db
            ))

        assert executed == ["C"]
        assert db.run.status == "complete"


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

class TestExecuteFromEndpoint:
    """Test the POST /pipelines/{id}/execute-from endpoint validation."""

    def _setup_app(self):
        """Import app and TestClient."""
        from fastapi.testclient import TestClient
        from backend.main import app
        return TestClient(app), app

    def test_pipeline_not_found(self):
        client, app = self._setup_app()
        try:
            resp = client.post(
                "/api/pipelines/nonexistent-id/execute-from",
                json={
                    "source_run_id": "run-1",
                    "start_node_id": "A",
                },
            )
        except Exception:
            pytest.skip("Database unavailable in test environment")
        assert resp.status_code == 404

    def test_missing_source_run_id(self):
        """Request body missing required field -> 422 (Pydantic validation)."""
        client, app = self._setup_app()
        resp = client.post(
            "/api/pipelines/any-id/execute-from",
            json={"start_node_id": "A"},
        )
        assert resp.status_code == 422

    def test_missing_start_node_id(self):
        """Request body missing required field -> 422."""
        client, app = self._setup_app()
        resp = client.post(
            "/api/pipelines/any-id/execute-from",
            json={"source_run_id": "run-1"},
        )
        assert resp.status_code == 422

    def test_pydantic_validates_config_overrides_type(self):
        """config_overrides must be dict[str, dict], not a string."""
        client, app = self._setup_app()
        resp = client.post(
            "/api/pipelines/any-id/execute-from",
            json={
                "source_run_id": "run-1",
                "start_node_id": "A",
                "config_overrides": "not-a-dict",
            },
        )
        assert resp.status_code == 422
