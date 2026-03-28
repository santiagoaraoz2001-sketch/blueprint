import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Literal

from ..database import get_db
from ..models.pipeline import Pipeline
from ..schemas.pipeline import PipelineCreate, PipelineUpdate, PipelineResponse

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


class ExportRequest(BaseModel):
    format: Literal["python", "jupyter"] = "python"
    bundle: bool = False


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


@router.post("/{pipeline_id}/export")
def export_pipeline(pipeline_id: str, body: ExportRequest, db: Session = Depends(get_db)):
    """Export a pipeline as a standalone Python script or Jupyter notebook.

    Uses the planner to produce an ExecutionPlan, then compiles from it so
    the exported code uses identical execution order and resolved configs.

    Body: { "format": "python" | "jupyter" }
    """
    from ..engine.compiler import compile_pipeline_from_plan
    from ..engine.graph_utils import validate_exportable
    from ..engine.planner import GraphPlanner
    from ..services.registry import BlockRegistryService

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

    # Plan the pipeline to get resolved configs and execution order
    registry = BlockRegistryService()
    planner = GraphPlanner(registry)
    workspace_config = definition.get("workspace_config") or None
    result = planner.plan(nodes, edges, workspace_config=workspace_config)

    if not result.is_valid or result.plan is None:
        raise HTTPException(
            400,
            detail={
                "error": "plan_failed",
                "reasons": list(result.errors),
            },
        )

    plan = result.plan

    if body.format == "jupyter":
        from ..engine.jupyter_export import compile_pipeline_to_jupyter, notebook_to_json

        nb = compile_pipeline_to_jupyter(
            pipeline_name=pipeline.name,
            plan=plan,
            edges=edges,
            nodes=nodes,
            description=pipeline.description or "",
        )
        content = notebook_to_json(nb)
        ext = "ipynb"
        media_type = "application/x-ipynb+json"
    else:
        content = compile_pipeline_from_plan(
            pipeline_name=pipeline.name,
            plan=plan,
            edges=edges,
            nodes=nodes,
            description=pipeline.description or "",
        )
        ext = "py"
        media_type = "text/x-python"

    if body.bundle:
        # Create a zip with the script + required block directories
        import io
        import zipfile
        from ..engine.executor import _find_block_module
        from ..engine.block_registry import get_block_yaml

        buf = io.BytesIO()
        base_name = f"pipeline_{pipeline_id[:8]}"
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # Write the main script/notebook
            zf.writestr(f"{base_name}/{base_name}.{ext}", content)

            # Copy each block's directory into blocks/<category>/<type>/
            bundled: set[str] = set()
            for node_id in plan.execution_order:
                resolved_node = plan.nodes.get(node_id)
                if not resolved_node:
                    continue
                bt = resolved_node.block_type
                if bt in bundled:
                    continue
                block_dir = _find_block_module(bt)
                if not block_dir:
                    continue
                schema = get_block_yaml(bt)
                category = (schema or {}).get("category", "unknown")
                block_dir_path = Path(str(block_dir))
                if not block_dir_path.is_dir():
                    continue

                bundled.add(bt)
                rel_base = f"{base_name}/blocks/{category}/{bt}"
                for file_path in block_dir_path.rglob("*"):
                    if file_path.is_file():
                        # Skip __pycache__ and .pyc files
                        if "__pycache__" in str(file_path) or file_path.suffix == ".pyc":
                            continue
                        arc_name = f"{rel_base}/{file_path.relative_to(block_dir_path)}"
                        zf.write(str(file_path), arc_name)

            # Write a requirements.txt
            from ..engine.export_dependencies import collect_pip_dependencies_for_plan
            pip_deps = collect_pip_dependencies_for_plan(plan)
            if pip_deps:
                req_content = "# Generated by Blueprint — pip install -r requirements.txt\n"
                req_content += "\n".join(pip_deps) + "\n"
                zf.writestr(f"{base_name}/requirements.txt", req_content)

        buf.seek(0)
        filename = f"{base_name}.zip"
        return Response(
            content=buf.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    filename = f"pipeline_{pipeline_id[:8]}.{ext}"
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/{pipeline_id}/export/preflight")
def export_preflight(pipeline_id: str, db: Session = Depends(get_db)):
    """Pre-flight check for export: returns supported features, warnings, and blockers.

    The frontend uses this to show a pre-flight check panel before generating
    the export, not after.
    """
    from ..engine.graph_utils import validate_exportable, contains_loop_or_cycle

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    definition = pipeline.definition or {}
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    supported = [
        {"label": "DAG execution", "status": "ok"},
        {"label": "Config resolution", "status": "ok"},
    ]

    warnings = [
        {"label": "No SSE progress events", "status": "warning"},
        {"label": "No artifact storage integration", "status": "warning"},
        {"label": "No partial rerun support", "status": "warning"},
    ]

    blockers = []

    # Check loops
    if contains_loop_or_cycle(nodes, edges):
        blockers.append({
            "label": "Loop graphs cannot be exported",
            "status": "error",
            "detail": "The compiler cannot faithfully reproduce loop semantics in a standalone script.",
        })

    # Check custom/non-exportable blocks
    from ..engine.block_registry import get_block_yaml
    _NON_EXPORTABLE_BLOCK_TYPES = {"python_runner"}
    for node in nodes:
        if node.get("type") in ("groupNode", "stickyNote"):
            continue
        data = node.get("data", {})
        block_type = data.get("type", "")
        label = data.get("label", block_type)

        if block_type in _NON_EXPORTABLE_BLOCK_TYPES:
            blockers.append({
                "label": f"Custom code blocks cannot be exported",
                "status": "error",
                "detail": f"Block '{label}' is a {block_type} block.",
            })

        schema = get_block_yaml(block_type)
        if schema and schema.get("exportable") is False:
            blockers.append({
                "label": f"Block '{label}' is not exportable",
                "status": "error",
                "detail": f"{block_type} is marked as non-exportable in its block.yaml.",
            })

    can_export = len(blockers) == 0

    return {
        "can_export": can_export,
        "supported": supported,
        "warnings": warnings,
        "blockers": blockers,
    }
