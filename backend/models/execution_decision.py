"""ExecutionDecision — records why each node was executed, cached, or skipped during a run."""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index
from ..database import Base


class ExecutionDecision(Base):
    __tablename__ = "execution_decisions"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("blueprint_runs.id"), nullable=False, index=True)
    node_id = Column(String, nullable=False)
    decision = Column(String, nullable=False)  # 'execute' | 'cache_hit' | 'cache_invalidated' | 'skipped'
    reason = Column(Text, nullable=True)
    cache_fingerprint = Column(String, nullable=True)
    plan_hash = Column(String, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_execution_decisions_run_node", "run_id", "node_id"),
        Index("ix_execution_decisions_timestamp", "timestamp"),
    )
