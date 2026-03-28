"""Generate a structured export schema for a completed run."""

import hashlib
import json
import sys
import platform as plat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import ARTIFACTS_DIR
from ..utils.redact import redact_config

EXPORT_SCHEMA_VERSION = "1.0.0"

# Files managed by the engine that are not user-facing artifacts
_INTERNAL_FILES = {"metrics.jsonl", "run-export.json", "error.log"}


def _collect_artifacts(run_dir: Path) -> list[dict]:
    """Collect artifact metadata from the run directory.

    Excludes internal engine files (metrics.jsonl, run-export.json, error.log).
    Handles files that may be deleted between enumeration and stat().
    """
    artifacts = []
    if not run_dir.exists():
        return artifacts

    for f in sorted(run_dir.rglob("*")):
        if not f.is_file():
            continue
        if f.name in _INTERNAL_FILES and f.parent == run_dir:
            continue
        try:
            size = f.stat().st_size
        except OSError:
            # File may have been deleted between rglob and stat
            continue
        artifacts.append({
            "name": str(f.relative_to(run_dir)),
            "path": str(f),
            "size_bytes": size,
        })

    return artifacts


def _extract_pipeline_metadata(config_snapshot: dict | None) -> dict:
    """Extract pipeline-level metadata from the config snapshot."""
    definition = config_snapshot or {}
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    # Compute a deterministic hash of the pipeline definition
    definition_hash = None
    if definition:
        canonical = json.dumps(definition, sort_keys=True, separators=(",", ":"))
        definition_hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]

    return {
        "definition_hash": definition_hash,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def _collect_environment() -> dict[str, Any]:
    """Collect runtime environment information."""
    env: dict[str, Any] = {
        "python_version": sys.version.split()[0],
        "platform": plat.platform(),
        "blueprint_version": "0.2.2",
    }
    try:
        import torch
        env["torch_version"] = torch.__version__
        env["gpu_available"] = torch.cuda.is_available()
    except ImportError:
        env["gpu_available"] = False
    return env


def generate_run_export(run, artifacts_dir: Path | None = None) -> dict:
    """
    Generate the universal run export schema.

    This is the "lingua franca" JSON that downstream tools, export connectors,
    and external scripts can parse without custom Blueprint knowledge.

    Args:
        run: A Run ORM instance with metrics, config_snapshot, etc.
        artifacts_dir: Override for the artifacts root directory.

    Returns:
        Dict conforming to the run export schema (version 1.0.0).
    """
    if artifacts_dir is None:
        artifacts_dir = ARTIFACTS_DIR

    run_dir = artifacts_dir / run.id

    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "export_timestamp": datetime.now(timezone.utc).isoformat(),
        "run": {
            "id": run.id,
            "pipeline_id": run.pipeline_id,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "duration_seconds": run.duration_seconds,
        },
        "pipeline": _extract_pipeline_metadata(run.config_snapshot),
        "config": redact_config(run.config_snapshot or {}),
        "metrics": {
            "summary": run.metrics or {},
            "timeseries": run.metrics_log or [],
        },
        "artifacts": _collect_artifacts(run_dir),
        "data_provenance": getattr(run, "data_fingerprints", None) or {},
        "environment": _collect_environment(),
    }
