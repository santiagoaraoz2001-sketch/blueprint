"""
Global Outputs API — cross-pipeline runs, artifacts, and telemetry.

Powers the Global Outputs Monitor dashboard with project-scoped queries.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.run import Run, LiveRun
from ..models.artifact import Artifact
from ..models.pipeline import Pipeline

router = APIRouter(prefix="/api/outputs", tags=["outputs"])


# ── Response Schemas ──────────────────────────────────────────────


class ArtifactItem(BaseModel):
    id: str
    run_id: str
    pipeline_id: str
    node_id: str
    block_type: str
    name: str
    artifact_type: str
    file_path: str
    size_bytes: int
    hash: str | None = None
    metadata: dict[str, Any] | None = Field(None, alias="metadata_")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class RunWithArtifacts(BaseModel):
    id: str
    pipeline_id: str
    pipeline_name: str | None = None
    project_id: str | None = None
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    metrics: dict[str, Any] | None = None
    artifacts: list[ArtifactItem] = []

    model_config = {"from_attributes": True}


class LiveRunItem(BaseModel):
    run_id: str
    pipeline_name: str
    project_name: str
    current_block: str
    current_block_index: int
    total_blocks: int
    block_progress: float
    overall_progress: float
    eta_seconds: float | None = None
    status: str
    started_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OutputsDashboard(BaseModel):
    """Aggregate response for the Global Outputs Monitor."""
    runs: list[RunWithArtifacts]
    live_runs: list[LiveRunItem]
    total_runs: int
    total_artifacts: int
    artifact_type_counts: dict[str, int]


# ── Endpoints ─────────────────────────────────────────────────────


@router.get("/dashboard", response_model=OutputsDashboard)
def get_outputs_dashboard(
    project_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Aggregate dashboard data: recent runs with nested artifacts + live runs.

    Supports project-scoped filtering via ?project_id=.
    """
    # Build runs query
    runs_q = db.query(Run)
    if project_id:
        runs_q = runs_q.filter(Run.project_id == project_id)
    if status:
        runs_q = runs_q.filter(Run.status == status)

    total_runs = runs_q.count()
    runs = runs_q.order_by(Run.started_at.desc()).offset(offset).limit(limit).all()

    # Batch-load pipeline names for all runs
    pipeline_ids = list({r.pipeline_id for r in runs})
    pipeline_name_map: dict[str, str] = {}
    if pipeline_ids:
        pipelines = db.query(Pipeline.id, Pipeline.name).filter(
            Pipeline.id.in_(pipeline_ids)
        ).all()
        pipeline_name_map = {p.id: p.name for p in pipelines}

    # Batch-load artifacts for all runs
    run_ids = [r.id for r in runs]
    artifacts_by_run: dict[str, list[Artifact]] = {rid: [] for rid in run_ids}
    if run_ids:
        artifacts = db.query(Artifact).filter(
            Artifact.run_id.in_(run_ids)
        ).order_by(Artifact.created_at.desc()).all()
        for a in artifacts:
            artifacts_by_run.setdefault(a.run_id, []).append(a)

    # Build response
    run_items = []
    for r in runs:
        run_items.append(RunWithArtifacts(
            id=r.id,
            pipeline_id=r.pipeline_id,
            pipeline_name=pipeline_name_map.get(r.pipeline_id),
            project_id=r.project_id,
            status=r.status,
            started_at=r.started_at,
            finished_at=r.finished_at,
            duration_seconds=r.duration_seconds,
            error_message=r.error_message,
            metrics=r.metrics,
            artifacts=[
                ArtifactItem.model_validate(a)
                for a in artifacts_by_run.get(r.id, [])
            ],
        ))

    # Artifact type counts (project-scoped if filtered)
    type_counts_q = db.query(Artifact.artifact_type, db.query(Artifact).with_entities(
        Artifact.artifact_type
    ).correlate(None).scalar_subquery())

    # Simpler approach: just count from the loaded artifacts
    all_artifacts = []
    for arts in artifacts_by_run.values():
        all_artifacts.extend(arts)
    type_counts: dict[str, int] = {}
    for a in all_artifacts:
        type_counts[a.artifact_type] = type_counts.get(a.artifact_type, 0) + 1

    # Total artifact count (project-scoped)
    total_artifacts_q = db.query(Artifact)
    if project_id:
        total_artifacts_q = total_artifacts_q.filter(Artifact.pipeline_id.in_(
            db.query(Pipeline.id).filter(Pipeline.project_id == project_id)
        ))
    total_artifacts = total_artifacts_q.count()

    # Live runs
    live_q = db.query(LiveRun).filter(LiveRun.status == "running")
    live_runs = live_q.all()

    return OutputsDashboard(
        runs=run_items,
        live_runs=[LiveRunItem.model_validate(lr) for lr in live_runs],
        total_runs=total_runs,
        total_artifacts=total_artifacts,
        artifact_type_counts=type_counts,
    )


@router.get("/runs", response_model=list[RunWithArtifacts])
def list_output_runs(
    project_id: str | None = None,
    pipeline_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List runs with nested artifacts. Supports project and pipeline filtering."""
    q = db.query(Run)
    if project_id:
        q = q.filter(Run.project_id == project_id)
    if pipeline_id:
        q = q.filter(Run.pipeline_id == pipeline_id)
    if status:
        q = q.filter(Run.status == status)

    runs = q.order_by(Run.started_at.desc()).offset(offset).limit(limit).all()

    # Batch-load
    pipeline_ids = list({r.pipeline_id for r in runs})
    pipeline_name_map: dict[str, str] = {}
    if pipeline_ids:
        pipelines = db.query(Pipeline.id, Pipeline.name).filter(
            Pipeline.id.in_(pipeline_ids)
        ).all()
        pipeline_name_map = {p.id: p.name for p in pipelines}

    run_ids = [r.id for r in runs]
    artifacts_by_run: dict[str, list[Artifact]] = {rid: [] for rid in run_ids}
    if run_ids:
        artifacts = db.query(Artifact).filter(
            Artifact.run_id.in_(run_ids)
        ).order_by(Artifact.created_at.desc()).all()
        for a in artifacts:
            artifacts_by_run.setdefault(a.run_id, []).append(a)

    return [
        RunWithArtifacts(
            id=r.id,
            pipeline_id=r.pipeline_id,
            pipeline_name=pipeline_name_map.get(r.pipeline_id),
            project_id=r.project_id,
            status=r.status,
            started_at=r.started_at,
            finished_at=r.finished_at,
            duration_seconds=r.duration_seconds,
            error_message=r.error_message,
            metrics=r.metrics,
            artifacts=[ArtifactItem.model_validate(a) for a in artifacts_by_run.get(r.id, [])],
        )
        for r in runs
    ]


@router.get("/artifacts", response_model=list[ArtifactItem])
def list_artifacts(
    project_id: str | None = None,
    pipeline_id: str | None = None,
    run_id: str | None = None,
    artifact_type: str | None = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List artifacts with filtering. Used for cross-pipeline artifact picker."""
    q = db.query(Artifact)
    if project_id:
        q = q.filter(Artifact.pipeline_id.in_(
            db.query(Pipeline.id).filter(Pipeline.project_id == project_id)
        ))
    if pipeline_id:
        q = q.filter(Artifact.pipeline_id == pipeline_id)
    if run_id:
        q = q.filter(Artifact.run_id == run_id)
    if artifact_type:
        q = q.filter(Artifact.artifact_type == artifact_type)

    return q.order_by(Artifact.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/artifacts/{artifact_id}", response_model=ArtifactItem)
def get_artifact(artifact_id: str, db: Session = Depends(get_db)):
    """Get a single artifact by ID."""
    artifact = db.query(Artifact).filter(Artifact.id == artifact_id).first()
    if not artifact:
        raise HTTPException(404, "Artifact not found")
    return artifact


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str, db: Session = Depends(get_db)):
    """Stream the raw artifact file for download."""
    import os

    artifact = db.query(Artifact).filter(Artifact.id == artifact_id).first()
    if not artifact:
        raise HTTPException(404, "Artifact not found")
    if not os.path.isfile(artifact.file_path):
        raise HTTPException(404, "Artifact file no longer exists on disk")
    return FileResponse(
        path=artifact.file_path,
        filename=artifact.name,
        media_type="application/octet-stream",
    )


@router.get("/artifacts/{artifact_id}/preview")
def preview_artifact(
    artifact_id: str,
    rows: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Return a structured preview of an artifact's content.

    Supports CSV, JSONL, JSON, Parquet, SQLite, text, Excel, and YAML via
    the shared dataset preview parsers.
    """
    import os
    from pathlib import Path
    from .datasets import _read_file_preview

    artifact = db.query(Artifact).filter(Artifact.id == artifact_id).first()
    if not artifact:
        raise HTTPException(404, "Artifact not found")
    if not os.path.isfile(artifact.file_path):
        raise HTTPException(404, "Artifact file no longer exists on disk")

    ext = Path(artifact.file_path).suffix.lower()
    try:
        preview_rows, columns, total_rows = _read_file_preview(
            artifact.file_path, ext, rows, offset,
        )
    except Exception as e:
        return {
            "artifact_id": artifact_id,
            "rows": [],
            "columns": [],
            "total_rows": 0,
            "format": ext.lstrip("."),
            "error": str(e),
        }

    return {
        "artifact_id": artifact_id,
        "rows": preview_rows,
        "columns": columns,
        "total_rows": total_rows,
        "format": ext.lstrip("."),
    }


@router.get("/live", response_model=list[LiveRunItem])
def list_live_runs(db: Session = Depends(get_db)):
    """List currently running pipelines."""
    return db.query(LiveRun).filter(LiveRun.status == "running").all()
