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
    notes: str | None = None
    source_pipeline_id: str | None = None
    variant_notes: str | None = None
    config_diff: dict[str, Any] | None = None


class PipelineUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    experiment_phase_id: str | None = None
    definition: dict[str, Any] | None = None
    notes: str | None = None
    variant_notes: str | None = None


class CloneAsVariantRequest(BaseModel):
    name: str | None = None
    project_id: str | None = None
    variant_notes: str | None = None


class PipelineHistoryUpdate(BaseModel):
    history_json: str  # JSON-encoded undo/redo history


class PipelineResponse(BaseModel):
    id: str
    name: str
    project_id: str | None
    experiment_id: str | None
    experiment_phase_id: str | None
    description: str
    definition: dict[str, Any]
    notes: str | None = None
    source_pipeline_id: str | None = None
    variant_notes: str | None = None
    config_diff: dict[str, Any] | None = None
    history_json: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
