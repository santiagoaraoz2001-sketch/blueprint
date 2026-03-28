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


class ValidationErrorDetail(BaseModel):
    """A structured validation error with remediation guidance."""
    message: str
    node_id: str | None = None
    severity: str = "error"  # 'error' | 'warning'
    action: str | None = None  # suggested remediation


class PipelineValidationResponse(BaseModel):
    """Returned from the pipeline validation endpoint."""
    valid: bool
    errors: list[str]
    warnings: list[str]
    estimated_runtime_s: float
    block_count: int
    edge_count: int


class GatewayValidationResponse(BaseModel):
    """Returned from the execution gateway when validation fails (HTTP 400)."""
    error: str = "validation_failed"
    errors: list[str]
    error_count: int
    remediation: list[str]
    warnings: list[str] = []


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


# ---------------------------------------------------------------------------
# Dry-run simulation
# ---------------------------------------------------------------------------

class NodeEstimateResponse(BaseModel):
    """Per-node resource estimate."""
    estimated_memory_mb: int
    estimated_duration_class: str  # 'seconds' | 'minutes' | 'hours'
    confidence: str  # 'high' | 'medium' | 'low'


class TotalEstimateResponse(BaseModel):
    """Aggregate resource estimate for the whole pipeline."""
    peak_memory_mb: int
    total_artifact_volume_mb: int
    runtime_class: str  # 'seconds' | 'minutes' | 'hours'
    confidence: str  # 'high' | 'medium' | 'low'


class DryRunResponse(BaseModel):
    """Returned from the dry-run simulation endpoint."""
    viable: bool
    blockers: list[str]
    warnings: list[str]
    per_node_estimates: dict[str, NodeEstimateResponse]
    total_estimate: TotalEstimateResponse
