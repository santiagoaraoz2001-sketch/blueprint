from pydantic import BaseModel
from datetime import datetime
from typing import Any


class PipelineCreate(BaseModel):
    name: str
    project_id: str | None = None
    experiment_id: str | None = None
    experiment_phase_id: str | None = None
    description: str = ""
    definition: dict[str, Any] = {}


class PipelineUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    experiment_phase_id: str | None = None
    definition: dict[str, Any] | None = None


class PipelineResponse(BaseModel):
    id: str
    name: str
    project_id: str | None
    experiment_id: str | None
    experiment_phase_id: str | None
    description: str
    definition: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
