from pydantic import BaseModel
from datetime import datetime


class ProjectCreate(BaseModel):
    name: str
    paper_number: str | None = None
    description: str = ""
    status: str = "planning"
    github_repo: str | None = None
    notes: str = ""
    tags: list[str] = []


class ProjectUpdate(BaseModel):
    name: str | None = None
    paper_number: str | None = None
    description: str | None = None
    status: str | None = None
    github_repo: str | None = None
    notes: str | None = None
    tags: list[str] | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    paper_number: str | None
    description: str
    status: str
    github_repo: str | None
    notes: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
