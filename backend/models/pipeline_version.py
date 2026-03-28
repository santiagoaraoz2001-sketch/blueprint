from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, UniqueConstraint
from ..database import Base


class PipelineVersion(Base):
    __tablename__ = "blueprint_pipeline_versions"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "version_number", name="uq_pipeline_version"),
    )

    id = Column(String, primary_key=True)
    pipeline_id = Column(String, ForeignKey("blueprint_pipelines.id"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    snapshot = Column(Text, nullable=False)  # Full JSON pipeline definition
    author = Column(String, default="local")
    message = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
