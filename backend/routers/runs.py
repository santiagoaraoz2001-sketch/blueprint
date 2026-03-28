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

        # Build metric_sources: {metric_key: node_id} from metrics_log
        # The metrics_log contains typed events with node_id for each metric.
        # We take the *last* node_id that emitted each metric key (matching
        # how all_metrics stores `block_type.metric_name` as the key, with
        # the last-written value winning).
        metric_sources: dict[str, str] = {}
        metrics_log = run.metrics_log if isinstance(run.metrics_log, list) else []
        for event in metrics_log:
            if not isinstance(event, dict):
                continue
            if event.get("type") != "metric":
                continue
            ename = event.get("name", "")
            enode = event.get("node_id", "")
            if not ename or not enode:
                continue
            # Reconstruct the key format used in all_metrics: block_type.name
            # The category is present in the event but not the block_type; however
            # we also need to try raw metric name matching since the compare
            # columns use the keys from run.metrics which are block_type.name.
            # Match both: the raw metric name and all possible prefixed forms.
            for mk in sorted_metrics:
                if mk == ename or mk.endswith(f".{ename}"):
                    metric_sources[mk] = enode

        rows.append({
            'id': run.id,
            'status': run.status,
            'started_at': run.started_at.isoformat() if run.started_at else None,
            'finished_at': run.finished_at.isoformat() if run.finished_at else None,
            'duration_seconds': run.duration_seconds,
            'error_message': run.error_message,
            'best_in_project': bool(run.best_in_project),
            'config': {k: flat_config.get(k) for k in sorted_config},
            'metrics': {k: metrics.get(k) for k in sorted_metrics},
            'metric_sources': metric_sources,
        })

    return {
        'config_columns': sorted_config,
        'metric_columns': sorted_metrics,
        'runs': rows,
    }


@router.post("/{run_id}/star")
def toggle_star(run_id: str, db: Session = Depends(get_db)):
    """Toggle the starred status of a run."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    run.starred = not bool(run.starred)
    db.commit()
    return {"run_id": run_id, "starred": run.starred}


@router.post("/batch-metrics-log")
def batch_metrics_log(
    body: dict,
    db: Session = Depends(get_db),
):
    """Return metrics logs for multiple runs in one request.

    Body: {"run_ids": ["id1", "id2", ...]}
    Returns: {"run_id": [...events...], ...}

    Each run's log is sourced from Layer 2 (SQLite metrics_log column)
    with Layer 1 (JSONL file) fallback, same as the single-run endpoint.
    """
    run_ids = body.get("run_ids", [])
    if not run_ids or not isinstance(run_ids, list):
        raise HTTPException(400, "Provide run_ids list")
    if len(run_ids) > 20:
        raise HTTPException(400, "Maximum 20 run IDs per batch request")

    runs = db.query(Run).filter(Run.id.in_(run_ids)).all()
    run_map = {r.id: r for r in runs}

    result = {}
    for rid in run_ids:
        run = run_map.get(rid)
        if not run:
            result[rid] = []
            continue

        # Layer 2: SQLite metrics_log
        if run.metrics_log:
            result[rid] = run.metrics_log
            continue

        # Layer 1 fallback: JSONL file
        jsonl_path = ARTIFACTS_DIR / rid / "metrics.jsonl"
        if jsonl_path.exists():
            events = []
            for line in jsonl_path.read_text().splitlines():
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            result[rid] = events
        else:
            result[rid] = []

    return result


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


@router.get("/{run_id}/decisions")
def get_execution_decisions(run_id: str, db: Session = Depends(get_db)):
    """Return execution decisions for a run, ordered by timestamp."""
    from ..models.execution_decision import ExecutionDecision

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    decisions = (
        db.query(ExecutionDecision)
        .filter(ExecutionDecision.run_id == run_id)
        .order_by(ExecutionDecision.timestamp.asc())
        .all()
    )

    # Build a node label lookup from the pipeline definition
    node_labels: dict[str, str] = {}
    if run.config_snapshot:
        for n in run.config_snapshot.get("nodes", []):
            node_labels[n["id"]] = n.get("data", {}).get("label", n["id"])

    return [
        {
            "id": d.id,
            "run_id": d.run_id,
            "node_id": d.node_id,
            "node_label": node_labels.get(d.node_id, d.node_id),
            "decision": d.decision,
            "reason": d.reason,
            "cache_fingerprint": d.cache_fingerprint,
            "plan_hash": d.plan_hash,
            "timestamp": d.timestamp.isoformat() if d.timestamp else None,
        }
        for d in decisions
    ]


@router.delete("/{run_id}/decisions", status_code=200)
def delete_run_decisions(run_id: str, db: Session = Depends(get_db)):
    """Delete all execution decisions for a specific run.

    Use for manual cleanup of decision logs for individual runs.
    """
    from ..models.execution_decision import ExecutionDecision

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    result = db.query(ExecutionDecision).filter(
        ExecutionDecision.run_id == run_id,
    ).delete(synchronize_session=False)
    db.commit()
    return {"deleted": result, "run_id": run_id}


@router.get("/decisions/stats")
def get_decision_stats(db: Session = Depends(get_db)):
    """Return statistics about the decision log.

    Includes total records, distinct runs, date range, and retention settings.
    """
    from ..services.decision_cleanup import get_decision_stats as _get_stats
    return _get_stats(db)


@router.post("/decisions/cleanup")
def trigger_decision_cleanup(db: Session = Depends(get_db)):
    """Manually trigger decision log cleanup.

    Deletes decisions for runs older than the retention threshold
    (default: 30 days), while always retaining the most recent N runs.
    """
    from ..services.decision_cleanup import cleanup_old_decisions
    return cleanup_old_decisions(db)


# ── Traceability ────────────────────────────────────────────────────────

_SECRET_PATTERNS = {"api_key", "secret", "token", "password", "credential", "auth", "private_key"}


def _redact_config(config: dict) -> dict:
    """Deep-redact any keys that look like secrets."""
    if not isinstance(config, dict):
        return config
    result = {}
    for k, v in config.items():
        if any(pat in k.lower() for pat in _SECRET_PATTERNS):
            result[k] = "[REDACTED]"
        elif isinstance(v, dict):
            result[k] = _redact_config(v)
        elif isinstance(v, list):
            result[k] = [_redact_config(i) if isinstance(i, dict) else i for i in v]
        else:
            result[k] = v
    return result


@router.get("/{run_id}/traceability/{node_id}")
def get_traceability(run_id: str, node_id: str, db: Session = Depends(get_db)):
    """Walk the execution plan edges backwards from a node to build a full provenance chain."""
    from ..models.artifact import ArtifactRecord

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    definition = run.config_snapshot
    if not isinstance(definition, dict):
        raise HTTPException(400, "Run has no execution plan")

    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])
    node_map = {n["id"]: n for n in nodes}

    if node_id not in node_map:
        raise HTTPException(404, f"Node {node_id} not found in run")

    incoming: dict[str, list[dict]] = {}
    for edge in edges:
        tgt = edge.get("target")
        if tgt:
            incoming.setdefault(tgt, []).append({
                "source_id": edge.get("source", ""),
                "source_handle": edge.get("sourceHandle", ""),
                "target_handle": edge.get("targetHandle", ""),
            })

    artifact_records = db.query(ArtifactRecord).filter(ArtifactRecord.run_id == run_id).all()
    artifact_by_node_port: dict[str, dict] = {}
    for ar in artifact_records:
        key = f"{ar.node_id}:{ar.port_id}"
        artifact_by_node_port[key] = {
            "artifact_id": ar.id,
            "data_type": ar.data_type,
            "size_bytes": ar.size_bytes,
            "content_hash": ar.content_hash[:12] if ar.content_hash else None,
            "serializer": ar.serializer,
        }

    SOURCE_BLOCK_TYPES = {
        "data_loader", "csv_loader", "json_loader", "dataset_loader",
        "model_selector", "model_loader", "huggingface_loader",
        "file_reader", "api_source",
    }

    def _is_source_node(n: dict) -> bool:
        bt = n.get("data", {}).get("type", "")
        cat = n.get("data", {}).get("category", "")
        return bt in SOURCE_BLOCK_TYPES or cat in ("data", "external")

    metrics_log = run.metrics_log if isinstance(run.metrics_log, list) else []
    node_started_times: dict[str, float] = {}
    node_completed_times: dict[str, float] = {}
    cached_nodes: set[str] = set()
    for event in metrics_log:
        if not isinstance(event, dict):
            continue
        etype = event.get("type", "")
        enid = event.get("node_id", "")
        ts = event.get("timestamp", 0)
        if etype == "node_started":
            node_started_times[enid] = ts
        elif etype == "node_completed":
            node_completed_times[enid] = ts
        elif etype == "node_cached":
            cached_nodes.add(enid)

    def _get_node_duration(nid: str) -> float | None:
        start = node_started_times.get(nid)
        end = node_completed_times.get(nid)
        if start and end:
            return round(end - start, 3)
        return None

    def _get_cache_decision(nid: str) -> str:
        if nid in cached_nodes:
            return "cache_hit"
        if nid in node_started_times:
            return "executed_fresh"
        return "unknown"

    def _trace_node(nid: str, depth: int = 0, visited: set | None = None) -> dict:
        if visited is None:
            visited = set()
        if nid in visited or depth > 20:
            return {"node_id": nid, "circular": True}
        visited.add(nid)

        node = node_map.get(nid, {})
        node_data = node.get("data", {})
        block_type = node_data.get("type", "")
        label = node_data.get("label", block_type)
        category = node_data.get("category", "")
        config = node_data.get("config", {})
        fingerprint = run.config_fingerprints.get(nid) if isinstance(run.config_fingerprints, dict) else None

        result = {
            "node_id": nid,
            "block_type": block_type,
            "label": label,
            "category": category,
            "resolved_config": _redact_config(config),
            "config_fingerprint": fingerprint,
            "duration_seconds": _get_node_duration(nid),
            "cache_decision": _get_cache_decision(nid),
            "is_source": _is_source_node(node),
        }

        if _is_source_node(node):
            source_info = {}
            for key in ("file_path", "model_name", "model_id", "dataset_name", "dataset_size"):
                if key in config:
                    source_info[key] = config[key]
            if "model_name" in source_info or "model_id" in source_info:
                source_info["model_identifier"] = source_info.pop("model_name", None) or source_info.pop("model_id", "")
            if source_info:
                result["data_source"] = source_info

        node_artifacts = {}
        for ar_key, ar_val in artifact_by_node_port.items():
            ar_nid, ar_port = ar_key.split(":", 1)
            if ar_nid == nid:
                node_artifacts[ar_port] = ar_val
        if node_artifacts:
            result["output_artifacts"] = node_artifacts

        upstream = incoming.get(nid, [])
        if upstream:
            inputs = []
            for edge_info in upstream:
                src_id = edge_info["source_id"]
                src_node = node_map.get(src_id, {})
                input_entry = {
                    "input_port": edge_info["target_handle"],
                    "from_node": src_id,
                    "from_node_label": src_node.get("data", {}).get("label", src_id),
                    "from_port": edge_info["source_handle"],
                }
                artifact_key = f"{src_id}:{edge_info['source_handle']}"
                upstream_artifact = artifact_by_node_port.get(artifact_key)
                if upstream_artifact:
                    input_entry["upstream_artifact"] = upstream_artifact
                input_entry["lineage"] = _trace_node(src_id, depth + 1, visited.copy())
                inputs.append(input_entry)
            result["input_lineage"] = inputs

        return result

    target_node = node_map[node_id]
    target_data = target_node.get("data", {})
    return {
        "run_id": run_id,
        "timestamp": run.started_at.isoformat() if run.started_at else None,
        "metric_source": {
            "node_id": node_id,
            "block_type": target_data.get("type", ""),
            "label": target_data.get("label", ""),
            "output_port": "metrics",
        },
        "provenance": _trace_node(node_id),
    }


# ── Experiment Journal ──────────────────────────────────────────────────

class JournalUpdateRequest(BaseModel):
    user_notes: str | None = None


@router.get("/{run_id}/journal")
def get_journal(run_id: str, db: Session = Depends(get_db)):
    """Get the experiment journal entry for a run."""
    from ..models.experiment_note import ExperimentNote

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    note = db.query(ExperimentNote).filter(ExperimentNote.run_id == run_id).first()
    if not note:
        from ..services.experiment_journal import generate_journal_entry
        note = generate_journal_entry(run_id, db)
        if not note:
            return {"run_id": run_id, "auto_summary": None, "user_notes": None}

    return {
        "id": note.id,
        "run_id": note.run_id,
        "auto_summary": note.auto_summary,
        "user_notes": note.user_notes,
        "created_at": note.created_at.isoformat() if note.created_at else None,
    }


@router.put("/{run_id}/journal")
def update_journal(run_id: str, data: JournalUpdateRequest, db: Session = Depends(get_db)):
    """Update user_notes on a journal entry."""
    from ..models.experiment_note import ExperimentNote

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    note = db.query(ExperimentNote).filter(ExperimentNote.run_id == run_id).first()
    if not note:
        from ..services.experiment_journal import generate_journal_entry
        note = generate_journal_entry(run_id, db)
        if not note:
            raise HTTPException(404, "Could not create journal entry")

    note.user_notes = data.user_notes
    db.commit()

    return {
        "id": note.id,
        "run_id": note.run_id,
        "auto_summary": note.auto_summary,
        "user_notes": note.user_notes,
        "created_at": note.created_at.isoformat() if note.created_at else None,
    }


# ── Pin Best Run ────────────────────────────────────────────────────────

@router.post("/{run_id}/pin-best")
def pin_best_run(run_id: str, db: Session = Depends(get_db)):
    """Pin a run as the best result in its project. Unpins the previous best."""
    from ..models.experiment_note import ExperimentNote

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    if run.project_id:
        db.query(Run).filter(
            Run.project_id == run.project_id,
            Run.best_in_project == True,
            Run.id != run_id,
        ).update({"best_in_project": False})

    run.best_in_project = True
    db.commit()

    top_metrics = {}
    if isinstance(run.metrics, dict):
        top_metrics = dict(list(run.metrics.items())[:5])

    existing_note = db.query(ExperimentNote).filter(ExperimentNote.run_id == run_id).first()
    if existing_note:
        metrics_str = ", ".join(f"{k}={v}" for k, v in top_metrics.items()) if top_metrics else "none recorded"
        pin_text = f"\n\nPinned as best result. Key metrics: {metrics_str}."
        if existing_note.user_notes:
            existing_note.user_notes += pin_text
        else:
            existing_note.user_notes = pin_text.strip()
        db.commit()

    return {"status": "pinned", "run_id": run_id, "best_in_project": True}


@router.post("/{run_id}/unpin-best")
def unpin_best_run(run_id: str, db: Session = Depends(get_db)):
    """Remove the best-run pin from a run."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    run.best_in_project = False
    db.commit()
    return {"status": "unpinned", "run_id": run_id, "best_in_project": False}
