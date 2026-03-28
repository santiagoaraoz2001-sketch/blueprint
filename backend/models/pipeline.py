from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, JSON, Boolean, ForeignKey
from ..database import Base


class Pipeline(Base):
    __tablename__ = "blueprint_pipelines"

    id = Column(String, primary_key=True)
    experiment_id = Column(String, ForeignKey("blueprint_experiments.id"), nullable=True)
    project_id = Column(String, ForeignKey("blueprint_projects.id"), nullable=True)
    experiment_phase_id = Column(String, ForeignKey("experiment_phases.id"), nullable=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    definition = Column(JSON, default=dict)  # Full DAG: nodes, edges, block configs
    notes = Column(Text, nullable=True)  # Pipeline-level notes (markdown)
    source_pipeline_id = Column(String, ForeignKey("blueprint_pipelines.id"), nullable=True)
    variant_notes = Column(Text, nullable=True)  # Why this variant exists
    config_diff = Column(JSON, nullable=True)  # Config keys that differ from source
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
