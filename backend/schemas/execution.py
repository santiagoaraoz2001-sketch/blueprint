"""Response models for execution endpoints."""

from pydantic import BaseModel
from typing import Any


class ExecuteResponse(BaseModel):
    """Returned when a pipeline execution is started."""
    status: str
    pipeline_id: str
    run_id: str


class PartialExecuteResponse(BaseModel):
    """Returned when a partial pipeline re-execution is started."""
    status: str
    pipeline_id: str
    run_id: str
    partial: bool = True
    source_run_id: str
    start_node_id: str


class CancelResponse(BaseModel):
    """Returned when a run cancellation is requested."""
    status: str
    run_id: str | None = None


class RunOutputsResponse(BaseModel):
    """Returned from the run outputs endpoint."""
    run_id: str
    status: str
    outputs: dict[str, Any]


class ValidationError(BaseModel):
    """A single validation error."""
    field: str | None = None
    message: str
    recoverable: bool = False


class PipelineValidationResponse(BaseModel):
    """Returned from the pipeline validation endpoint."""
    valid: bool
    errors: list[str]
    warnings: list[str]
    estimated_runtime_s: float
    block_count: int
    edge_count: int


class BlockConfigValidationResponse(BaseModel):
    """Returned from the block config validation endpoint."""
    valid: bool
    errors: list[dict[str, Any]]
    validated_config: dict[str, Any]


class PipelineTestResponse(BaseModel):
    """Returned from the pipeline test endpoint."""
    mode: str
    validation: dict[str, Any]
    estimated_runtime_s: float
    sample_size: int
    block_count: int
