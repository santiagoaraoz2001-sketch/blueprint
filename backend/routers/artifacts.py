"""Artifact cache management endpoints — storage usage and cleanup."""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..config import ARTIFACTS_DIR
from ..engine.artifacts import ArtifactStore

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])

_store = ArtifactStore(base_path=Path(ARTIFACTS_DIR))


@router.get("/usage")
def get_artifact_usage():
    """Return artifact cache storage statistics."""
    return _store.get_storage_usage()


@router.delete("/runs/{run_id}")
def cleanup_run_artifacts(run_id: str):
    """Delete all cached artifacts for a specific run. Returns bytes freed."""
    bytes_freed = _store.cleanup_run(run_id)
    if bytes_freed == 0:
        raise HTTPException(status_code=404, detail=f"No artifacts found for run {run_id}")
    return {"run_id": run_id, "bytes_freed": bytes_freed}
