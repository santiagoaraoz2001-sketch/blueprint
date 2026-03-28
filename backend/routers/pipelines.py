import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Any

from ..config import SNAPSHOTS_DIR
from ..database import get_db
from ..models.pipeline import Pipeline
from ..schemas.pipeline import PipelineCreate, PipelineUpdate, PipelineHistoryUpdate, PipelineResponse

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


class HistorySnapshotPayload(BaseModel):
    """Full history snapshots (for SNAPSHOTS_DIR file)."""
    history_snapshots: str  # JSON-encoded full history with nodes/edges


@router.put("/{pipeline_id}/history", status_code=204)
def update_pipeline_history(pipeline_id: str, data: PipelineHistoryUpdate, db: Session = Depends(get_db)):
    """Persist lightweight history metadata in the DB column."""
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")
    pipeline.history_json = data.history_json
    db.commit()


@router.post("/{pipeline_id}/history", status_code=204)
def update_pipeline_history_post(pipeline_id: str, data: PipelineHistoryUpdate, db: Session = Depends(get_db)):
    """POST alias for history persistence — required by navigator.sendBeacon()
    which only supports POST. Identical behavior to PUT."""
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")
    pipeline.history_json = data.history_json
    db.commit()


@router.post("/{pipeline_id}/history/snapshots", status_code=204)
def update_pipeline_history_snapshots_post(pipeline_id: str, data: HistorySnapshotPayload):
    """POST alias for snapshot persistence — required by navigator.sendBeacon()."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOTS_DIR / f"{pipeline_id}_history.json"
    path.write_text(data.history_snapshots)


@router.put("/{pipeline_id}/history/snapshots", status_code=204)
def update_pipeline_history_snapshots(pipeline_id: str, data: HistorySnapshotPayload):
    """Persist full history snapshots to SNAPSHOTS_DIR (off the DB).

    This keeps heavy node/edge data out of the SQLite database.
    The file is capped at ~5 MB by the frontend serializer.
    """
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOTS_DIR / f"{pipeline_id}_history.json"
    path.write_text(data.history_snapshots)


@router.get("/{pipeline_id}/history/snapshots")
def get_pipeline_history_snapshots(pipeline_id: str):
    """Retrieve full history snapshots from SNAPSHOTS_DIR."""
    path = SNAPSHOTS_DIR / f"{pipeline_id}_history.json"
    if not path.exists():
        return {"exists": False, "history_snapshots": None}
    try:
        return {"exists": True, "history_snapshots": path.read_text()}
    except OSError:
        return {"exists": False, "history_snapshots": None}


class AutosavePayload(BaseModel):
    definition: dict[str, Any]
    name: str = ""
    session_id: str = ""


import re

_SAFE_ID_RE = re.compile(r"^[a-z0-9\-]{1,64}$")


def _autosave_glob(pipeline_id: str) -> list[Path]:
    """Find all autosave files for a pipeline across all sessions.

    Pattern: {pipeline_id}_*_autosave.json
    Falls back to legacy {pipeline_id}_autosave.json for backward compat.
    """
    results = list(SNAPSHOTS_DIR.glob(f"{pipeline_id}_*_autosave.json"))
    legacy = SNAPSHOTS_DIR / f"{pipeline_id}_autosave.json"
    if legacy.exists() and legacy not in results:
        results.append(legacy)
    return results


@router.post("/{pipeline_id}/autosave", status_code=204)
def create_autosave(pipeline_id: str, data: AutosavePayload):
    """Write a session-scoped autosave snapshot to SNAPSHOTS_DIR.

    Each browser tab sends a unique session_id so that concurrent
    tabs editing the same pipeline don't overwrite each other.
    """
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    # Sanitize session_id to prevent path traversal
    session_id = data.session_id if _SAFE_ID_RE.match(data.session_id) else "default"
    path = SNAPSHOTS_DIR / f"{pipeline_id}_{session_id}_autosave.json"

    payload = {
        "pipeline_id": pipeline_id,
        "session_id": session_id,
        "name": data.name,
        "definition": data.definition,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload))


@router.get("/{pipeline_id}/autosave")
def get_autosave(pipeline_id: str, db: Session = Depends(get_db)):
    """Find the newest autosave across all sessions for a pipeline.

    Scans all {pipeline_id}_*_autosave.json files, returns the one
    with the most recent timestamp — but only if it's newer than
    the last explicit save.
    """
    candidates = _autosave_glob(pipeline_id)
    if not candidates:
        return {"exists": False}

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        return {"exists": False}

    last_save_dt = pipeline.updated_at
    if last_save_dt.tzinfo is None:
        last_save_dt = last_save_dt.replace(tzinfo=timezone.utc)

    # Find the newest valid autosave
    best = None
    best_dt = None
    stale_paths = []

    for path in candidates:
        try:
            data = json.loads(path.read_text())
            ts = data.get("timestamp", "")
            dt = datetime.fromisoformat(ts)
        except (json.JSONDecodeError, OSError, ValueError, TypeError):
            stale_paths.append(path)
            continue

        if dt <= last_save_dt:
            stale_paths.append(path)
            continue

        if best_dt is None or dt > best_dt:
            # If we had a previous best, it's now stale relative to this one
            if best is not None:
                stale_paths.append(best["_path"])
            best = {**data, "_path": path}
            best_dt = dt

    # Clean up stale autosaves
    for p in stale_paths:
        p.unlink(missing_ok=True)

    if best is None:
        return {"exists": False}

    return {
        "exists": True,
        "timestamp": best.get("timestamp"),
        "definition": best.get("definition"),
        "name": best.get("name", ""),
    }


@router.delete("/{pipeline_id}/autosave", status_code=204)
def delete_autosave(pipeline_id: str):
    """Delete ALL autosave files for a pipeline (from any session)."""
    for path in _autosave_glob(pipeline_id):
        path.unlink(missing_ok=True)


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
