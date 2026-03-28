import json
import uuid
from pathlib import Path

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..config import ARTIFACTS_DIR
from ..database import get_db
from ..models.run import Run
from ..models.pipeline import Pipeline
from ..models.experiment_phase import ExperimentPhase
from ..schemas.run import RunResponse, RunMetadataUpdate
from ..schemas.pipeline import PipelineResponse

router = APIRouter(prefix="/api/runs", tags=["runs"])


class AssignRequest(BaseModel):
    experiment_phase_id: str


def _flatten_dict(d: dict, prefix: str = '') -> dict:
    """Flatten nested dicts: {"a": {"b": 1}} -> {"a.b": 1}"""
    items = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            items.update(_flatten_dict(v, key))
        else:
            items[key] = v
    return items


@router.get("", response_model=list[RunResponse])
def list_runs(
    pipeline_id: str | None = None,
    project_id: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    starred: bool | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(Run)
    if pipeline_id:
        q = q.filter(Run.pipeline_id == pipeline_id)
    if project_id:
        q = q.filter(Run.project_id == project_id)
    if status:
        q = q.filter(Run.status == status)
    if tag:
        q = q.filter(Run.tags.contains(tag))
    if starred is not None:
        q = q.filter(Run.starred == starred)
    return q.order_by(Run.started_at.desc()).limit(limit).all()


@router.get("/compare")
def compare_runs(
    ids: str = Query(None, description="Comma-separated run IDs"),
    pipeline_id: str = Query(None, description="Pipeline ID to compare all runs"),
    db: Session = Depends(get_db),
):
    """Compare runs with flattened config/metric columns for table display and diff."""
    if ids:
        run_ids = [rid.strip() for rid in ids.split(",")]
        runs = db.query(Run).filter(Run.id.in_(run_ids)).order_by(Run.started_at.desc()).all()
    elif pipeline_id:
        runs = db.query(Run).filter(Run.pipeline_id == pipeline_id).order_by(Run.started_at.desc()).limit(50).all()
    else:
        raise HTTPException(400, "Provide 'ids' or 'pipeline_id'")

    if not runs:
        return {'config_columns': [], 'metric_columns': [], 'runs': []}

    # Extract all unique config and metric keys across runs
    all_config_keys: set[str] = set()
    all_metric_keys: set[str] = set()

    for run in runs:
        config = run.config_snapshot if isinstance(run.config_snapshot, dict) else {}
        flat_config = _flatten_dict(config)
        all_config_keys.update(flat_config.keys())

        metrics = run.metrics if isinstance(run.metrics, dict) else {}
        all_metric_keys.update(metrics.keys())

    sorted_config = sorted(all_config_keys)
    sorted_metrics = sorted(all_metric_keys)

    rows = []
    for run in runs:
        config = run.config_snapshot if isinstance(run.config_snapshot, dict) else {}
        flat_config = _flatten_dict(config)
        metrics = run.metrics if isinstance(run.metrics, dict) else {}

        rows.append({
            'id': run.id,
            'status': run.status,
            'started_at': run.started_at.isoformat() if run.started_at else None,
            'finished_at': run.finished_at.isoformat() if run.finished_at else None,
            'duration_seconds': run.duration_seconds,
            'error_message': run.error_message,
            'config': {k: flat_config.get(k) for k in sorted_config},
            'metrics': {k: metrics.get(k) for k in sorted_metrics},
        })

    return {
        'config_columns': sorted_config,
        'metric_columns': sorted_metrics,
        'runs': rows,
    }


@router.get("/{run_id}/metrics-log")
def get_metrics_log(run_id: str, db: Session = Depends(get_db)):
    """Return the full metrics event log for a run.

    Layer 2 (SQLite) is preferred. Falls back to Layer 1 (JSONL file)
    if metrics_log is null (crash recovery / old runs).
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    # Layer 2: SQLite metrics_log
    if run.metrics_log:
        return run.metrics_log

    # Layer 1 fallback: JSONL file
    jsonl_path = ARTIFACTS_DIR / run_id / "metrics.jsonl"
    if jsonl_path.exists():
        events = []
        for line in jsonl_path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return events

    return []


@router.get("/{run_id}/metrics-typed")
def get_typed_metrics(run_id: str, db: Session = Depends(get_db)):
    """Get metrics with schema version and aggregation.

    Layer 2 (SQLite metrics_log) is preferred.  Falls back to Layer 1
    (JSONL file) when metrics_log is null -- e.g. crash recovery or
    old runs that pre-date the column.
    """
    from ..engine.metrics_schema import (
        CURRENT_SCHEMA_VERSION, parse_metrics_log, aggregate_metrics,
    )

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    raw_log = run.metrics_log
    if not raw_log:
        # Layer 1 fallback: JSONL file
        jsonl_path = ARTIFACTS_DIR / run_id / "metrics.jsonl"
        if jsonl_path.exists():
            raw_log = []
            for line in jsonl_path.read_text().splitlines():
                line = line.strip()
                if line:
                    try:
                        raw_log.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

    events = parse_metrics_log(raw_log or [])
    summary = aggregate_metrics(events)

    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "events": [e.to_dict() for e in events],
        "summary": summary,
        "event_count": len(events),
    }


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@router.put("/{run_id}/metadata", response_model=RunResponse)
def update_run_metadata(run_id: str, data: RunMetadataUpdate, db: Session = Depends(get_db)):
    """Update run notes, tags, and/or starred status."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(run, key, value)
    db.commit()
    db.refresh(run)
    return run


@router.post("/{run_id}/assign")
def assign_run(run_id: str, data: AssignRequest, db: Session = Depends(get_db)):
    """Retroactively assign a run to an experiment phase via its pipeline."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    phase = db.query(ExperimentPhase).filter(ExperimentPhase.id == data.experiment_phase_id).first()
    if not phase:
        raise HTTPException(404, "Experiment phase not found")

    pipeline = db.query(Pipeline).filter(Pipeline.id == run.pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    pipeline.experiment_phase_id = data.experiment_phase_id
    db.commit()

    # Trigger lifecycle recalculation
    try:
        from ..services.project_lifecycle import on_run_completed
        if run.status == "complete":
            on_run_completed(run_id, db)
    except Exception:
        pass

    return {"status": "assigned", "run_id": run_id, "experiment_phase_id": data.experiment_phase_id}


@router.get("/{run_id}/artifacts")
def list_artifacts(run_id: str, db: Session = Depends(get_db)):
    """List files in a run's artifact directory."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    artifact_dir = ARTIFACTS_DIR / run_id
    if not artifact_dir.exists():
        return []

    files = []
    for f in sorted(artifact_dir.iterdir()):
        if f.is_file():
            files.append({
                "name": f.name,
                "size": f.stat().st_size,
                "modified": f.stat().st_mtime,
            })
    return files


@router.get("/{run_id}/artifacts/{filename}")
def get_artifact(run_id: str, filename: str, db: Session = Depends(get_db)):
    """Download a specific artifact file."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    file_path = ARTIFACTS_DIR / run_id / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "Artifact not found")

    # Prevent path traversal
    try:
        file_path.resolve().relative_to((ARTIFACTS_DIR / run_id).resolve())
    except ValueError:
        raise HTTPException(400, "Invalid file path")

    from fastapi.responses import FileResponse
    return FileResponse(str(file_path), filename=filename)


@router.get("/{run_id}/export")
def get_run_export(run_id: str, db: Session = Depends(get_db)):
    """Get the structured export for a run."""
    from ..engine.run_export import generate_run_export

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    return generate_run_export(run, ARTIFACTS_DIR)


@router.get("/{run_id}/export/download")
def download_run_export(run_id: str, db: Session = Depends(get_db)):
    """Download run-export.json as a file."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    # Use the validated run.id (from DB) to construct the path, not raw input
    export_path = ARTIFACTS_DIR / run.id / "run-export.json"

    # Prevent path traversal
    try:
        export_path.resolve().relative_to(ARTIFACTS_DIR.resolve())
    except ValueError:
        raise HTTPException(400, "Invalid run ID")

    if not export_path.exists():
        raise HTTPException(404, "Export not yet generated")

    from fastapi.responses import FileResponse
    return FileResponse(str(export_path), filename=f"blueprint-run-{run.id[:8]}.json")


@router.get("/{run_id}/data-provenance")
def get_data_provenance(run_id: str, db: Session = Depends(get_db)):
    """Return data fingerprints for a run, showing which datasets were used."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    return {
        "run_id": run_id,
        "fingerprints": run.data_fingerprints or {},
    }


@router.post("/compare-data")
def compare_run_data(
    run_id_a: str = Query(..., description="First run ID"),
    run_id_b: str = Query(..., description="Second run ID"),
    db: Session = Depends(get_db),
):
    """Compare data fingerprints between two runs."""
    run_a = db.query(Run).filter(Run.id == run_id_a).first()
    run_b = db.query(Run).filter(Run.id == run_id_b).first()
    if not run_a or not run_b:
        raise HTTPException(404, "Run not found")

    fp_a = run_a.data_fingerprints or {}
    fp_b = run_b.data_fingerprints or {}

    diffs = []
    all_nodes = set(fp_a.keys()) | set(fp_b.keys())
    for node_id in sorted(all_nodes):
        a_inputs = fp_a.get(node_id, {})
        b_inputs = fp_b.get(node_id, {})
        for input_name in sorted(set(a_inputs.keys()) | set(b_inputs.keys())):
            hash_a = a_inputs.get(input_name, {}).get("hash")
            hash_b = b_inputs.get(input_name, {}).get("hash")
            if hash_a != hash_b:
                diffs.append({
                    "node_id": node_id,
                    "input": input_name,
                    "run_a_hash": hash_a,
                    "run_b_hash": hash_b,
                    "changed": True,
                })

    return {"identical": len(diffs) == 0, "diffs": diffs}


@router.get("/{run_id}/checkpoints")
def list_checkpoints(run_id: str):
    """List all checkpoints for a training run."""
    # Prevent path traversal
    run_dir = ARTIFACTS_DIR / run_id
    try:
        run_dir.resolve().relative_to(ARTIFACTS_DIR.resolve())
    except ValueError:
        raise HTTPException(400, "Invalid run ID")

    manifest_path = run_dir / "checkpoints" / "manifest.json"
    if not manifest_path.exists():
        return {"checkpoints": []}
    try:
        with open(manifest_path) as f:
            data = json.load(f)
        if not isinstance(data, list):
            return {"checkpoints": []}
        return {"checkpoints": data}
    except (json.JSONDecodeError, OSError):
        return {"checkpoints": []}


@router.post("/{run_id}/checkpoints/{epoch}/load")
def load_checkpoint_as_model(run_id: str, epoch: int, db: Session = Depends(get_db)):
    """Create a new model reference from a checkpoint, usable as input to other blocks."""
    # Prevent path traversal
    run_dir = ARTIFACTS_DIR / run_id
    try:
        run_dir.resolve().relative_to(ARTIFACTS_DIR.resolve())
    except ValueError:
        raise HTTPException(400, "Invalid run ID")

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    manifest_path = run_dir / "checkpoints" / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(404, "No checkpoints found")

    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
        if not isinstance(manifest, list):
            raise HTTPException(404, "No checkpoints found")
    except (json.JSONDecodeError, OSError):
        raise HTTPException(500, "Checkpoint manifest is corrupted")

    checkpoint = next(
        (c for c in manifest if isinstance(c, dict) and c.get("epoch") == epoch),
        None,
    )
    if not checkpoint:
        raise HTTPException(404, f"Checkpoint at epoch {epoch} not found")

    return {
        "model_path": checkpoint.get("path", ""),
        "source_run": run_id,
        "source_epoch": epoch,
        "metrics": checkpoint.get("metrics", {}),
    }


@router.post("/{run_id}/clone-pipeline", response_model=PipelineResponse)
def clone_pipeline_from_run(run_id: str, db: Session = Depends(get_db)):
    """Create a new pipeline from a run's config_snapshot."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    original = db.query(Pipeline).filter(Pipeline.id == run.pipeline_id).first()
    name = f"{original.name} (from run)" if original else "Pipeline from run"

    new_pipeline = Pipeline(
        id=str(uuid.uuid4()),
        name=name,
        project_id=original.project_id if original else None,
        experiment_id=original.experiment_id if original else None,
        description=f"Cloned from run {run_id[:8]}",
        definition=run.config_snapshot or {},
    )
    db.add(new_pipeline)
    db.commit()
    db.refresh(new_pipeline)
    return new_pipeline
