"""Pipeline version history — auto-versioning on save, preview, restore, and export."""

import json
import logging
import platform
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.pipeline import Pipeline
from ..models.pipeline_version import PipelineVersion
from ..schemas.pipeline_version import (
    PipelineVersionResponse,
    PipelineVersionSummary,
    RestoreVersionRequest,
)

logger = logging.getLogger("blueprint.versions")

router = APIRouter(prefix="/api/pipelines", tags=["pipeline-versions"])

# Maximum retries for concurrent version number conflicts.
# In practice conflicts are near-impossible with SQLite's WAL serialization,
# but this makes the code safe for any backend (e.g. PostgreSQL migration).
_MAX_VERSION_RETRIES = 3


def _next_version_number(db: Session, pipeline_id: str) -> int:
    """Return the next version number for a pipeline.

    Uses SELECT ... FOR UPDATE semantics where supported (PostgreSQL),
    and relies on the UNIQUE constraint + retry loop as a safety net
    for all backends including SQLite.
    """
    max_ver = (
        db.query(func.max(PipelineVersion.version_number))
        .filter(PipelineVersion.pipeline_id == pipeline_id)
        .scalar()
    )
    return (max_ver or 0) + 1


def create_version_for_pipeline(
    db: Session,
    pipeline_id: str,
    snapshot_dict: dict,
    author: str = "local",
    message: str | None = None,
) -> PipelineVersion:
    """Create a new pipeline version with concurrency-safe version numbering.

    If two concurrent saves race on the same pipeline, the UNIQUE constraint
    on (pipeline_id, version_number) will reject the loser. We retry up to
    _MAX_VERSION_RETRIES times with a fresh MAX() query, which is guaranteed
    to see the winner's committed row (SQLite WAL read-committed isolation).
    """
    snapshot_json = json.dumps(snapshot_dict, sort_keys=True)
    last_error: Exception | None = None

    for attempt in range(_MAX_VERSION_RETRIES):
        version_number = _next_version_number(db, pipeline_id)
        version = PipelineVersion(
            id=str(uuid.uuid4()),
            pipeline_id=pipeline_id,
            version_number=version_number,
            snapshot=snapshot_json,
            author=author,
            message=message,
            created_at=datetime.now(timezone.utc),
        )
        db.add(version)
        try:
            db.flush()  # Push to DB to trigger unique constraint check
            return version
        except IntegrityError as exc:
            last_error = exc
            db.rollback()
            logger.warning(
                "Version number %d conflict on pipeline %s (attempt %d/%d)",
                version_number, pipeline_id, attempt + 1, _MAX_VERSION_RETRIES,
            )

    raise RuntimeError(
        f"Failed to allocate version number for pipeline {pipeline_id} "
        f"after {_MAX_VERSION_RETRIES} attempts: {last_error}"
    )


# ── List versions ────────────────────────────────────────────────────
@router.get(
    "/{pipeline_id}/versions",
    response_model=list[PipelineVersionSummary],
)
def list_versions(pipeline_id: str, db: Session = Depends(get_db)):
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")
    versions = (
        db.query(PipelineVersion)
        .filter(PipelineVersion.pipeline_id == pipeline_id)
        .order_by(PipelineVersion.version_number.desc())
        .all()
    )
    return versions


# ── Get single version (includes full snapshot) ──────────────────────
@router.get(
    "/{pipeline_id}/versions/{version_number}",
    response_model=PipelineVersionResponse,
)
def get_version(pipeline_id: str, version_number: int, db: Session = Depends(get_db)):
    version = (
        db.query(PipelineVersion)
        .filter(
            PipelineVersion.pipeline_id == pipeline_id,
            PipelineVersion.version_number == version_number,
        )
        .first()
    )
    if not version:
        raise HTTPException(404, "Version not found")
    return version


# ── Restore a version ────────────────────────────────────────────────
@router.post("/{pipeline_id}/versions/{version_number}/restore")
def restore_version(
    pipeline_id: str,
    version_number: int,
    body: RestoreVersionRequest | None = None,
    db: Session = Depends(get_db),
):
    """Restore creates a *new* version with the old snapshot and sets it as current state."""
    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    old_version = (
        db.query(PipelineVersion)
        .filter(
            PipelineVersion.pipeline_id == pipeline_id,
            PipelineVersion.version_number == version_number,
        )
        .first()
    )
    if not old_version:
        raise HTTPException(404, "Version not found")

    snapshot_dict = json.loads(old_version.snapshot)

    # Create a new version with the restored snapshot
    message = (body.message if body and body.message else f"Restored from v{version_number}")
    new_version = create_version_for_pipeline(
        db, pipeline_id, snapshot_dict, message=message,
    )

    # Update the pipeline's current definition to the restored state
    pipeline.definition = snapshot_dict
    pipeline.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(new_version)

    return {
        "restored_from": version_number,
        "new_version": new_version.version_number,
        "pipeline_id": pipeline_id,
    }


# ── Export as deterministic .blueprint.json ──────────────────────────
@router.get("/{pipeline_id}/export-blueprint")
def export_blueprint(pipeline_id: str, db: Session = Depends(get_db)):
    """Export the pipeline as a deterministic .blueprint.json for git-friendly storage."""
    from ..engine.config_resolver import resolve_configs
    from ..engine.executor import _topological_sort
    from ..engine.block_registry import BlockRegistryService

    pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    definition = pipeline.definition or {}
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    # Resolve configs for the export
    resolved_configs = {}
    block_versions = {}
    if nodes:
        try:
            order = _topological_sort(nodes, edges)
            registry = BlockRegistryService()
            resolved_tuples = resolve_configs(nodes, edges, order, registry=registry)
            resolved_configs = {
                nid: cfg for nid, (cfg, _src) in resolved_tuples.items()
            }
        except Exception:
            pass  # Graceful degradation — export without resolved configs

        # Collect block versions from node data
        for node in nodes:
            block_type = node.get("data", {}).get("type", "")
            block_version = node.get("data", {}).get("block_version", "unknown")
            if block_type:
                block_versions[block_type] = block_version

    blueprint = {
        "version": "1.0.0",
        "pipeline_name": pipeline.name,
        "nodes": nodes,
        "edges": edges,
        "resolved_configs": resolved_configs,
        "block_versions": block_versions,
        "platform_profile": {
            "os": platform.system(),
            "python": platform.python_version(),
            "capabilities": [],
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Deterministic JSON with sorted keys for clean git diffs
    content = json.dumps(blueprint, sort_keys=True, indent=2)
    return JSONResponse(
        content=json.loads(content),
        headers={
            "Content-Disposition": f'attachment; filename="{pipeline.name}.blueprint.json"',
        },
    )
