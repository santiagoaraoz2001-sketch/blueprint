"""
Run History Service — gathers per-node execution statistics from past runs.

Provides the dry-run simulator with historical timing and memory data
so it can produce high-confidence estimates when prior runs exist.

Data sources (in priority order):
  1. metrics_log — per-node node_started/node_completed timestamps give
     exact per-node durations.  system_metric events give memory snapshots.
     Block-logged metrics (peak_memory_gb, etc.) give per-block memory.
  2. config_snapshot — stores the full pipeline definition at run time,
     including each node's block_type and config.
  3. Run.duration_seconds — total pipeline duration, divided across nodes
     as a last resort.

This module NEVER modifies the database.  All queries are read-only.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class NodeRunStats:
    """Aggregated per-node statistics from historical runs."""

    __slots__ = (
        "block_type",
        "duration_seconds",
        "peak_memory_mb",
        "sample_count",
        "config_hash",
    )

    def __init__(
        self,
        block_type: str,
        duration_seconds: float,
        peak_memory_mb: int | None = None,
        sample_count: int = 1,
        config_hash: str = "",
    ):
        self.block_type = block_type
        self.duration_seconds = duration_seconds
        self.peak_memory_mb = peak_memory_mb
        self.sample_count = sample_count
        self.config_hash = config_hash


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def gather_run_history(
    db: Session,
    plan: Any,
    pipeline_id: str | None = None,
    max_runs: int = 50,
) -> list[dict[str, Any]]:
    """Gather per-node execution history for blocks in this plan.

    Strategy:
      1. Query completed runs (same pipeline first, then any pipeline)
      2. For each run, parse config_snapshot to map node_id → block_type
      3. Parse metrics_log to extract per-node durations and memory
      4. Return a flat list of per-node records the dry-run simulator expects

    Args:
        db: SQLAlchemy session (read-only).
        plan: ExecutionPlan with .nodes dict.
        pipeline_id: If set, prefer history from this specific pipeline.
        max_runs: Maximum number of past runs to scan.

    Returns:
        List of dicts with keys: block_type, duration_seconds, peak_memory_mb.
    """
    from ..models.run import Run

    target_block_types = {
        n.block_type for n in plan.nodes.values() if n.block_type
    }
    if not target_block_types:
        return []

    history: list[dict[str, Any]] = []

    try:
        runs = _query_relevant_runs(db, Run, pipeline_id, max_runs)
        for run in runs:
            node_records = _extract_node_records(run, target_block_types)
            history.extend(node_records)
    except Exception as e:
        # History is best-effort — never break dry-run on DB issues
        logger.debug("Failed to gather run history: %s", e)

    return history


# ---------------------------------------------------------------------------
# Query layer
# ---------------------------------------------------------------------------

def _query_relevant_runs(
    db: Session,
    run_model: type,
    pipeline_id: str | None,
    max_runs: int,
) -> list:
    """Query completed runs, preferring same-pipeline runs."""
    runs = []

    # Priority 1: runs from the same pipeline (most relevant)
    if pipeline_id:
        try:
            same_pipeline = (
                db.query(run_model)
                .filter(
                    run_model.pipeline_id == pipeline_id,
                    run_model.status == "complete",
                )
                .order_by(run_model.finished_at.desc())
                .limit(max_runs)
                .all()
            )
            runs.extend(same_pipeline)
        except Exception:
            pass

    # Priority 2: fill remaining from any completed run
    seen_ids = {r.id for r in runs}
    remaining = max_runs - len(runs)
    if remaining > 0:
        try:
            other_runs = (
                db.query(run_model)
                .filter(run_model.status == "complete")
                .order_by(run_model.finished_at.desc())
                .limit(remaining + len(seen_ids))  # over-fetch to skip dupes
                .all()
            )
            for r in other_runs:
                if r.id not in seen_ids and len(runs) < max_runs:
                    runs.append(r)
                    seen_ids.add(r.id)
        except Exception:
            pass

    return runs


# ---------------------------------------------------------------------------
# Per-run extraction
# ---------------------------------------------------------------------------

def _extract_node_records(
    run: Any,
    target_block_types: set[str],
) -> list[dict[str, Any]]:
    """Extract per-node timing and memory data from a single run.

    Uses three complementary data sources:
      1. metrics_log node_started/node_completed events → exact per-node durations
      2. metrics_log metric events → per-block logged memory (peak_memory_gb)
      3. config_snapshot → node → block_type mapping (the pipeline definition)
      4. Run.duration_seconds ÷ node_count → fallback duration estimate
    """
    records: list[dict[str, Any]] = []

    # ── Step 1: Build node_id → block_type map from config_snapshot ──
    node_block_types = _parse_block_types_from_snapshot(run.config_snapshot)
    if not node_block_types:
        return records

    # Filter to only target block types
    relevant_nodes = {
        nid: bt for nid, bt in node_block_types.items()
        if bt in target_block_types
    }
    if not relevant_nodes:
        return records

    # ── Step 2: Parse metrics_log for per-node timing ──
    node_durations = _parse_node_durations(run.metrics_log)
    node_memory = _parse_node_memory(run.metrics_log)

    # ── Step 3: Build records for each relevant node ──
    for node_id, block_type in relevant_nodes.items():
        duration_s = node_durations.get(node_id)
        memory_mb = node_memory.get(node_id)

        # Fallback: if we have no per-node timing but have total duration
        if duration_s is None and run.duration_seconds:
            total_nodes = len(node_block_types)
            duration_s = run.duration_seconds / max(total_nodes, 1)

        if duration_s is not None:
            records.append({
                "block_type": block_type,
                "duration_seconds": duration_s,
                "peak_memory_mb": memory_mb,
            })

    return records


# ---------------------------------------------------------------------------
# config_snapshot parsing
# ---------------------------------------------------------------------------

def _parse_block_types_from_snapshot(
    config_snapshot: dict | None,
) -> dict[str, str]:
    """Extract {node_id: block_type} from a run's config_snapshot.

    config_snapshot stores the full pipeline definition:
        {"nodes": [...], "edges": [...]}
    where each node is:
        {"id": "...", "type": "default", "data": {"type": "lora_finetuning", ...}}
    """
    if not config_snapshot or not isinstance(config_snapshot, dict):
        return {}

    result: dict[str, str] = {}
    nodes = config_snapshot.get("nodes", [])

    if isinstance(nodes, list):
        # Standard format: nodes is a list of node dicts
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = node.get("id", "")
            node_data = node.get("data", {})
            if isinstance(node_data, dict):
                block_type = node_data.get("type", "")
                if node_id and block_type:
                    result[node_id] = block_type

    elif isinstance(nodes, dict):
        # Alternate format: nodes is a dict keyed by node_id
        for node_id, node_data in nodes.items():
            if isinstance(node_data, dict):
                block_type = node_data.get("block_type", node_data.get("type", ""))
                if block_type:
                    result[node_id] = block_type

    return result


# ---------------------------------------------------------------------------
# metrics_log parsing
# ---------------------------------------------------------------------------

def _parse_node_durations(
    metrics_log: list | None,
) -> dict[str, float]:
    """Extract per-node durations from metrics_log events.

    Matches node_started and node_completed events by node_id,
    computing duration = completed.timestamp - started.timestamp.
    """
    if not metrics_log or not isinstance(metrics_log, list):
        return {}

    # Track the most recent start time for each node
    start_times: dict[str, float] = {}
    durations: dict[str, float] = {}

    for event in metrics_log:
        if not isinstance(event, dict):
            continue

        event_type = event.get("type", "")
        node_id = event.get("node_id", "")
        timestamp = event.get("timestamp")

        if not node_id or timestamp is None:
            continue

        try:
            ts = float(timestamp)
        except (ValueError, TypeError):
            continue

        if event_type == "node_started":
            start_times[node_id] = ts

        elif event_type == "node_completed":
            start_ts = start_times.get(node_id)
            if start_ts is not None and ts > start_ts:
                durations[node_id] = ts - start_ts

    return durations


def _parse_node_memory(
    metrics_log: list | None,
) -> dict[str, int | None]:
    """Extract per-node peak memory from metrics_log events.

    Looks for:
      1. Block-logged metrics named 'peak_memory_gb' or 'peak_memory_mb'
      2. system_metric events between node_started/node_completed
    """
    if not metrics_log or not isinstance(metrics_log, list):
        return {}

    node_memory: dict[str, int | None] = {}
    current_node: str | None = None
    max_system_mem_per_node: dict[str, float] = {}

    for event in metrics_log:
        if not isinstance(event, dict):
            continue

        event_type = event.get("type", "")

        # Track which node is currently executing
        if event_type == "node_started":
            current_node = event.get("node_id")
        elif event_type == "node_completed":
            current_node = None

        # Block-logged memory metrics (most accurate)
        elif event_type == "metric":
            node_id = event.get("node_id", "")
            name = str(event.get("name", "")).lower()
            value = event.get("value")

            if not node_id or value is None:
                continue

            try:
                val = float(value)
            except (ValueError, TypeError):
                continue

            if "peak_memory_gb" in name:
                node_memory[node_id] = int(val * 1024)
            elif "peak_memory_mb" in name:
                node_memory[node_id] = int(val)
            elif "mem_gb" in name and "peak" in name:
                node_memory[node_id] = int(val * 1024)

        # System-level memory snapshots (fallback)
        elif event_type == "system_metric" and current_node:
            mem_gb = event.get("mem_gb")
            if mem_gb is not None:
                try:
                    gb = float(mem_gb)
                    if current_node not in max_system_mem_per_node or gb > max_system_mem_per_node[current_node]:
                        max_system_mem_per_node[current_node] = gb
                except (ValueError, TypeError):
                    pass

    # Fill in from system metrics where block-level data is missing
    for node_id, mem_gb in max_system_mem_per_node.items():
        if node_id not in node_memory:
            node_memory[node_id] = int(mem_gb * 1024)

    return node_memory
