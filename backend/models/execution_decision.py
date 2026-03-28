"""ExecutionDecision — records why each node was executed, cached, or skipped during a run.

Tracks per-node decisions with timing, resolved config, errors, and loop info.
Populated by the executor, partial executor, and planner during pipeline execution.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Float, Integer, Text, JSON, ForeignKey, Index
from ..database import Base


class ExecutionDecision(Base):
    """Per-node execution decision recorded during a run."""
    __tablename__ = "execution_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("blueprint_runs.id"), nullable=False, index=True)
    node_id = Column(String, nullable=False)
    block_type = Column(String, nullable=False, default="")
    execution_order = Column(Integer, nullable=False, default=0)

    # 'execute' | 'cache_hit' | 'cache_invalidated' | 'skipped'
    decision = Column(String, nullable=False)
    decision_reason = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)  # Alias kept for backward compat with main

    # 'completed' | 'failed' | 'skipped' | 'cached' | 'not_executed'
    status = Column(String, nullable=False, default="pending")

    started_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)
    memory_peak_mb = Column(Float, nullable=True)

    # Resolved config with source annotations
    resolved_config = Column(JSON, nullable=True)
    config_sources = Column(JSON, nullable=True)

    # Error info (populated on failure)
    error_json = Column(JSON, nullable=True)  # {title, message, action, severity, original_type}

    # Cache/plan fingerprints (from planner)
    cache_fingerprint = Column(String, nullable=True)
    plan_hash = Column(String, nullable=True)

    # Loop info
    iteration = Column(Integer, nullable=True)  # null for non-loop nodes
    loop_id = Column(String, nullable=True)

    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_execution_decisions_run_node", "run_id", "node_id"),
        Index("ix_execution_decisions_timestamp", "timestamp"),
    )
