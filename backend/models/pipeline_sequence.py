from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Integer, JSON, ForeignKey
from ..database import Base


class PipelineSequence(Base):
    """Sequential pipeline execution queue — runs pipelines one after another."""
    __tablename__ = "blueprint_pipeline_sequences"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("blueprint_projects.id"), nullable=False, index=True)
    pipeline_ids = Column(JSON, nullable=False)  # ordered list of pipeline IDs
    status = Column(String, default="pending")  # pending | running | completed | failed
    current_index = Column(Integer, default=0)
    current_run_id = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
