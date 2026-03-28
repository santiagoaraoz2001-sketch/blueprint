"""ExecutionDecision — per-node execution decision records for replay inspection.

Tracks what decision was made for each node during a run (execute, cache_hit,
skipped) along with the reason and timing information.  Populated by the
executor and partial executor during pipeline execution.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Float, Integer, Text, JSON, ForeignKey, Index
from ..database import Base


class ExecutionDecision(Base):
    """Per-node execution decision recorded during a run."""
    __tablename__ = "blueprint_execution_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("blueprint_runs.id"), nullable=False, index=True)
    node_id = Column(String, nullable=False)
    block_type = Column(String, nullable=False)
    execution_order = Column(Integer, nullable=False)

    # 'execute' | 'cache_hit' | 'skipped'
    decision = Column(String, nullable=False)
    decision_reason = Column(Text, nullable=True)

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

    # Loop info
    iteration = Column(Integer, nullable=True)  # null for non-loop nodes
    loop_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_exec_decision_run_node", "run_id", "node_id"),
    )
