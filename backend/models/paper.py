from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, JSON, ForeignKey
from ..database import Base


class Paper(Base):
    __tablename__ = "blueprint_papers"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("blueprint_projects.id"), nullable=False)
    name = Column(String, nullable=False)
    content = Column(JSON, default=dict)  # Stores sections, citations, charts
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
