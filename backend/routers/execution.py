import uuid
import logging
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from ..models.pipeline import Pipeline
from ..models.run import Run
from ..engine.executor import execute_pipeline, request_cancel
from ..engine.partial_executor import execute_partial_pipeline
from ..engine.validator import validate_pipeline
from ..engine.block_registry import get_block_config_schema, is_known_block
from ..block_sdk.config_validator import (
    validate_and_apply_defaults,
    _validate_type,
    _validate_bounds,
    _validate_select,
)
from ..block_sdk.exceptions import BlockConfigError

router = APIRouter(prefix="/api", tags=["execution"])
_logger = logging.getLogger("blueprint.execution")

# Bounded thread pool prevents resource exhaustion from concurrent runs
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pipeline-run")


class PartialExecuteRequest(BaseModel):
    """Request body for partial pipeline re-execution."""
    source_run_id: str = Field(..., description="ID of the completed run to reuse cached outputs from")
    start_node_id: str = Field(..., description="Node ID to re-execute from (inclusive)")
    config_overrides: dict[str, dict] = Field(
        default_factory=dict,
        description="Per-node config overrides: {node_id: {key: value}}",
    )


def shutdown_executor():
    """Gracefully shut down the pipeline executor pool. Called during app shutdown."""
    _logger.info("Shutting down pipeline executor pool...")
    _executor.shutdown(wait=True, cancel_futures=False)
    _logger.info("Pipeline executor pool shut down.")


@router.post("/pipelines/{pipeline_id}/execute")
def start_pipeline_run(pipeline_id: str, db: Session = Depends(get_db)):
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    definition = pipeline.definition or {}
    if not definition.get("nodes"):
        raise HTTPException(400, "Pipeline has no blocks")

    run_id = str(uuid.uuid4())
    project_id = pipeline.project_id  # May be None if pipeline has no project

    # Run in background thread with its own DB session
    def run_in_thread():
        session = SessionLocal()
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            loop.run_until_complete(execute_pipeline(pipeline_id, run_id, definition, session, project_id=project_id))
        finally:
            session.close()

    try:
        _executor.submit(run_in_thread)
    except RuntimeError:
        raise HTTPException(503, "Pipeline executor is shutting down. Please try again later.")

    return {"status": "started", "pipeline_id": pipeline_id, "run_id": run_id}


@router.post("/pipelines/{pipeline_id}/execute-from")
def execute_from_node(
    pipeline_id: str,
    body: PartialExecuteRequest,
    db: Session = Depends(get_db),
):
    """Execute a pipeline starting from a specific node, reusing cached outputs."""
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    definition = pipeline.definition or {}
    nodes = definition.get("nodes", [])
    if not nodes:
        raise HTTPException(400, "Pipeline has no blocks")

    # --- Validate source run (fail-fast before thread submission) ---
    source_run = db.query(Run).filter(Run.id == body.source_run_id).first()
    if not source_run:
        raise HTTPException(404, "Source run not found")
    if source_run.status != "complete":
        raise HTTPException(
            400,
            f"Source run has status '{source_run.status}', expected 'complete'",
        )
    if not source_run.outputs_snapshot:
        raise HTTPException(400, "Source run has no cached outputs")

    # --- Validate start_node_id exists in the pipeline ---
    node_ids = {n["id"] for n in nodes}
    if body.start_node_id not in node_ids:
        raise HTTPException(
            400,
            f"start_node_id '{body.start_node_id}' not found in pipeline",
        )

    # --- Validate config_overrides reference real nodes ---
    if body.config_overrides:
        unknown = set(body.config_overrides.keys()) - node_ids
        if unknown:
            raise HTTPException(
                400,
                f"config_overrides reference unknown node IDs: {sorted(unknown)}",
            )

    run_id = str(uuid.uuid4())
    project_id = pipeline.project_id

    def run_in_thread():
        session = SessionLocal()
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                execute_partial_pipeline(
                    pipeline_id, run_id, body.source_run_id, body.start_node_id,
                    definition, body.config_overrides, session, project_id=project_id,
                )
            )
        finally:
            session.close()

    try:
        _executor.submit(run_in_thread)
    except RuntimeError:
        raise HTTPException(503, "Pipeline executor is shutting down. Please try again later.")

    return {
        "status": "started",
        "pipeline_id": pipeline_id,
        "run_id": run_id,
        "partial": True,
        "source_run_id": body.source_run_id,
        "start_node_id": body.start_node_id,
    }


@router.post("/runs/{run_id}/stop")
def stop_run(run_id: str, db: Session = Depends(get_db)):
    """Legacy stop endpoint — delegates to cancel."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    request_cancel(run_id)
    return {"status": "cancelling"}


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, db: Session = Depends(get_db)):
    """Signal a running pipeline to cancel. Returns immediately."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status not in ("running", "pending"):
        raise HTTPException(400, f"Run is already {run.status}")
    request_cancel(run_id)
    return {"status": "cancelling", "run_id": run_id}


@router.get("/runs/{run_id}/outputs")
def get_run_outputs(run_id: str, db: Session = Depends(get_db)):
    """Get partial or complete outputs for a run."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    return {
        "run_id": run_id,
        "status": run.status,
        "outputs": run.outputs_snapshot or {},
    }


@router.post("/pipelines/{pipeline_id}/validate")
def validate_pipeline_endpoint(pipeline_id: str, db: Session = Depends(get_db)):
    """Validate a pipeline definition without running it."""
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    definition = pipeline.definition or {}

    report = validate_pipeline(definition)
    return {
        "valid": report.valid,
        "errors": report.errors,
        "warnings": report.warnings,
        "estimated_runtime_s": report.estimated_runtime_s,
        "block_count": report.block_count,
        "edge_count": report.edge_count,
    }


@router.post("/blocks/{block_type}/validate-config")
def validate_block_config(block_type: str, config: dict):
    """Validate a block's config against its block.yaml schema.

    Returns per-field validation results including type errors,
    bounds violations, and invalid select options.
    """
    if not is_known_block(block_type):
        raise HTTPException(404, f"Unknown block type: {block_type}")

    schema = get_block_config_schema(block_type)
    if not schema:
        return {"valid": True, "errors": [], "validated_config": config}

    # Validate each field independently to collect all errors
    errors = []
    result = dict(config)

    for field_name, field_spec in schema.items():
        if not isinstance(field_spec, dict):
            continue
        field_type = field_spec.get("type", "string")

        # Apply default if missing
        if field_name not in result or result[field_name] is None or result[field_name] == "":
            if "default" in field_spec:
                result[field_name] = field_spec["default"]

        value = result.get(field_name)
        if value is None or value == "":
            continue

        try:
            _validate_type(field_name, value, field_type)
        except BlockConfigError as exc:
            errors.append({"field": exc.field, "message": str(exc), "recoverable": exc.recoverable})
            continue

        if field_type in ("integer", "float"):
            try:
                _validate_bounds(field_name, value, field_spec)
            except BlockConfigError as exc:
                errors.append({"field": exc.field, "message": str(exc), "recoverable": exc.recoverable})

        if field_type == "select":
            try:
                _validate_select(field_name, value, field_spec)
            except BlockConfigError as exc:
                errors.append({"field": exc.field, "message": str(exc), "recoverable": exc.recoverable})

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "validated_config": result,
    }


@router.post("/pipelines/{pipeline_id}/test")
def test_pipeline_endpoint(pipeline_id: str, db: Session = Depends(get_db)):
    """Run pipeline in test mode with reduced data."""
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    definition = pipeline.definition or {}

    report = validate_pipeline(definition)

    return {
        "mode": "test",
        "validation": {
            "valid": report.valid,
            "errors": report.errors,
            "warnings": report.warnings,
        },
        "estimated_runtime_s": max(report.estimated_runtime_s // 10, 1),
        "sample_size": 10,
        "block_count": report.block_count,
    }
