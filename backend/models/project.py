from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, JSON
from ..database import Base


class Project(Base):
    __tablename__ = "blueprint_projects"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    paper_number = Column(String, nullable=True)
    description = Column(Text, default="")
    status = Column(String, default="planning")  # planning | active | complete | paused
    github_repo = Column(String, nullable=True)
    xlsx_plan_path = Column(String, nullable=True)
    notes = Column(Text, default="")
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
