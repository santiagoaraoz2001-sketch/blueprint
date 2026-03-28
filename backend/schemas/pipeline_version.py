from pydantic import BaseModel
from datetime import datetime
from typing import Any


class PipelineVersionResponse(BaseModel):
    id: str
    pipeline_id: str
    version_number: int
    snapshot: str  # JSON string — parsed by frontend
    author: str
    message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PipelineVersionSummary(BaseModel):
    """Lighter response without the full snapshot for list views."""
    id: str
    pipeline_id: str
    version_number: int
    author: str
    message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RestoreVersionRequest(BaseModel):
    message: str | None = None
