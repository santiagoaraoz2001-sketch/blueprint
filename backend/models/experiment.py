from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from ..database import Base


class Experiment(Base):
    __tablename__ = "blueprint_experiments"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("blueprint_projects.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    status = Column(String, default="planning")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
