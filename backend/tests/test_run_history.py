"""Tests for the run history service (Risk 1 fix)."""

import time
import pytest
from unittest.mock import MagicMock

from backend.services.run_history import (
    gather_run_history,
    _parse_block_types_from_snapshot,
    _parse_node_durations,
    _parse_node_memory,
    _extract_node_records,
)
from backend.engine.planner_models import ExecutionPlan, ResolvedNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolved_node(node_id: str, block_type: str) -> ResolvedNode:
    return ResolvedNode(
        node_id=node_id,
        block_type=block_type,
        block_version="1.0.0",
        resolved_config={},
        config_sources={},
        cache_fingerprint="abc",
        cache_eligible=True,
        in_loop=False,
        loop_id=None,
    )


def _make_plan(nodes: dict[str, ResolvedNode]) -> ExecutionPlan:
    return ExecutionPlan(
        execution_order=tuple(nodes.keys()),
        nodes=nodes,
        loops=(),
        independent_subgraphs=(),
        plan_hash="test",
        warnings=(),
    )


def _make_run(
    run_id: str = "run-1",
    pipeline_id: str = "pipe-1",
    status: str = "complete",
    duration_seconds: float = 300.0,
    config_snapshot: dict | None = None,
    metrics_log: list | None = None,
) -> MagicMock:
    """Create a mock Run object."""
    run = MagicMock()
    run.id = run_id
    run.pipeline_id = pipeline_id
    run.status = status
    run.duration_seconds = duration_seconds
    run.finished_at = MagicMock()
    run.config_snapshot = config_snapshot
    run.metrics_log = metrics_log
    return run


# ---------------------------------------------------------------------------
# config_snapshot parsing
# ---------------------------------------------------------------------------

class TestParseBlockTypesFromSnapshot:
    def test_list_format(self):
        """Standard format: nodes is an array of node objects."""
        snapshot = {
            "nodes": [
                {"id": "n1", "type": "default", "data": {"type": "lora_finetuning", "label": "Train"}},
                {"id": "n2", "type": "default", "data": {"type": "text_generation", "label": "Gen"}},
                {"id": "n3", "type": "groupNode", "data": {}},  # Visual node, no block type
            ],
            "edges": [],
        }
        result = _parse_block_types_from_snapshot(snapshot)
        assert result == {"n1": "lora_finetuning", "n2": "text_generation"}

    def test_dict_format(self):
        """Alternate format: nodes is a dict keyed by node_id."""
        snapshot = {
            "nodes": {
                "n1": {"block_type": "lora_finetuning"},
                "n2": {"type": "text_generation"},
            },
        }
        result = _parse_block_types_from_snapshot(snapshot)
        assert result == {"n1": "lora_finetuning", "n2": "text_generation"}

    def test_none_snapshot(self):
        assert _parse_block_types_from_snapshot(None) == {}

    def test_empty_snapshot(self):
        assert _parse_block_types_from_snapshot({}) == {}

    def test_missing_data_key(self):
        """Nodes without data.type are skipped."""
        snapshot = {"nodes": [{"id": "n1"}]}
        assert _parse_block_types_from_snapshot(snapshot) == {}


# ---------------------------------------------------------------------------
# metrics_log duration parsing
# ---------------------------------------------------------------------------

class TestParseNodeDurations:
    def test_extracts_durations(self):
        """Correctly compute duration from started/completed timestamp pairs."""
        base = time.time()
        log = [
            {"type": "node_started", "node_id": "n1", "timestamp": base},
            {"type": "node_started", "node_id": "n2", "timestamp": base + 10},
            {"type": "node_completed", "node_id": "n1", "timestamp": base + 60},
            {"type": "node_completed", "node_id": "n2", "timestamp": base + 120},
        ]
        durations = _parse_node_durations(log)
        assert abs(durations["n1"] - 60.0) < 0.01
        assert abs(durations["n2"] - 110.0) < 0.01

    def test_handles_missing_start(self):
        """Completed event without a matching start is ignored."""
        log = [
            {"type": "node_completed", "node_id": "n1", "timestamp": 1000},
        ]
        assert _parse_node_durations(log) == {}

    def test_handles_none_log(self):
        assert _parse_node_durations(None) == {}

    def test_handles_empty_log(self):
        assert _parse_node_durations([]) == {}

    def test_handles_malformed_events(self):
        """Non-dict or missing fields are safely skipped."""
        log = [
            "not a dict",
            {"type": "node_started"},  # missing node_id and timestamp
            {"type": "node_started", "node_id": "n1", "timestamp": "not_a_number"},
            {"type": "node_started", "node_id": "n1", "timestamp": 100},
            {"type": "node_completed", "node_id": "n1", "timestamp": 200},
        ]
        durations = _parse_node_durations(log)
        assert abs(durations["n1"] - 100.0) < 0.01

    def test_last_start_wins_for_retries(self):
        """If a node is started multiple times (retries), use the last start."""
        log = [
            {"type": "node_started", "node_id": "n1", "timestamp": 100},
            {"type": "node_started", "node_id": "n1", "timestamp": 200},  # retry
            {"type": "node_completed", "node_id": "n1", "timestamp": 250},
        ]
        durations = _parse_node_durations(log)
        assert abs(durations["n1"] - 50.0) < 0.01


# ---------------------------------------------------------------------------
# metrics_log memory parsing
# ---------------------------------------------------------------------------

class TestParseNodeMemory:
    def test_block_logged_peak_memory_gb(self):
        """Block-logged peak_memory_gb metric is converted to MB."""
        log = [
            {"type": "node_started", "node_id": "n1"},
            {"type": "metric", "node_id": "n1", "name": "peak_memory_gb", "value": 8.5},
            {"type": "node_completed", "node_id": "n1"},
        ]
        mem = _parse_node_memory(log)
        assert mem["n1"] == 8704  # 8.5 * 1024

    def test_block_logged_peak_memory_mb(self):
        """Block-logged peak_memory_mb metric used directly."""
        log = [
            {"type": "metric", "node_id": "n1", "name": "peak_memory_mb", "value": 4096},
        ]
        mem = _parse_node_memory(log)
        assert mem["n1"] == 4096

    def test_system_metric_fallback(self):
        """When no block metric exists, use system_metric mem_gb as fallback."""
        log = [
            {"type": "node_started", "node_id": "n1"},
            {"type": "system_metric", "mem_gb": 12.5, "timestamp": 100},
            {"type": "system_metric", "mem_gb": 16.0, "timestamp": 110},
            {"type": "node_completed", "node_id": "n1"},
        ]
        mem = _parse_node_memory(log)
        assert mem["n1"] == 16384  # max(12.5, 16.0) * 1024

    def test_block_metric_overrides_system(self):
        """Block-level metric takes priority over system-level."""
        log = [
            {"type": "node_started", "node_id": "n1"},
            {"type": "system_metric", "mem_gb": 20.0},
            {"type": "metric", "node_id": "n1", "name": "peak_memory_gb", "value": 8.0},
            {"type": "node_completed", "node_id": "n1"},
        ]
        mem = _parse_node_memory(log)
        assert mem["n1"] == 8192  # Block metric wins

    def test_handles_none(self):
        assert _parse_node_memory(None) == {}


# ---------------------------------------------------------------------------
# Full record extraction
# ---------------------------------------------------------------------------

class TestExtractNodeRecords:
    def test_full_extraction_pipeline(self):
        """End-to-end: extract records from a run with all data sources."""
        base = time.time()
        run = _make_run(
            config_snapshot={
                "nodes": [
                    {"id": "n1", "data": {"type": "lora_finetuning"}},
                    {"id": "n2", "data": {"type": "text_generation"}},
                ],
            },
            metrics_log=[
                {"type": "node_started", "node_id": "n1", "timestamp": base},
                {"type": "metric", "node_id": "n1", "name": "peak_memory_gb", "value": 14.0},
                {"type": "node_completed", "node_id": "n1", "timestamp": base + 300},
                {"type": "node_started", "node_id": "n2", "timestamp": base + 301},
                {"type": "node_completed", "node_id": "n2", "timestamp": base + 360},
            ],
            duration_seconds=360.0,
        )

        records = _extract_node_records(run, {"lora_finetuning", "text_generation"})

        assert len(records) == 2

        train_record = next(r for r in records if r["block_type"] == "lora_finetuning")
        assert abs(train_record["duration_seconds"] - 300.0) < 0.01
        assert train_record["peak_memory_mb"] == 14336

        gen_record = next(r for r in records if r["block_type"] == "text_generation")
        assert abs(gen_record["duration_seconds"] - 59.0) < 0.01

    def test_fallback_to_total_duration(self):
        """When metrics_log has no timing, divide total duration across nodes."""
        run = _make_run(
            config_snapshot={
                "nodes": [
                    {"id": "n1", "data": {"type": "lora_finetuning"}},
                    {"id": "n2", "data": {"type": "text_generation"}},
                ],
            },
            metrics_log=[],  # No per-node timing
            duration_seconds=600.0,
        )

        records = _extract_node_records(run, {"lora_finetuning"})

        assert len(records) == 1
        assert records[0]["block_type"] == "lora_finetuning"
        assert records[0]["duration_seconds"] == 300.0  # 600 / 2 nodes

    def test_filters_to_target_block_types(self):
        """Only returns records for block types we're interested in."""
        run = _make_run(
            config_snapshot={
                "nodes": [
                    {"id": "n1", "data": {"type": "csv_loader"}},
                    {"id": "n2", "data": {"type": "lora_finetuning"}},
                ],
            },
            metrics_log=[],
            duration_seconds=100.0,
        )

        records = _extract_node_records(run, {"lora_finetuning"})

        assert len(records) == 1
        assert records[0]["block_type"] == "lora_finetuning"

    def test_empty_config_snapshot(self):
        """Run with no config_snapshot returns empty."""
        run = _make_run(config_snapshot=None)
        records = _extract_node_records(run, {"lora_finetuning"})
        assert records == []


# ---------------------------------------------------------------------------
# Integration: gather_run_history
# ---------------------------------------------------------------------------

class TestGatherRunHistory:
    def test_gathers_from_db(self):
        """Full integration with mocked DB session."""
        base = time.time()
        plan = _make_plan({
            "n1": _resolved_node("n1", "lora_finetuning"),
        })

        mock_run = _make_run(
            run_id="run-1",
            pipeline_id="pipe-1",
            config_snapshot={
                "nodes": [
                    {"id": "x1", "data": {"type": "lora_finetuning"}},
                ],
            },
            metrics_log=[
                {"type": "node_started", "node_id": "x1", "timestamp": base},
                {"type": "node_completed", "node_id": "x1", "timestamp": base + 180},
            ],
        )

        mock_db = MagicMock()
        # Mock the chained query calls
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_run]

        history = gather_run_history(mock_db, plan, pipeline_id="pipe-1")

        assert len(history) >= 1
        assert any(r["block_type"] == "lora_finetuning" for r in history)

    def test_empty_plan_returns_empty(self):
        """Plan with no nodes returns empty history."""
        plan = _make_plan({})
        mock_db = MagicMock()

        history = gather_run_history(mock_db, plan)
        assert history == []

    def test_db_error_returns_empty(self):
        """DB errors don't propagate — return empty list."""
        plan = _make_plan({
            "n1": _resolved_node("n1", "lora_finetuning"),
        })

        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("DB down")

        history = gather_run_history(mock_db, plan)
        assert history == []
