from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Integer, JSON, ForeignKey, Index
from ..database import Base


class Artifact(Base):
    __tablename__ = "blueprint_artifacts"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("blueprint_runs.id"), nullable=False, index=True)
    pipeline_id = Column(String, ForeignKey("blueprint_pipelines.id"), nullable=False, index=True)
    node_id = Column(String, nullable=False)
    block_type = Column(String, nullable=False)

    name = Column(String, nullable=False)
    artifact_type = Column(String, nullable=False, index=True)  # dataset|model|adapter|log|figure|checkpoint|metrics
    file_path = Column(String, nullable=False)
    size_bytes = Column(Integer, default=0)
    hash = Column(String, nullable=True)  # SHA-256

    metadata = Column(JSON, default=dict)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_artifact_pipeline_type", "pipeline_id", "artifact_type"),
    )
