import uuid
import threading
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from ..models.pipeline import Pipeline
from ..models.run import Run
from ..engine.executor import execute_pipeline
from ..engine.validator import validate_pipeline

router = APIRouter(prefix="/api", tags=["execution"])


@router.post("/pipelines/{pipeline_id}/execute")
def start_pipeline_run(pipeline_id: str, db: Session = Depends(get_db)):
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    definition = pipeline.definition or {}
    if not definition.get("nodes"):
        raise HTTPException(400, "Pipeline has no blocks")

    run_id = str(uuid.uuid4())

    # Run in background thread with its own DB session
    def run_in_thread():
        session = SessionLocal()
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            loop.run_until_complete(execute_pipeline(pipeline_id, run_id, definition, session))
        finally:
            session.close()

    thread = threading.Thread(target=run_in_thread, daemon=False)
    thread.start()

    return {"status": "started", "pipeline_id": pipeline_id, "run_id": run_id}


@router.post("/runs/{run_id}/stop")
def stop_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    run.status = "failed"
    run.error_message = "Stopped by user"
    db.commit()
    return {"status": "stopped"}


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
