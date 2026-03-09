from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.run import Run
from ..schemas.run import RunResponse

router = APIRouter(prefix="/api/runs", tags=["runs"])


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
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(Run)
    if pipeline_id:
        q = q.filter(Run.pipeline_id == pipeline_id)
    if status:
        q = q.filter(Run.status == status)
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


@router.get("/{run_id}", response_model=RunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    return run
