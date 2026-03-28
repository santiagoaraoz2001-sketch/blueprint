"""Model registry — tracks all models produced by Blueprint pipelines."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.model_record import ModelRecord
from ..models.run import Run
from ..schemas.model_record import ModelRecordCreate, ModelRecordResponse

router = APIRouter(prefix="/api/models/registry", tags=["model-registry"])


# ── List models ──────────────────────────────────────────────────────
@router.get("", response_model=list[ModelRecordResponse])
def list_models(
    format: str | None = None,
    tags: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(ModelRecord)
    if format:
        q = q.filter(ModelRecord.format == format)
    if tags:
        q = q.filter(ModelRecord.tags.contains(tags))
    if search:
        q = q.filter(ModelRecord.name.contains(search))
    return q.order_by(ModelRecord.created_at.desc()).all()


# ── Get model card ───────────────────────────────────────────────────
@router.get("/{model_id}", response_model=ModelRecordResponse)
def get_model(model_id: str, db: Session = Depends(get_db)):
    model = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if not model:
        raise HTTPException(404, "Model not found")
    return model


# ── Get model card with full provenance ─────────────────────────────
@router.get("/{model_id}/card")
def get_model_card(model_id: str, db: Session = Depends(get_db)):
    model = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if not model:
        raise HTTPException(404, "Model not found")

    # Build provenance info from source run
    provenance = {
        "run_id": model.source_run_id,
        "node_id": model.source_node_id,
        "pipeline_id": None,
        "pipeline_name": None,
    }
    if model.source_run_id:
        run = db.query(Run).filter(Run.id == model.source_run_id).first()
        if run:
            provenance["pipeline_id"] = run.pipeline_id

    return {
        "model": ModelRecordResponse.model_validate(model).model_dump(),
        "provenance": provenance,
        "training_config": model.training_config or {},
        "metrics": model.metrics or {},
    }


# ── Create model (manual registration) ──────────────────────────────
@router.post("", response_model=ModelRecordResponse, status_code=201)
def create_model(data: ModelRecordCreate, db: Session = Depends(get_db)):
    record = ModelRecord(id=str(uuid.uuid4()), **data.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# ── Delete model ─────────────────────────────────────────────────────
@router.delete("/{model_id}", status_code=204)
def delete_model(model_id: str, db: Session = Depends(get_db)):
    model = db.query(ModelRecord).filter(ModelRecord.id == model_id).first()
    if not model:
        raise HTTPException(404, "Model not found")
    db.delete(model)
    db.commit()
