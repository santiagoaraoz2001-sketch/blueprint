from pydantic import BaseModel
from datetime import datetime
from typing import Any


class PaperCreate(BaseModel):
    name: str
    project_id: str
    content: dict[str, Any] = {}


class PaperUpdate(BaseModel):
    name: str | None = None
    content: dict[str, Any] | None = None


class PaperResponse(BaseModel):
    id: str
    name: str
    project_id: str
    content: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
