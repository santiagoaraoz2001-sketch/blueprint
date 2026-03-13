"""
Metrics Schema -- versioned metric event format with forward/backward compatibility.
"""

import time
from typing import Any, Optional
from dataclasses import dataclass, asdict

CURRENT_SCHEMA_VERSION = 1


@dataclass
class MetricEvent:
    """A single metric measurement."""
    schema_version: int
    type: str              # "metric" | "node_completed" | "system" | "checkpoint"
    node_id: str
    name: str
    value: Any             # float, int, str, dict, list
    category: str          # block category (training, evaluation, etc.)
    timestamp: float       # unix timestamp
    step: Optional[int] = None
    unit: Optional[str] = None       # "percent", "seconds", "loss", "accuracy", etc.
    aggregation: Optional[str] = None  # "last", "min", "max", "mean" -- how to summarize
    tags: Optional[dict] = None       # arbitrary metadata

    def to_dict(self) -> dict:
        d = asdict(self)
        # Remove None fields to save space
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "MetricEvent":
        """Parse a metric event, handling version migration."""
        version = data.get("schema_version", 0)

        if version == 0:
            # Legacy format (pre-versioning) -- migrate to v1
            return cls(
                schema_version=1,
                type=data.get("type", "metric"),
                node_id=data.get("node_id", ""),
                name=data.get("name", ""),
                value=data.get("value", 0),
                category=data.get("category", ""),
                timestamp=data.get("timestamp", 0),
                step=data.get("step"),
            )
        elif version == 1:
            return cls(
                schema_version=version,
                type=data.get("type", "metric"),
                node_id=data.get("node_id", ""),
                name=data.get("name", ""),
                value=data.get("value", 0),
                category=data.get("category", ""),
                timestamp=data.get("timestamp", 0),
                step=data.get("step"),
                unit=data.get("unit"),
                aggregation=data.get("aggregation"),
                tags=data.get("tags"),
            )
        else:
            # Future version -- best effort parse (forward compat)
            return cls(
                schema_version=version,
                type=data.get("type", "metric"),
                node_id=data.get("node_id", ""),
                name=data.get("name", ""),
                value=data.get("value", 0),
                category=data.get("category", ""),
                timestamp=data.get("timestamp", 0),
                step=data.get("step"),
                unit=data.get("unit"),
                aggregation=data.get("aggregation"),
                tags=data.get("tags"),
            )


def create_metric(
    node_id: str,
    name: str,
    value: Any,
    category: str,
    step: Optional[int] = None,
    unit: Optional[str] = None,
    aggregation: Optional[str] = None,
    tags: Optional[dict] = None,
) -> MetricEvent:
    """Factory function for creating a properly versioned metric event."""
    return MetricEvent(
        schema_version=CURRENT_SCHEMA_VERSION,
        type="metric",
        node_id=node_id,
        name=name,
        value=value,
        category=category,
        timestamp=time.time(),
        step=step,
        unit=unit,
        aggregation=aggregation,
        tags=tags,
    )


def parse_metrics_log(log: list[dict]) -> list[MetricEvent]:
    """Parse a metrics_log (from Run model) into typed MetricEvent objects."""
    events = []
    for entry in log:
        try:
            events.append(MetricEvent.from_dict(entry))
        except Exception:
            continue  # Skip unparseable entries
    return events


def aggregate_metrics(events: list[MetricEvent]) -> dict[str, Any]:
    """
    Aggregate metric events into a summary dict.

    Uses the 'aggregation' field to determine how to summarize:
    - "last": use the final value (default)
    - "min": use the minimum value
    - "max": use the maximum value
    - "mean": use the average value
    """
    grouped: dict[str, list[float]] = {}
    aggregations: dict[str, str] = {}

    for event in events:
        if event.type != "metric":
            continue
        key = f"{event.node_id}.{event.name}" if event.node_id else event.name
        if key not in grouped:
            grouped[key] = []
        # Use the last explicitly-set aggregation for each key.
        # This ensures that if early events lack an aggregation but
        # later ones set it, the explicit value wins.
        if event.aggregation:
            aggregations[key] = event.aggregation
        elif key not in aggregations:
            aggregations[key] = "last"
        try:
            grouped[key].append(float(event.value))
        except (ValueError, TypeError):
            pass

    result = {}
    for key, values in grouped.items():
        if not values:
            continue
        agg = aggregations.get(key, "last")
        if agg == "min":
            result[key] = min(values)
        elif agg == "max":
            result[key] = max(values)
        elif agg == "mean":
            result[key] = sum(values) / len(values)
        else:  # "last" or unknown
            result[key] = values[-1]

    return result
