from pydantic import BaseModel
from datetime import datetime
from typing import Any


class ModelRecordResponse(BaseModel):
    id: str
    name: str
    version: str
    format: str
    size_bytes: int | None
    source_run_id: str | None
    source_node_id: str | None
    metrics: dict[str, Any]
    tags: str
    training_config: dict[str, Any]
    source_data: str | None
    model_path: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ModelRecordCreate(BaseModel):
    name: str
    version: str = "1.0.0"
    format: str
    size_bytes: int | None = None
    source_run_id: str | None = None
    source_node_id: str | None = None
    metrics: dict[str, Any] = {}
    tags: str = ""
    training_config: dict[str, Any] = {}
    source_data: str | None = None
    model_path: str | None = None
