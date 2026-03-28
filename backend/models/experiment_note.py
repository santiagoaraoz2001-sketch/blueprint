from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index
from ..database import Base


class ExperimentNote(Base):
    """Auto-generated and user-editable experiment journal entries."""
    __tablename__ = "blueprint_experiment_notes"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("blueprint_runs.id"), nullable=False, index=True)
    auto_summary = Column(Text, nullable=False)
    user_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_experiment_note_created", "created_at"),
    )
