from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, Float, Integer, JSON, ForeignKey
from ..database import Base


class Run(Base):
    __tablename__ = "blueprint_runs"

    id = Column(String, primary_key=True)
    pipeline_id = Column(String, ForeignKey("blueprint_pipelines.id"), nullable=False)
    mlflow_run_id = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending | running | paused | complete | failed
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    last_heartbeat = Column(DateTime, nullable=True)
    config_snapshot = Column(JSON, default=dict)
    metrics = Column(JSON, default=dict)


class LiveRun(Base):
    """Shared with Control Tower for live monitoring."""
    __tablename__ = "blueprint_live_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("blueprint_runs.id"), nullable=False)
    pipeline_name = Column(String, default="")
    project_name = Column(String, default="")
    current_block = Column(String, default="")
    current_block_index = Column(Integer, default=0)
    total_blocks = Column(Integer, default=0)
    block_progress = Column(Float, default=0.0)
    overall_progress = Column(Float, default=0.0)
    eta_seconds = Column(Float, nullable=True)
    model_path = Column(String, nullable=True)
    status = Column(String, default="running")
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
