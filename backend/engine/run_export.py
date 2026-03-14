"""
Structured run export — generates a portable dict from a completed Run.

Used by export connectors to push run data to external services.
"""

import json
import logging
from pathlib import Path
from typing import Any

from ..models.run import Run

_logger = logging.getLogger("blueprint.run_export")


def generate_run_export(run: Run, artifacts_dir: Path) -> dict[str, Any]:
    """Build a structured export dict from a Run record.

    Args:
        run: The SQLAlchemy Run object.
        artifacts_dir: Root artifacts directory (e.g. ``~/.specific-labs/artifacts``).

    Returns:
        A portable dict containing run metadata, config, metrics, outputs,
        and artifact manifest.
    """
    run_artifact_dir = artifacts_dir / run.id

    artifacts = _collect_artifact_manifest(run_artifact_dir)
    metrics_log = _collect_metrics_log(run, run_artifact_dir)

    return {
        "format": "blueprint-run-export",
        "version": "1.0",
        "run": {
            "id": run.id,
            "pipeline_id": run.pipeline_id,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "duration_seconds": run.duration_seconds,
            "error_message": run.error_message,
        },
        "config": run.config_snapshot or {},
        "metrics": run.metrics or {},
        "metrics_log": metrics_log,
        "outputs": run.outputs_snapshot or {},
        "data_fingerprints": run.data_fingerprints or {},
        "artifacts": artifacts,
    }


def _collect_artifact_manifest(run_artifact_dir: Path) -> list[dict[str, Any]]:
    """Walk the run's artifact directory and return a file manifest.

    Gracefully handles missing directories and permission errors on
    individual files (logs a warning and skips).
    """
    artifacts: list[dict[str, Any]] = []
    if not run_artifact_dir.is_dir():
        return artifacts

    try:
        entries = sorted(run_artifact_dir.rglob("*"))
    except OSError as exc:
        _logger.warning("Could not list artifacts in %s: %s", run_artifact_dir, exc)
        return artifacts

    for f in entries:
        if not f.is_file():
            continue
        try:
            stat = f.stat()
            artifacts.append({
                "path": str(f.relative_to(run_artifact_dir)),
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
        except OSError as exc:
            _logger.warning("Could not stat artifact %s: %s", f, exc)
            continue

    return artifacts


def _collect_metrics_log(run: Run, run_artifact_dir: Path) -> list[dict]:
    """Return the metrics event log, preferring Layer 2 (SQLite column) and
    falling back to Layer 1 (JSONL file on disk).
    """
    if run.metrics_log:
        return run.metrics_log

    jsonl_path = run_artifact_dir / "metrics.jsonl"
    if not jsonl_path.is_file():
        return []

    events: list[dict] = []
    try:
        for line in jsonl_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError as exc:
        _logger.warning("Could not read metrics log %s: %s", jsonl_path, exc)

    return events
