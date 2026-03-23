from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, JSON, Integer, Float
from ..database import Base


class Project(Base):
    __tablename__ = "blueprint_projects"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    paper_number = Column(String, nullable=True)
    paper_title = Column(String, nullable=True)
    paper_subtitle = Column(String, nullable=True)
    target_venue = Column(String, nullable=True)
    description = Column(Text, default="")
    status = Column(String, default="planned")  # planned|queued|active|blocked|analyzing|writing|complete
    blocked_by = Column(String, nullable=True)
    priority = Column(Integer, default=5)  # 1=highest
    github_repo = Column(String, nullable=True)
    xlsx_plan_path = Column(String, nullable=True)
    notes = Column(Text, default="")
    hypothesis = Column(Text, nullable=True)
    key_result = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    total_experiments = Column(Integer, default=0)
    completed_experiments = Column(Integer, default=0)
    current_phase = Column(String, nullable=True)
    completion_criteria = Column(Text, nullable=True)
    estimated_compute_hours = Column(Float, default=0)
    estimated_cost_usd = Column(Float, default=0)
    actual_compute_hours = Column(Float, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
