import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.pipeline import Pipeline
from ..schemas.pipeline import PipelineCreate, PipelineUpdate, PipelineResponse

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


@router.get("/{pipeline_id}/plan")
def get_pipeline_plan(pipeline_id: str, db: Session = Depends(get_db)):
    """Run the planner on the current pipeline and return a JSON-serialized plan summary.

    Read-only — does not trigger execution. For each node returns:
    resolved_config, config_sources, cache_fingerprint, cache_eligible, in_loop.

    Config merge precedence: global workspace → project → pipeline definition.
    """
    from ..engine.planner import GraphPlanner
    from ..engine.config_merge import merge_workspace_config
    from ..services.registry import get_global_registry

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    definition = pipeline.definition or {}
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    # Merge config from all scopes: global → project → definition
    workspace_config = merge_workspace_config(
        definition_config=definition.get("workspace_config") or None,
        project_id=pipeline.project_id,
        db=db,
    )

    if not nodes:
        return {
            "is_valid": True,
            "errors": [],
            "plan_hash": "empty",
            "nodes": {},
            "execution_order": [],
            "warnings": [],
        }

    registry = get_global_registry()
    if registry is None:
        from ..services.registry import BlockRegistryService
        registry = BlockRegistryService()

    planner = GraphPlanner(registry)
    result = planner.plan(nodes, edges, workspace_config=workspace_config or None)

    if not result.is_valid or result.plan is None:
        return {
            "is_valid": False,
            "errors": list(result.errors),
            "plan_hash": None,
            "nodes": {},
            "execution_order": [],
            "warnings": [],
        }

    plan = result.plan
    node_map = {n["id"]: n for n in nodes}

    nodes_summary = {}
    for node_id, rn in plan.nodes.items():
        node_label = node_map.get(node_id, {}).get("data", {}).get("label", node_id)
        nodes_summary[node_id] = {
            "node_id": rn.node_id,
            "label": node_label,
            "block_type": rn.block_type,
            "block_version": rn.block_version,
            "resolved_config": rn.resolved_config,
            "config_sources": rn.config_sources,
            "cache_fingerprint": rn.cache_fingerprint,
            "cache_eligible": rn.cache_eligible,
            "in_loop": rn.in_loop,
            "loop_id": rn.loop_id,
        }

    return {
        "is_valid": True,
        "errors": [],
        "plan_hash": plan.plan_hash,
        "nodes": nodes_summary,
        "execution_order": list(plan.execution_order),
        "warnings": list(plan.warnings),
    }


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
    from ..engine.config_merge import merge_workspace_config

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    definition = pipeline.definition or {}
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])
    workspace_config = merge_workspace_config(
        definition_config=definition.get("workspace_config") or None,
        project_id=pipeline.project_id,
        db=db,
    ) or None

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
