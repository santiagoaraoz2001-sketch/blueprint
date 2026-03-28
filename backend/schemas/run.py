from pydantic import BaseModel
from datetime import datetime
from typing import Any


class RunResponse(BaseModel):
    id: str
    pipeline_id: str
    project_id: str | None = None
    mlflow_run_id: str | None
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_seconds: float | None
    error_message: str | None
    config_snapshot: dict[str, Any]
    metrics: dict[str, Any]
    outputs_snapshot: dict[str, Any] | None = None
    data_fingerprints: dict[str, Any] | None = None
    starred: str | None = "false"

    model_config = {"from_attributes": True}
