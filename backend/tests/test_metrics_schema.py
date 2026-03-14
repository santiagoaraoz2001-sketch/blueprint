"""Tests for metrics schema versioning."""

import pytest

from backend.engine.metrics_schema import (
    CURRENT_SCHEMA_VERSION,
    MetricEvent,
    create_metric,
    parse_metrics_log,
    aggregate_metrics,
)
from backend.utils.metrics_migrator import migrate_metrics_log


# ---- Test 1: v0 migration ----

def test_v0_legacy_migration():
    """v0 (pre-versioning) events migrate to v1."""
    legacy = {
        "type": "metric",
        "node_id": "x",
        "name": "loss",
        "value": 0.5,
        "timestamp": 1.0,
    }
    event = MetricEvent.from_dict(legacy)
    assert event.schema_version == 1
    assert event.type == "metric"
    assert event.node_id == "x"
    assert event.name == "loss"
    assert event.value == 0.5
    assert event.timestamp == 1.0
    assert event.step is None
    assert event.unit is None
    assert event.aggregation is None
    assert event.tags is None


def test_v0_legacy_with_category():
    """Legacy event with category field preserved."""
    legacy = {
        "type": "metric",
        "node_id": "abc",
        "name": "accuracy",
        "value": 0.95,
        "category": "training",
        "timestamp": 100.0,
    }
    event = MetricEvent.from_dict(legacy)
    assert event.schema_version == 1
    assert event.category == "training"


# ---- Test 2: v1 round-trip ----

def test_v1_round_trip():
    """Create metric -> to_dict -> from_dict produces identical event."""
    original = create_metric(
        node_id="node_1",
        name="loss",
        value=0.42,
        category="training",
        step=10,
        unit="loss",
        aggregation="last",
        tags={"epoch": 3},
    )
    d = original.to_dict()
    restored = MetricEvent.from_dict(d)

    assert restored.schema_version == original.schema_version
    assert restored.type == original.type
    assert restored.node_id == original.node_id
    assert restored.name == original.name
    assert restored.value == original.value
    assert restored.category == original.category
    assert restored.step == original.step
    assert restored.unit == original.unit
    assert restored.aggregation == original.aggregation
    assert restored.tags == original.tags


def test_to_dict_omits_none():
    """to_dict strips None fields to save space."""
    event = create_metric(
        node_id="n", name="x", value=1.0, category="eval",
    )
    d = event.to_dict()
    assert "step" not in d
    assert "unit" not in d
    assert "aggregation" not in d
    assert "tags" not in d
    assert "schema_version" in d


# ---- Test 3: Aggregation ----

def _make_loss_events(values, aggregation="last"):
    events = []
    for i, v in enumerate(values):
        e = MetricEvent(
            schema_version=1,
            type="metric",
            node_id="train",
            name="loss",
            value=v,
            category="training",
            timestamp=float(i),
            step=i,
            aggregation=aggregation,
        )
        events.append(e)
    return events


def test_aggregation_last():
    events = _make_loss_events([0.8, 0.6, 0.4, 0.3, 0.2], aggregation="last")
    summary = aggregate_metrics(events)
    assert summary["train.loss"] == 0.2


def test_aggregation_min():
    events = _make_loss_events([0.8, 0.6, 0.4, 0.3, 0.2], aggregation="min")
    summary = aggregate_metrics(events)
    assert summary["train.loss"] == 0.2


def test_aggregation_max():
    events = _make_loss_events([0.8, 0.6, 0.4, 0.3, 0.2], aggregation="max")
    summary = aggregate_metrics(events)
    assert summary["train.loss"] == 0.8


def test_aggregation_mean():
    events = _make_loss_events([0.8, 0.6, 0.4, 0.3, 0.2], aggregation="mean")
    summary = aggregate_metrics(events)
    assert abs(summary["train.loss"] - 0.46) < 1e-9


def test_aggregation_default_is_last():
    """No aggregation field defaults to 'last'."""
    events = _make_loss_events([0.8, 0.6, 0.4, 0.3, 0.2])
    # Override aggregation to None for default
    for e in events:
        e.aggregation = None
    summary = aggregate_metrics(events)
    assert summary["train.loss"] == 0.2


def test_aggregation_late_override():
    """If early events have no aggregation but a later one sets it, the later wins."""
    events = []
    for i, v in enumerate([0.8, 0.6, 0.4]):
        events.append(MetricEvent(
            schema_version=1, type="metric", node_id="train", name="loss",
            value=v, category="training", timestamp=float(i), step=i,
            aggregation=None,  # No aggregation on early events
        ))
    # Last event sets aggregation to "min"
    events.append(MetricEvent(
        schema_version=1, type="metric", node_id="train", name="loss",
        value=0.2, category="training", timestamp=3.0, step=3,
        aggregation="min",
    ))
    summary = aggregate_metrics(events)
    assert summary["train.loss"] == 0.2  # min of [0.8, 0.6, 0.4, 0.2]


def test_aggregation_multiple_keys():
    """Multiple metric keys aggregate independently."""
    events = [
        MetricEvent(schema_version=1, type="metric", node_id="train", name="loss",
                    value=0.5, category="training", timestamp=1.0, aggregation="last"),
        MetricEvent(schema_version=1, type="metric", node_id="train", name="loss",
                    value=0.3, category="training", timestamp=2.0, aggregation="last"),
        MetricEvent(schema_version=1, type="metric", node_id="eval", name="accuracy",
                    value=0.8, category="evaluation", timestamp=1.0, aggregation="max"),
        MetricEvent(schema_version=1, type="metric", node_id="eval", name="accuracy",
                    value=0.9, category="evaluation", timestamp=2.0, aggregation="max"),
    ]
    summary = aggregate_metrics(events)
    assert summary["train.loss"] == 0.3
    assert summary["eval.accuracy"] == 0.9


def test_aggregation_non_numeric_values_skipped():
    """Non-numeric values are silently skipped in aggregation."""
    events = [
        MetricEvent(schema_version=1, type="metric", node_id="n", name="info",
                    value="not_a_number", category="meta", timestamp=1.0),
    ]
    summary = aggregate_metrics(events)
    assert summary == {}  # Skipped because float("not_a_number") fails


def test_aggregation_skips_non_metric_events():
    events = [
        MetricEvent(
            schema_version=1, type="system", node_id="n",
            name="checkpoint", value="path.pt", category="system",
            timestamp=1.0,
        ),
    ]
    summary = aggregate_metrics(events)
    assert summary == {}


# ---- Test 4: Forward compatibility ----

def test_forward_compat_v99():
    """Future schema version parses without error (best-effort)."""
    future = {
        "schema_version": 99,
        "type": "metric",
        "node_id": "future_node",
        "name": "new_metric",
        "value": 3.14,
        "category": "experimental",
        "timestamp": 9999.0,
        "unit": "widgets",
        "aggregation": "max",
        "tags": {"new_field": True},
        "unknown_field": "ignored",
    }
    event = MetricEvent.from_dict(future)
    assert event.schema_version == 99
    assert event.name == "new_metric"
    assert event.value == 3.14
    assert event.unit == "widgets"
    assert event.tags == {"new_field": True}


# ---- Test 5: parse_metrics_log ----

def test_parse_metrics_log_mixed():
    """Parses a log with v0 and v1 entries, using defaults for sparse dicts."""
    log = [
        {"type": "metric", "node_id": "a", "name": "loss", "value": 0.5, "timestamp": 1.0},
        {"schema_version": 1, "type": "metric", "node_id": "b", "name": "acc", "value": 0.9, "category": "eval", "timestamp": 2.0},
        {"broken": True},  # Sparse dict — parsed with defaults (from_dict fills missing fields)
    ]
    events = parse_metrics_log(log)
    assert len(events) == 3  # All parsed; from_dict uses defaults for missing fields
    assert events[0].schema_version == 1  # migrated from v0
    assert events[1].schema_version == 1
    # The sparse entry gets defaults
    assert events[2].schema_version == 1
    assert events[2].name == ""
    assert events[2].value == 0


def test_parse_metrics_log_skips_non_dict():
    """Non-dict entries (None, str, int) are skipped without crashing."""
    log = [None, "not a dict", 42, {"type": "metric", "node_id": "a", "name": "ok", "value": 1.0, "timestamp": 1.0}]
    events = parse_metrics_log(log)
    assert len(events) == 1
    assert events[0].name == "ok"


def test_parse_metrics_log_empty():
    """Empty log returns empty list."""
    assert parse_metrics_log([]) == []


# ---- Test 6: metrics_migrator ----

def test_migrate_metrics_log():
    """migrate_metrics_log upgrades all entries to current version."""
    old_log = [
        {"type": "metric", "node_id": "x", "name": "loss", "value": 0.5, "timestamp": 1.0},
        {"schema_version": 1, "type": "metric", "node_id": "y", "name": "acc", "value": 0.9, "category": "eval", "timestamp": 2.0},
    ]
    migrated = migrate_metrics_log(old_log)
    assert len(migrated) == 2
    for entry in migrated:
        assert entry["schema_version"] == CURRENT_SCHEMA_VERSION
    assert migrated[0]["name"] == "loss"
    assert migrated[1]["name"] == "acc"


def test_migrate_metrics_log_skips_bad_entries():
    """migrate_metrics_log skips non-dict entries without crashing."""
    log_with_junk = [
        None,
        {"type": "metric", "node_id": "x", "name": "loss", "value": 0.5, "timestamp": 1.0},
        42,
    ]
    migrated = migrate_metrics_log(log_with_junk)
    assert len(migrated) == 1
    assert migrated[0]["name"] == "loss"


# ---- Test 7: create_metric factory ----

def test_create_metric_sets_version_and_timestamp():
    event = create_metric(
        node_id="n1", name="lr", value=0.001, category="training",
    )
    assert event.schema_version == CURRENT_SCHEMA_VERSION
    assert event.type == "metric"
    assert event.timestamp > 0


# ---- Test 8: API endpoint logic (unit) ----

def test_get_typed_metrics_404():
    """get_typed_metrics raises 404 for missing run."""
    from unittest.mock import MagicMock
    from fastapi import HTTPException
    from backend.routers.runs import get_typed_metrics

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        get_typed_metrics("nonexistent-id", mock_db)
    assert exc_info.value.status_code == 404


def test_get_typed_metrics_returns_versioned_events():
    """get_typed_metrics returns versioned events + summary."""
    from unittest.mock import MagicMock
    from backend.routers.runs import get_typed_metrics

    mock_run = MagicMock()
    mock_run.metrics_log = [
        {"type": "metric", "node_id": "n1", "name": "loss", "value": 0.5, "category": "training", "timestamp": 1.0},
        {"schema_version": 1, "type": "metric", "node_id": "n1", "name": "loss", "value": 0.3, "category": "training", "timestamp": 2.0},
    ]

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_run

    result = get_typed_metrics("test-run-id", mock_db)

    assert result["schema_version"] == CURRENT_SCHEMA_VERSION
    assert result["event_count"] == 2
    assert len(result["events"]) == 2
    assert all(e["schema_version"] == 1 for e in result["events"])
    assert "n1.loss" in result["summary"]
    assert result["summary"]["n1.loss"] == 0.3  # last value (default aggregation)


def test_get_typed_metrics_jsonl_fallback(tmp_path):
    """get_typed_metrics falls back to JSONL when metrics_log is null."""
    import json
    from unittest.mock import MagicMock, patch
    from backend.routers.runs import get_typed_metrics

    # Create a fake JSONL file
    run_dir = tmp_path / "test-run-id"
    run_dir.mkdir()
    jsonl_file = run_dir / "metrics.jsonl"
    events = [
        {"type": "metric", "node_id": "n1", "name": "acc", "value": 0.85, "category": "eval", "timestamp": 1.0},
        {"type": "metric", "node_id": "n1", "name": "acc", "value": 0.92, "category": "eval", "timestamp": 2.0},
    ]
    jsonl_file.write_text("\n".join(json.dumps(e) for e in events) + "\n")

    mock_run = MagicMock()
    mock_run.metrics_log = None  # Simulate crash recovery — no SQLite data

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_run

    with patch("backend.routers.runs.ARTIFACTS_DIR", tmp_path):
        result = get_typed_metrics("test-run-id", mock_db)

    assert result["event_count"] == 2
    assert result["summary"]["n1.acc"] == 0.92


def test_get_typed_metrics_empty_when_no_data():
    """get_typed_metrics returns empty results when run has no metrics at all."""
    from unittest.mock import MagicMock, patch
    from pathlib import Path
    from backend.routers.runs import get_typed_metrics

    mock_run = MagicMock()
    mock_run.metrics_log = None

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_run

    # Point ARTIFACTS_DIR to a temp dir with no JSONL file
    with patch("backend.routers.runs.ARTIFACTS_DIR", Path("/nonexistent")):
        result = get_typed_metrics("test-run-id", mock_db)

    assert result["event_count"] == 0
    assert result["events"] == []
    assert result["summary"] == {}
