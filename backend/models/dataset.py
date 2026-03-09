from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, Integer, JSON
from ..database import Base


class Dataset(Base):
    __tablename__ = "blueprint_datasets"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    source = Column(String, default="local")  # huggingface | local | generated
    source_path = Column(String, default="")
    description = Column(Text, default="")
    row_count = Column(Integer, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    column_count = Column(Integer, nullable=True)
    columns = Column(JSON, default=list)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    version = Column(Integer, default=1)
