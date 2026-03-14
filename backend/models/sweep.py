from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey
from ..database import Base


class Sweep(Base):
    __tablename__ = "blueprint_sweeps"

    id = Column(String, primary_key=True)
    pipeline_id = Column(String, ForeignKey("blueprint_pipelines.id"), nullable=False)
    target_node_id = Column(String, nullable=False)
    metric_name = Column(String, nullable=False)
    search_type = Column(String, nullable=False)  # grid, random
    configs = Column(JSON, nullable=False)  # List of config dicts
    run_ids = Column(JSON, default=list)  # List of associated run IDs
    results = Column(JSON, default=list)  # [{config, metric, run_id}, ...]
    status = Column(String, default="pending")  # pending, running, complete, failed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
