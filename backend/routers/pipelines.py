import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.pipeline import Pipeline
from ..schemas.pipeline import PipelineCreate, PipelineUpdate, PipelineResponse
from .pipeline_versions import create_version_for_pipeline

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


@router.get("", response_model=list[PipelineResponse])
def list_pipelines(project_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Pipeline)
    if project_id:
        q = q.filter(Pipeline.project_id == project_id)
    return q.order_by(Pipeline.updated_at.desc()).all()


@router.post("", response_model=PipelineResponse, status_code=201)
def create_pipeline(data: PipelineCreate, db: Session = Depends(get_db)):
    pipeline = Pipeline(id=str(uuid.uuid4()), **data.model_dump())
    db.add(pipeline)
    db.commit()
    db.refresh(pipeline)
    return pipeline


@router.get("/{pipeline_id}", response_model=PipelineResponse)
def get_pipeline(pipeline_id: str, db: Session = Depends(get_db)):
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")
    return pipeline


@router.put("/{pipeline_id}", response_model=PipelineResponse)
def update_pipeline(pipeline_id: str, data: PipelineUpdate, db: Session = Depends(get_db)):
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(pipeline, key, value)

    # Auto-save a version snapshot on every explicit Save
    definition = pipeline.definition or {}
    create_version_for_pipeline(db, pipeline_id, definition, message="Auto-save")

    db.commit()
    db.refresh(pipeline)
    return pipeline


@router.delete("/{pipeline_id}", status_code=204)
def delete_pipeline(pipeline_id: str, db: Session = Depends(get_db)):
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")
    db.delete(pipeline)
    db.commit()


@router.post("/{pipeline_id}/duplicate", response_model=PipelineResponse)
def duplicate_pipeline(pipeline_id: str, db: Session = Depends(get_db)):
    original = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not original:
        raise HTTPException(404, "Pipeline not found")
    clone = Pipeline(
        id=str(uuid.uuid4()),
        name=f"{original.name} (copy)",
        project_id=original.project_id,
        experiment_id=original.experiment_id,
        description=original.description,
        definition=original.definition,
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return clone


@router.post("/{pipeline_id}/clone", response_model=PipelineResponse)
def clone_pipeline(pipeline_id: str, db: Session = Depends(get_db)):
    """Clone a pipeline (alias for duplicate)."""
    original = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not original:
        raise HTTPException(404, "Pipeline not found")
    clone = Pipeline(
        id=str(uuid.uuid4()),
        name=f"{original.name} (clone)",
        project_id=original.project_id,
        experiment_id=original.experiment_id,
        description=original.description,
        definition=original.definition,
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return clone


@router.post("/{pipeline_id}/resolve-config")
def resolve_pipeline_config(pipeline_id: str, db: Session = Depends(get_db)):
    """Resolve config inheritance for preview in the UI (dry run)."""
    from ..engine.executor import _topological_sort
    from ..engine.config_resolver import (
        resolve_configs,
        GLOBAL_PROPAGATION_KEYS,
        CATEGORY_PROPAGATION_KEYS,
    )
    from ..engine.block_registry import BlockRegistryService

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    definition = pipeline.definition or {}
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])
    workspace_config = definition.get("workspace_config") or None

    if not nodes:
        return {"resolved": {}, "propagation_keys": {}}

    try:
        order = _topological_sort(nodes, edges)
        _registry = BlockRegistryService()
        resolved_tuples = resolve_configs(
            nodes, edges, order,
            workspace_config=workspace_config,
            registry=_registry,
        )
        # Extract configs and sources for the UI response
        resolved = {
            nid: cfg for nid, (cfg, _src) in resolved_tuples.items()
        }
        config_sources = {
            nid: src for nid, (_cfg, src) in resolved_tuples.items()
        }
    except Exception as exc:
        raise HTTPException(
            500,
            f"Config resolution failed: {exc}",
        ) from exc

    return {
        "resolved": resolved,
        "config_sources": config_sources,
        "propagation_keys": {
            "global": sorted(GLOBAL_PROPAGATION_KEYS),
            "by_category": {
                cat: sorted(keys)
                for cat, keys in CATEGORY_PROPAGATION_KEYS.items()
            },
        },
    }


@router.get("/{pipeline_id}/compile")
def compile_pipeline(pipeline_id: str, db: Session = Depends(get_db)):
    from ..engine.compiler import compile_pipeline_to_python
    from ..engine.graph_utils import validate_exportable

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    definition = pipeline.definition or {}
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    # Kill switch: block export for unsupported pipelines
    export_errors = validate_exportable(nodes, edges)
    if export_errors:
        raise HTTPException(
            400,
            detail={
                "error": "export_unsupported",
                "reasons": export_errors,
                "remediation": "Remove unsupported blocks or use the full executor instead.",
            },
        )

    script = compile_pipeline_to_python(pipeline.name, definition)
    return PlainTextResponse(content=script, media_type="text/x-python")
