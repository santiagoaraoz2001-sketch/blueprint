from pydantic import BaseModel
from datetime import datetime


class ExperimentPhaseCreate(BaseModel):
    phase_id: str
    name: str
    description: str | None = None
    status: str = "planned"
    blocked_by_phase: str | None = None
    total_runs: int = 0
    research_question: str | None = None
    sort_order: int = 0


class ExperimentPhaseUpdate(BaseModel):
    phase_id: str | None = None
    name: str | None = None
    description: str | None = None
    status: str | None = None
    blocked_by_phase: str | None = None
    total_runs: int | None = None
    completed_runs: int | None = None
    research_question: str | None = None
    finding: str | None = None
    sort_order: int | None = None


class ExperimentPhaseResponse(BaseModel):
    id: str
    project_id: str
    phase_id: str
    name: str
    description: str | None
    status: str
    blocked_by_phase: str | None
    total_runs: int
    completed_runs: int
    research_question: str | None
    finding: str | None
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class QuickSetupPhase(BaseModel):
    phase_id: str
    name: str
    total_runs: int = 0
    description: str | None = None
    research_question: str | None = None


class QuickSetupRequest(BaseModel):
    phases: list[QuickSetupPhase]
