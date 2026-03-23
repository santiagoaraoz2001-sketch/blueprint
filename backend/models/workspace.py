from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime
from ..database import Base


class WorkspaceSettings(Base):
    __tablename__ = "blueprint_workspace"

    id = Column(String, primary_key=True, default="default")
    root_path = Column(String, nullable=True)
    auto_fill_paths = Column(Boolean, default=True)
    watcher_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
