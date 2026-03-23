from pydantic import BaseModel
from datetime import datetime
from typing import Any


class DatasetCreate(BaseModel):
    name: str
    source: str = "local"
    source_path: str = ""
    description: str = ""
    tags: list[str] = []


class DatasetResponse(BaseModel):
    id: str
    name: str
    source: str
    source_path: str
    description: str
    row_count: int | None
    size_bytes: int | None
    column_count: int | None
    columns: list[Any]
    tags: list[str]
    created_at: datetime
    version: int

    model_config = {"from_attributes": True}
