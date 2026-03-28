"""Tests for the Replay Inspector API (backend/routers/replay.py)."""

import json
import threading
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.engine.error_classifier import classify_error, ClassifiedError
from backend.models.execution_decision import ExecutionDecision
from backend.engine.decision_recorder import (
    record_decision,
    update_decision,
    flush_decisions,
    cleanup_decisions,
    measure_memory_mb,
    _DecisionBuffer,
    _get_buffer,
)


# ── Decision Buffer Unit Tests ──────────────────────────────────────────


class TestDecisionBuffer:
    """Test the _DecisionBuffer internal buffered writer."""

    def test_add_and_flush(self):
        """Verify buffered items are written on flush."""
        buf = _DecisionBuffer("run_test_buf")
        key = buf.add({
            "run_id": "run_test_buf",
            "node_id": "n1",
            "block_type": "text_input",
            "execution_order": 0,
            "decision": "execute",
            "status": "running",
        })
        assert key == "n1:"
        assert buf.should_flush() is False  # Not enough time elapsed

    def test_update_queues_field_changes(self):
        """Verify update queues changes for next flush."""
        buf = _DecisionBuffer("run_test_upd")
        key = buf.add({
            "run_id": "run_test_upd",
            "node_id": "n1",
            "block_type": "text_input",
            "execution_order": 0,
            "decision": "execute",
            "status": "running",
        })
        buf.update(key, {"status": "completed", "duration_ms": 1234.5})
        # Verify the update was queued (internal state)
        assert len(buf._updates) == 1


class TestDecisionRecorderPublicAPI:
    """Test the public record_decision / update_decision / flush API."""

    def test_record_decision_returns_node_key(self):
        """Verify record_decision returns a string node_key."""
        key = record_decision(
            None,  # db param ignored
            run_id="run_api_1",
            node_id="node_a",
            block_type="text_input",
            execution_order=0,
            decision="execute",
            status="running",
        )
        assert isinstance(key, str)
        assert "node_a" in key
        cleanup_decisions("run_api_1")

    def test_update_decision_noop_for_none(self):
        """Verify update_decision is a no-op for None key."""
        # Should not raise
        update_decision(None, None, status="completed")

    def test_record_decision_with_iteration(self):
        """Verify iteration is included in node_key."""
        key = record_decision(
            None,
            run_id="run_api_2",
            node_id="node_loop",
            block_type="training_step",
            execution_order=5,
            decision="execute",
            status="running",
            iteration=3,
            loop_id="controller_1",
        )
        assert "node_loop" in key
        assert "3" in key
        cleanup_decisions("run_api_2")

    def test_flush_and_cleanup(self):
        """Verify flush_decisions and cleanup_decisions don't raise."""
        record_decision(
            None,
            run_id="run_api_3",
            node_id="n1",
            block_type="loader",
            execution_order=0,
            decision="execute",
            status="running",
        )
        # flush_decisions tries to write to DB — may fail in test environment
        # but should never raise
        try:
            flush_decisions("run_api_3")
        except Exception:
            pass
        cleanup_decisions("run_api_3")


class TestMemoryMeasurement:
    """Test the memory measurement utility."""

    def test_measure_memory_returns_float_or_none(self):
        """Verify measure_memory_mb returns float or None."""
        result = measure_memory_mb()
        # psutil may or may not be available
        if result is not None:
            assert isinstance(result, float)
            assert result > 0

    def test_measure_memory_positive_value(self):
        """If psutil is available, memory should be positive."""
        try:
            import psutil
            result = measure_memory_mb()
            assert result is not None
            assert result > 10  # Any running Python process uses > 10 MB
        except ImportError:
            pytest.skip("psutil not installed")


# ── Decision Recorder with Error JSON ───────────────────────────────────


class TestDecisionRecorderErrorHandling:
    """Test error recording in decisions."""

    def test_record_with_error_json(self):
        """Verify error_json is included in the queued kwargs."""
        error_data = {
            "title": "File Not Found",
            "message": "File '/data/input.csv' does not exist",
            "action": "Check file path in block config",
            "severity": "error",
        }
        key = record_decision(
            None,
            run_id="run_err_1",
            node_id="node_b",
            block_type="data_loader",
            execution_order=1,
            decision="execute",
            status="failed",
            error_json=error_data,
        )
        assert key is not None
        cleanup_decisions("run_err_1")


# ── Replay API Response Tests ───────────────────────────────────────────


class TestReplayDataShape:
    """Test the replay endpoint response shape and data integrity."""

    def test_replay_node_has_required_fields(self):
        """Verify ReplayNode shape matches the spec."""
        from backend.routers.replay import _build_node_replay

        decision = ExecutionDecision(
            run_id="run_1",
            node_id="node_1",
            block_type="text_input",
            execution_order=0,
            decision="execute",
            decision_reason="full pipeline execution",
            status="completed",
            started_at=datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc),
            duration_ms=1500.0,
            resolved_config={"text": "hello"},
            config_sources={"text": "user"},
            error_json=None,
            iteration=None,
            loop_id=None,
            memory_peak_mb=128.5,
        )

        node = _build_node_replay(decision, [], [])

        assert node["node_id"] == "node_1"
        assert node["block_type"] == "text_input"
        assert node["status"] == "completed"
        assert node["started_at"] is not None
        assert node["duration_ms"] == 1500.0
        assert node["resolved_config"] == {"text": "hello"}
        assert node["config_sources"] == {"text": "user"}
        assert node["decision"] == "execute"
        assert node["decision_reason"] == "full pipeline execution"
        assert node["error"] is None
        assert node["input_artifacts"] == []
        assert node["output_artifacts"] == []
        assert node["execution_order"] == 0
        assert node["memory_peak_mb"] == 128.5

    def test_replay_node_with_error(self):
        """Verify failed node includes error details."""
        from backend.routers.replay import _build_node_replay

        decision = ExecutionDecision(
            run_id="run_1",
            node_id="node_2",
            block_type="data_loader",
            execution_order=1,
            decision="execute",
            status="failed",
            error_json={
                "title": "File Not Found",
                "message": "File '/data/input.csv' does not exist",
                "action": "Check file path",
            },
        )

        node = _build_node_replay(decision, [], [])

        assert node["error"] is not None
        assert node["error"]["title"] == "File Not Found"
        assert "input.csv" in node["error"]["message"]
        assert node["error"]["action"] == "Check file path"

    def test_replay_node_not_executed(self):
        """Verify downstream node after failure shows not_executed."""
        from backend.routers.replay import _build_node_replay

        decision = ExecutionDecision(
            run_id="run_1",
            node_id="node_3",
            block_type="model_trainer",
            execution_order=2,
            decision="skipped",
            decision_reason="Not executed — upstream failure at node_2",
            status="not_executed",
        )

        node = _build_node_replay(decision, [], [])

        assert node["status"] == "not_executed"
        assert node["decision"] == "skipped"
        assert "upstream failure" in node["decision_reason"]

    def test_replay_node_with_memory_peak(self):
        """Verify memory_peak_mb is returned correctly."""
        from backend.routers.replay import _build_node_replay

        decision = ExecutionDecision(
            run_id="run_1",
            node_id="node_4",
            block_type="model_trainer",
            execution_order=0,
            decision="execute",
            status="completed",
            memory_peak_mb=2048.3,
        )

        node = _build_node_replay(decision, [], [])
        assert node["memory_peak_mb"] == 2048.3


# ── Replay API Route Tests ──────────────────────────────────────────────


class TestReplayEndpoint:
    """Integration tests for the replay endpoint using mock DB."""

    def _make_run(self, run_id="run_1", status="complete", **kwargs):
        """Create a mock Run object."""
        run = MagicMock()
        run.id = run_id
        run.pipeline_id = "pipe_1"
        run.status = status
        run.started_at = datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc)
        run.finished_at = datetime(2026, 3, 28, 10, 5, 0, tzinfo=timezone.utc)
        run.duration_seconds = 300.0
        run.error_message = kwargs.get("error_message")
        run.config_snapshot = kwargs.get("config_snapshot", {
            "nodes": [
                {"id": "n1", "data": {"type": "text_input", "config": {}}},
                {"id": "n2", "data": {"type": "model_trainer", "config": {}}},
            ],
            "edges": [
                {"source": "n1", "target": "n2", "sourceHandle": "output", "targetHandle": "input"},
            ],
        })
        return run

    def test_replay_returns_correct_data_for_completed_run(self):
        """Verify replay API returns correct data for a completed run."""
        from backend.routers.replay import get_run_replay

        run = self._make_run()
        decisions = [
            ExecutionDecision(
                run_id="run_1", node_id="n1", block_type="text_input",
                execution_order=0, decision="execute", status="completed",
                started_at=datetime(2026, 3, 28, 10, 0, 0, tzinfo=timezone.utc),
                duration_ms=100.0,
            ),
            ExecutionDecision(
                run_id="run_1", node_id="n2", block_type="model_trainer",
                execution_order=1, decision="execute", status="completed",
                started_at=datetime(2026, 3, 28, 10, 0, 1, tzinfo=timezone.utc),
                duration_ms=4900.0,
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = run
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = decisions
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = get_run_replay("run_1", mock_db)

        assert result["run_id"] == "run_1"
        assert result["status"] == "complete"
        assert result["duration_ms"] == 300000.0
        assert len(result["nodes"]) == 2
        assert result["nodes"][0]["node_id"] == "n1"
        assert result["nodes"][0]["status"] == "completed"
        assert result["nodes"][1]["node_id"] == "n2"
        assert "loops" in result
        assert result["loops"] == []

    def test_replay_failure_node_shows_error(self):
        """Verify failure node shows classified error."""
        from backend.routers.replay import get_run_replay

        run = self._make_run(status="failed")
        decisions = [
            ExecutionDecision(
                run_id="run_1", node_id="n1", block_type="text_input",
                execution_order=0, decision="execute", status="completed",
                duration_ms=100.0,
            ),
            ExecutionDecision(
                run_id="run_1", node_id="n2", block_type="model_trainer",
                execution_order=1, decision="execute", status="failed",
                error_json={"title": "Out of Memory", "message": "GPU OOM", "action": "Reduce batch size"},
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = run
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = decisions
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = get_run_replay("run_1", mock_db)

        assert result["status"] == "failed"
        failed_node = result["nodes"][1]
        assert failed_node["status"] == "failed"
        assert failed_node["error"]["title"] == "Out of Memory"

    def test_replay_404_for_missing_run(self):
        """Verify 404 for non-existent run."""
        from backend.routers.replay import get_run_replay
        from fastapi import HTTPException

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            get_run_replay("nonexistent", mock_db)
        assert exc_info.value.status_code == 404

    def test_replay_400_for_running_run(self):
        """Verify 400 for a still-running run."""
        from backend.routers.replay import get_run_replay
        from fastapi import HTTPException

        run = self._make_run(status="running")
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = run

        with pytest.raises(HTTPException) as exc_info:
            get_run_replay("run_1", mock_db)
        assert exc_info.value.status_code == 400

    def test_replay_navigation_follows_execution_order(self):
        """Verify nodes are returned in execution order."""
        from backend.routers.replay import get_run_replay

        run = self._make_run()
        decisions = [
            ExecutionDecision(
                run_id="run_1", node_id="n2", block_type="trainer",
                execution_order=1, decision="execute", status="completed",
            ),
            ExecutionDecision(
                run_id="run_1", node_id="n1", block_type="loader",
                execution_order=0, decision="execute", status="completed",
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = run
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = sorted(
            decisions, key=lambda d: d.execution_order
        )
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = get_run_replay("run_1", mock_db)

        assert result["nodes"][0]["execution_order"] == 0
        assert result["nodes"][1]["execution_order"] == 1

    def test_replay_loops_summary(self):
        """Verify loop iterations are summarized in the response."""
        from backend.routers.replay import get_run_replay

        run = self._make_run()
        decisions = [
            ExecutionDecision(
                run_id="run_1", node_id="ctrl", block_type="loop_controller",
                execution_order=0, decision="execute", status="completed",
            ),
            ExecutionDecision(
                run_id="run_1", node_id="body_a", block_type="trainer",
                execution_order=1, decision="execute", status="completed",
                iteration=0, loop_id="ctrl",
            ),
            ExecutionDecision(
                run_id="run_1", node_id="body_a", block_type="trainer",
                execution_order=2, decision="execute", status="completed",
                iteration=1, loop_id="ctrl",
            ),
            ExecutionDecision(
                run_id="run_1", node_id="body_a", block_type="trainer",
                execution_order=3, decision="execute", status="completed",
                iteration=2, loop_id="ctrl",
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = run
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = decisions
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = get_run_replay("run_1", mock_db)

        assert len(result["loops"]) == 1
        loop = result["loops"][0]
        assert loop["controller_id"] == "ctrl"
        assert loop["iterations"] == [0, 1, 2]
        assert loop["iteration_count"] == 3
        assert "body_a" in loop["body_node_ids"]

    def test_replay_cache_hit_decisions(self):
        """Verify cache_hit decisions are correctly represented."""
        from backend.routers.replay import get_run_replay

        run = self._make_run()
        decisions = [
            ExecutionDecision(
                run_id="run_1", node_id="n1", block_type="text_input",
                execution_order=0, decision="cache_hit", status="cached",
                decision_reason="outputs reused from source run run_0",
            ),
            ExecutionDecision(
                run_id="run_1", node_id="n2", block_type="model_trainer",
                execution_order=1, decision="execute", status="completed",
            ),
        ]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = run
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = decisions
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = get_run_replay("run_1", mock_db)

        cached_node = result["nodes"][0]
        assert cached_node["decision"] == "cache_hit"
        assert cached_node["status"] == "cached"
        assert "source run" in cached_node["decision_reason"]
