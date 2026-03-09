from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey
from ..database import Base


class Artifact(Base):
    __tablename__ = "blueprint_artifacts"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("blueprint_runs.id"), nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, default="file")  # model | dataset | metrics | log | figure
    path = Column(String, nullable=False)
    size_bytes = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
