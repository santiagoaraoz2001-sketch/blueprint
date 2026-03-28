import copy
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.pipeline import Pipeline
from ..schemas.pipeline import PipelineCreate, PipelineUpdate, PipelineResponse, CloneAsVariantRequest

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


# ── Config Diff Engine ───────────────────────────────────────────────

def _compute_config_diff(
    source_definition: dict,
    variant_definition: dict,
    source_pipeline_id: str,
    source_pipeline_name: str,
) -> dict:
    """Compute a comprehensive config diff between a source and variant pipeline.

    Handles:
    - Modified configs (same node ID, different config values)
    - Added nodes (present in variant but absent in source)
    - Removed nodes (present in source but absent in variant)
    - Fuzzy matching: when a node ID changes but block_type + label match,
      the node is treated as "moved" and its configs are still diffed.
    """
    source_nodes_list = source_definition.get("nodes", [])
    variant_nodes_list = variant_definition.get("nodes", [])

    source_by_id = {n.get("id"): n for n in source_nodes_list}
    variant_by_id = {n.get("id"): n for n in variant_nodes_list}

    source_ids = set(source_by_id.keys())
    variant_ids = set(variant_by_id.keys())

    # Phase 1: Direct ID matches
    matched_source_ids: set[str] = set()
    matched_variant_ids: set[str] = set()
    id_matches: list[tuple[str, str]] = []  # (source_id, variant_id)

    for nid in source_ids & variant_ids:
        id_matches.append((nid, nid))
        matched_source_ids.add(nid)
        matched_variant_ids.add(nid)

    # Phase 2: Fuzzy matching for unmatched nodes by (block_type, label)
    unmatched_source = source_ids - matched_source_ids
    unmatched_variant = variant_ids - matched_variant_ids

    if unmatched_source and unmatched_variant:
        # Build signature -> node_id maps for unmatched nodes
        source_sigs: dict[tuple[str, str], str] = {}
        for sid in unmatched_source:
            sn = source_by_id[sid]
            sig = (
                sn.get("data", {}).get("type", ""),
                sn.get("data", {}).get("label", ""),
            )
            # Only use first match per signature to avoid ambiguity
            if sig not in source_sigs:
                source_sigs[sig] = sid

        for vid in list(unmatched_variant):
            vn = variant_by_id[vid]
            sig = (
                vn.get("data", {}).get("type", ""),
                vn.get("data", {}).get("label", ""),
            )
            if sig in source_sigs:
                sid = source_sigs.pop(sig)
                id_matches.append((sid, vid))
                matched_source_ids.add(sid)
                matched_variant_ids.add(vid)

    # Phase 3: Compute per-field diffs for matched pairs
    changed_keys: dict[str, dict[str, dict]] = {}
    total_count = 0
    inherited_count = 0

    for source_id, variant_id in id_matches:
        source_config = source_by_id[source_id].get("data", {}).get("config", {})
        variant_config = variant_by_id[variant_id].get("data", {}).get("config", {})
        all_keys = set(source_config.keys()) | set(variant_config.keys())

        for key in all_keys:
            total_count += 1
            source_val = source_config.get(key)
            variant_val = variant_config.get(key)
            if source_val != variant_val:
                if variant_id not in changed_keys:
                    changed_keys[variant_id] = {}
                changed_keys[variant_id][key] = {
                    "source": source_val,
                    "current": variant_val,
                }
            else:
                inherited_count += 1

    # Phase 4: Track structural changes (added/removed nodes)
    added_node_ids = list(variant_ids - matched_variant_ids)
    removed_node_ids = list(source_ids - matched_source_ids)

    # Count configs in added nodes as "all changed" (no source to inherit from)
    for vid in added_node_ids:
        vn = variant_by_id[vid]
        variant_config = vn.get("data", {}).get("config", {})
        if variant_config:
            changed_keys[vid] = {
                key: {"source": None, "current": val}
                for key, val in variant_config.items()
            }
            total_count += len(variant_config)

    changed_count = total_count - inherited_count

    return {
        "source_pipeline_id": source_pipeline_id,
        "source_pipeline_name": source_pipeline_name,
        "changed_keys": changed_keys,
        "inherited_count": inherited_count,
        "total_count": total_count,
        "changed_count": changed_count,
        "added_nodes": [
            {
                "id": vid,
                "type": variant_by_id[vid].get("data", {}).get("type", ""),
                "label": variant_by_id[vid].get("data", {}).get("label", ""),
            }
            for vid in added_node_ids
        ],
        "removed_nodes": [
            {
                "id": sid,
                "type": source_by_id[sid].get("data", {}).get("type", ""),
                "label": source_by_id[sid].get("data", {}).get("label", ""),
            }
            for sid in removed_node_ids
        ],
    }


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

    # Auto-recompute config diff if this is a variant and definition changed
    if pipeline.source_pipeline_id and data.definition is not None:
        source = db.query(Pipeline).filter(Pipeline.id == pipeline.source_pipeline_id).first()
        if source:
            pipeline.config_diff = _compute_config_diff(
                source_definition=source.definition or {},
                variant_definition=pipeline.definition or {},
                source_pipeline_id=pipeline.source_pipeline_id,
                source_pipeline_name=source.name,
            )

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


@router.post("/{pipeline_id}/clone-variant")
def clone_as_variant(pipeline_id: str, data: CloneAsVariantRequest, db: Session = Depends(get_db)):
    """Clone a pipeline as an experiment variant with config diff tracking."""
    original = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not original:
        raise HTTPException(404, "Pipeline not found")

    # Count existing variants to generate default name
    variant_count = db.query(Pipeline).filter(
        Pipeline.source_pipeline_id == pipeline_id
    ).count()

    new_name = data.name or f"{original.name} (variant {variant_count + 1})"
    project_id = data.project_id or original.project_id

    # Deep-copy definition
    definition_copy = copy.deepcopy(original.definition or {})
    source_def = original.definition or {}

    # Compute initial config diff (identical at clone time → all inherited)
    config_diff = _compute_config_diff(
        source_definition=source_def,
        variant_definition=definition_copy,
        source_pipeline_id=pipeline_id,
        source_pipeline_name=original.name,
    )

    clone = Pipeline(
        id=str(uuid.uuid4()),
        name=new_name,
        project_id=project_id,
        experiment_id=original.experiment_id,
        description=original.description,
        definition=definition_copy,
        source_pipeline_id=pipeline_id,
        variant_notes=data.variant_notes,
        config_diff=config_diff,
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)

    return {
        "pipeline": PipelineResponse.model_validate(clone).model_dump(),
        "new_pipeline_id": clone.id,
        "inherited_config_count": config_diff["inherited_count"],
        "total_config_count": config_diff["total_count"],
    }


@router.post("/{pipeline_id}/update-config-diff")
def update_config_diff(pipeline_id: str, db: Session = Depends(get_db)):
    """Recompute config diff between a variant and its source pipeline."""
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    if not pipeline.source_pipeline_id:
        return {"changed_count": 0, "total_count": 0, "changes": {}}

    source = db.query(Pipeline).filter(Pipeline.id == pipeline.source_pipeline_id).first()
    if not source:
        return {"changed_count": 0, "total_count": 0, "changes": {}}

    config_diff = _compute_config_diff(
        source_definition=source.definition or {},
        variant_definition=pipeline.definition or {},
        source_pipeline_id=pipeline.source_pipeline_id,
        source_pipeline_name=source.name,
    )

    pipeline.config_diff = config_diff
    db.commit()

    return {
        "changed_count": config_diff["changed_count"],
        "inherited_count": config_diff["inherited_count"],
        "total_count": config_diff["total_count"],
        "changes": config_diff["changed_keys"],
        "added_nodes": config_diff["added_nodes"],
        "removed_nodes": config_diff["removed_nodes"],
        "source_pipeline_name": source.name,
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
