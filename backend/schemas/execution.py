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


class AutofixPatchResponse(BaseModel):
    """A single proposed autofix patch."""
    patch_id: str
    node_id: str
    field: str
    action: str
    old_value: Any = None
    new_value: Any = None
    reason: str
    confidence: str
    edge_id: str | None = None
    source_id: str | None = None
    target_id: str | None = None


class AutofixRequest(BaseModel):
    """Request body for the autofix endpoint."""
    action: str  # 'propose' | 'apply'
    patch_ids: list[str] | None = None


class AutofixResponse(BaseModel):
    """Response from the autofix endpoint."""
    patches: list[AutofixPatchResponse]
    applied: list[str] = []
    skipped: list[dict[str, str]] = []
    definition: dict[str, Any] | None = None
