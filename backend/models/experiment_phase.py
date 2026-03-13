from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey
from ..database import Base


class ExperimentPhase(Base):
    __tablename__ = "experiment_phases"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("blueprint_projects.id"), nullable=False)
    phase_id = Column(String, nullable=False)  # "E0", "E1", "E2.3"
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, default="planned")  # planned|queued|active|complete|skipped
    blocked_by_phase = Column(String, nullable=True)
    total_runs = Column(Integer, default=0)
    completed_runs = Column(Integer, default=0)
    research_question = Column(Text, nullable=True)
    finding = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
