from pydantic import BaseModel, field_validator
from datetime import datetime


class ProjectCreate(BaseModel):
    name: str
    paper_number: str | None = None
    paper_title: str | None = None
    paper_subtitle: str | None = None
    target_venue: str | None = None
    description: str = ""
    status: str = "planned"
    blocked_by: str | None = None
    priority: int = 5
    github_repo: str | None = None
    notes: str = ""
    hypothesis: str | None = None
    key_result: str | None = None
    tags: list[str] = []
    total_experiments: int = 0
    completed_experiments: int = 0
    current_phase: str | None = None
    completion_criteria: str | None = None
    estimated_compute_hours: float = 0
    estimated_cost_usd: float = 0


class ProjectUpdate(BaseModel):
    name: str | None = None
    paper_number: str | None = None
    paper_title: str | None = None
    paper_subtitle: str | None = None
    target_venue: str | None = None
    description: str | None = None
    status: str | None = None
    blocked_by: str | None = None
    priority: int | None = None
    github_repo: str | None = None
    notes: str | None = None
    hypothesis: str | None = None
    key_result: str | None = None
    tags: list[str] | None = None
    total_experiments: int | None = None
    completed_experiments: int | None = None
    current_phase: str | None = None
    completion_criteria: str | None = None
    estimated_compute_hours: float | None = None
    estimated_cost_usd: float | None = None
    actual_compute_hours: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    paper_number: str | None = None
    paper_title: str | None = None
    paper_subtitle: str | None = None
    target_venue: str | None = None
    description: str = ""
    status: str = "planned"
    blocked_by: str | None = None
    priority: int = 5
    github_repo: str | None = None
    notes: str = ""
    hypothesis: str | None = None
    key_result: str | None = None
    tags: list[str] = []
    total_experiments: int = 0
    completed_experiments: int = 0
    current_phase: str | None = None
    completion_criteria: str | None = None
    estimated_compute_hours: float = 0
    estimated_cost_usd: float = 0
    actual_compute_hours: float = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator('priority', 'total_experiments', 'completed_experiments', mode='before')
    @classmethod
    def default_int_none(cls, v: int | None) -> int:
        return v if v is not None else 0

    @field_validator('estimated_compute_hours', 'estimated_cost_usd', 'actual_compute_hours', mode='before')
    @classmethod
    def default_float_none(cls, v: float | None) -> float:
        return v if v is not None else 0.0

    @field_validator('notes', 'description', mode='before')
    @classmethod
    def default_str_none(cls, v: str | None) -> str:
        return v if v is not None else ""

    @field_validator('tags', mode='before')
    @classmethod
    def default_tags_none(cls, v: list | None) -> list:
        return v if v is not None else []

    model_config = {"from_attributes": True}
