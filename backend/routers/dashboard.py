"""
Dashboard router — aggregated experiment views and sequential execution.

Endpoints:
  GET  /api/projects/{id}/dashboard          — full dashboard data
  GET  /api/projects/{id}/comparison-matrix   — structured diff matrix
  POST /api/projects/{id}/sequential-run      — start sequential execution
  GET  /api/projects/{id}/sequences           — list sequences for project
  GET  /api/projects/{id}/events              — SSE stream for project-wide events
"""

import asyncio
import collections
import json
import logging
import threading
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ..database import get_db, SessionLocal
from ..models.project import Project
from ..models.pipeline import Pipeline
from ..models.run import Run
from ..models.pipeline_sequence import PipelineSequence
from ..routers.events import publish_event

router = APIRouter(prefix="/api/projects", tags=["dashboard"])
_logger = logging.getLogger("blueprint.dashboard")

# ── Shutdown signal for cooperative sequence cancellation ─────────────

_sequence_shutdown = threading.Event()
_active_sequence_threads: dict[str, threading.Thread] = {}
_thread_lock = threading.Lock()


def shutdown_sequences(timeout: float = 10.0):
    """Signal all running sequences to stop and wait up to `timeout` seconds.

    Called from _full_shutdown() during server teardown. Sequences check
    _sequence_shutdown between pipeline executions; if set, they mark the
    sequence as 'failed' with a recoverable error message and exit.
    """
    _sequence_shutdown.set()
    with _thread_lock:
        threads = list(_active_sequence_threads.values())
    for t in threads:
        t.join(timeout=timeout / max(len(threads), 1))
    _logger.info("Sequence executor shutdown complete (%d threads)", len(threads))


def recover_orphaned_sequences():
    """Mark any sequences stuck in 'running' or 'pending' as failed.

    Called at server startup (same pattern as _recover_stale_runs) to
    clean up sequences whose background threads were killed by a previous
    crash / SIGKILL.
    """
    db = SessionLocal()
    try:
        orphaned = db.query(PipelineSequence).filter(
            PipelineSequence.status.in_(["running", "pending"])
        ).all()
        if not orphaned:
            return
        for seq in orphaned:
            seq.status = "failed"
            seq.error_message = "Recovered: server restarted while sequence was running"
        db.commit()
        _logger.info("Recovered %d orphaned sequence(s)", len(orphaned))

        # Notify any connected dashboards
        for seq in orphaned:
            publish_project_event(seq.project_id, "sequence_progress", {
                "sequence_id": seq.id,
                "current_index": seq.current_index,
                "total": len(seq.pipeline_ids or []),
                "current_pipeline_name": "",
                "current_status": "failed",
            })
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        _logger.warning("Orphaned sequence recovery failed: %s", exc)
    finally:
        db.close()


# ── Project-level SSE infrastructure ─────────────────────────────────

_project_lock = threading.Lock()
_project_queues: dict[str, list[asyncio.Queue]] = {}

KEEPALIVE_TIMEOUT = 15.0


def publish_project_event(project_id: str, event_type: str, data: dict):
    """Publish an event to all SSE subscribers for a project."""
    with _project_lock:
        queues = list(_project_queues.get(project_id, []))
    event = {"event": event_type, "data": json.dumps(data)}
    for queue in queues:
        try:
            queue.put_nowait(event)
        except Exception:
            pass


# ── Helpers ──────────────────────────────────────────────────────────

def _flatten_dict(d: dict, prefix: str = '') -> dict:
    items = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            items.update(_flatten_dict(v, key))
        else:
            items[key] = v
    return items


def _get_project_pipelines(project_id: str, db: Session) -> list[Pipeline]:
    """Get all pipelines belonging to a project (direct or via experiment phases)."""
    from ..models.experiment_phase import ExperimentPhase

    # Direct project pipelines
    direct = db.query(Pipeline).filter(Pipeline.project_id == project_id).all()

    # Pipelines via experiment phases
    phase_ids = [
        p.id for p in
        db.query(ExperimentPhase.id).filter(ExperimentPhase.project_id == project_id).all()
    ]
    phase_pipelines = []
    if phase_ids:
        phase_pipelines = db.query(Pipeline).filter(
            Pipeline.experiment_phase_id.in_(phase_ids)
        ).all()

    # Deduplicate
    seen = set()
    result = []
    for p in direct + phase_pipelines:
        if p.id not in seen:
            seen.add(p.id)
            result.append(p)
    return result


def _compute_config_diff(config_a: dict, config_b: dict) -> dict:
    """Compute config differences between two flattened config dicts."""
    flat_a = _flatten_dict(config_a) if config_a else {}
    flat_b = _flatten_dict(config_b) if config_b else {}
    all_keys = set(flat_a.keys()) | set(flat_b.keys())
    diff = {}
    for key in sorted(all_keys):
        val_a = flat_a.get(key)
        val_b = flat_b.get(key)
        if val_a != val_b:
            diff[key] = {"old": val_a, "new": val_b}
    return diff


# ── GET /api/projects/{id}/dashboard ─────────────────────────────────

@router.get("/{project_id}/dashboard")
def get_project_dashboard(project_id: str, db: Session = Depends(get_db)):
    """Aggregate dashboard data across all pipelines and runs in a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    pipelines = _get_project_pipelines(project_id, db)
    pipeline_ids = [p.id for p in pipelines]

    # Build source pipeline map (first pipeline by creation order is the "source")
    source_pipeline = pipelines[0] if pipelines else None
    source_config = {}
    if source_pipeline:
        # Use the latest completed run's config as the source config
        source_run = db.query(Run).filter(
            Run.pipeline_id == source_pipeline.id,
            Run.status == "complete",
        ).order_by(Run.started_at.desc()).first()
        if source_run and source_run.config_snapshot:
            source_config = source_run.config_snapshot

    experiments = []
    for pipeline in pipelines:
        runs = db.query(Run).filter(
            Run.pipeline_id == pipeline.id
        ).order_by(Run.started_at.desc()).all()

        # Compute config diff from source
        config_diff = {}
        if pipeline.id != (source_pipeline.id if source_pipeline else None) and source_config:
            # Use the latest run config for diff
            if runs and runs[0].config_snapshot:
                config_diff = _compute_config_diff(source_config, runs[0].config_snapshot)

        run_data = []
        for run in runs:
            duration_ms = int((run.duration_seconds or 0) * 1000)
            run_data.append({
                "run_id": run.id,
                "status": run.status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "duration_ms": duration_ms,
                "metrics": run.metrics or {},
                "config_summary": _flatten_dict(run.config_snapshot) if run.config_snapshot else {},
                "starred": bool(getattr(run, 'starred', False)),
                "tags": [],
            })

        experiments.append({
            "pipeline_id": pipeline.id,
            "pipeline_name": pipeline.name,
            "variant_notes": pipeline.description or "",
            "source_pipeline_id": source_pipeline.id if source_pipeline else None,
            "config_diff_from_source": config_diff,
            "runs": run_data,
        })

    # Active sequences
    sequences = db.query(PipelineSequence).filter(
        PipelineSequence.project_id == project_id,
        PipelineSequence.status.in_(["pending", "running"]),
    ).all()
    active_sequences = []
    for seq in sequences:
        pipeline_names = []
        for pid in (seq.pipeline_ids or []):
            p = db.query(Pipeline).filter(Pipeline.id == pid).first()
            pipeline_names.append(p.name if p else pid)
        active_sequences.append({
            "sequence_id": seq.id,
            "status": seq.status,
            "current_index": seq.current_index,
            "total": len(seq.pipeline_ids or []),
            "current_pipeline_name": pipeline_names[seq.current_index] if seq.current_index < len(pipeline_names) else None,
            "pipeline_names": pipeline_names,
        })

    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "hypothesis": project.hypothesis,
            "status": project.status,
        },
        "experiments": experiments,
        "active_sequences": active_sequences,
    }


# ── GET /api/projects/{id}/comparison-matrix ─────────────────────────

@router.get("/{project_id}/comparison-matrix")
def get_comparison_matrix(
    project_id: str,
    config_keys: str = Query("", description="Comma-separated config keys"),
    metric_keys: str = Query("", description="Comma-separated metric keys"),
    run_ids: str = Query("", description="Comma-separated run IDs to compare"),
    db: Session = Depends(get_db),
):
    """Return a structured comparison matrix optimized for table rendering."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    # Get runs to compare
    if run_ids:
        ids = [r.strip() for r in run_ids.split(",") if r.strip()]
        runs = db.query(Run).filter(Run.id.in_(ids)).order_by(Run.started_at).all()
    else:
        # Default: all completed runs in the project
        pipelines = _get_project_pipelines(project_id, db)
        pipeline_ids = [p.id for p in pipelines]
        runs = db.query(Run).filter(
            Run.pipeline_id.in_(pipeline_ids),
            Run.status == "complete",
        ).order_by(Run.started_at).all() if pipeline_ids else []

    if not runs:
        return {"columns": [], "diff_cells": [], "row_keys": [], "sections": {"config": [], "metrics": []}}

    # Build pipeline name lookup
    pipeline_names = {}
    for run in runs:
        if run.pipeline_id not in pipeline_names:
            p = db.query(Pipeline).filter(Pipeline.id == run.pipeline_id).first()
            pipeline_names[run.pipeline_id] = p.name if p else run.pipeline_id

    # Collect all config and metric keys from runs
    all_config_keys: set[str] = set()
    all_metric_keys: set[str] = set()
    run_configs = []
    run_metrics = []

    for run in runs:
        flat_config = _flatten_dict(run.config_snapshot) if run.config_snapshot else {}
        metrics = run.metrics if isinstance(run.metrics, dict) else {}
        run_configs.append(flat_config)
        run_metrics.append(metrics)
        all_config_keys.update(flat_config.keys())
        all_metric_keys.update(metrics.keys())

    # Filter to requested keys (or auto-detect diffs)
    req_config = [k.strip() for k in config_keys.split(",") if k.strip()] if config_keys else None
    req_metric = [k.strip() for k in metric_keys.split(",") if k.strip()] if metric_keys else None

    if req_config:
        selected_config_keys = [k for k in req_config if k in all_config_keys]
    else:
        # Auto-detect: show keys where values differ
        selected_config_keys = []
        for key in sorted(all_config_keys):
            values = {str(rc.get(key)) for rc in run_configs}
            if len(values) > 1:
                selected_config_keys.append(key)

    if req_metric:
        selected_metric_keys = [k for k in req_metric if k in all_metric_keys]
    else:
        selected_metric_keys = sorted(all_metric_keys)

    # Build columns (one per run)
    columns = []
    for i, run in enumerate(runs):
        values = {}
        for key in selected_config_keys:
            values[key] = run_configs[i].get(key)
        for key in selected_metric_keys:
            values[key] = run_metrics[i].get(key)
        columns.append({
            "experiment_name": pipeline_names.get(run.pipeline_id, ""),
            "run_id": run.id,
            "values": values,
        })

    # Build diff_cells: compare each cell against the first column
    diff_cells = []
    all_row_keys = selected_config_keys + selected_metric_keys
    for row_key in all_row_keys:
        if not columns:
            continue
        ref_value = columns[0]["values"].get(row_key)
        for col_idx in range(1, len(columns)):
            col_value = columns[col_idx]["values"].get(row_key)
            if str(col_value) != str(ref_value):
                diff_cells.append({
                    "row_key": row_key,
                    "col_idx": col_idx,
                    "is_different": True,
                })

    return {
        "columns": columns,
        "diff_cells": diff_cells,
        "row_keys": all_row_keys,
        "sections": {
            "config": selected_config_keys,
            "metrics": selected_metric_keys,
        },
        "available_config_keys": sorted(all_config_keys),
        "available_metric_keys": sorted(all_metric_keys),
    }


# ── POST /api/projects/{id}/sequential-run ───────────────────────────

class SequentialRunRequest(BaseModel):
    pipeline_ids: list[str] = Field(..., min_length=2, max_length=5)


@router.post("/{project_id}/sequential-run")
def start_sequential_run(
    project_id: str,
    body: SequentialRunRequest,
    db: Session = Depends(get_db),
):
    """Start a sequential pipeline execution — pipelines run one after another."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    # Validate all pipeline IDs exist and belong to this project
    project_pipelines = _get_project_pipelines(project_id, db)
    project_pipeline_ids = {p.id for p in project_pipelines}
    for pid in body.pipeline_ids:
        if pid not in project_pipeline_ids:
            raise HTTPException(400, f"Pipeline {pid} not found in project")

    # Check no other sequence is running for this project
    active = db.query(PipelineSequence).filter(
        PipelineSequence.project_id == project_id,
        PipelineSequence.status.in_(["pending", "running"]),
    ).first()
    if active:
        raise HTTPException(409, "A sequential run is already active for this project")

    sequence = PipelineSequence(
        id=str(uuid.uuid4()),
        project_id=project_id,
        pipeline_ids=body.pipeline_ids,
        status="running",
        current_index=0,
    )
    db.add(sequence)
    db.commit()
    db.refresh(sequence)

    # Start the first pipeline in a background thread (tracked for shutdown)
    _sequence_shutdown.clear()  # Ensure fresh start
    thread = threading.Thread(
        target=_run_sequence,
        args=(sequence.id,),
        daemon=True,
        name=f"seq-{sequence.id[:8]}",
    )
    with _thread_lock:
        _active_sequence_threads[sequence.id] = thread
    thread.start()

    return {
        "sequence_id": sequence.id,
        "status": "running",
        "pipeline_ids": body.pipeline_ids,
        "total": len(body.pipeline_ids),
    }


def _run_sequence(sequence_id: str):
    """Background thread: execute pipelines sequentially.

    Checks _sequence_shutdown between each pipeline execution so the
    server can shut down cleanly without leaving orphaned sequences.
    On shutdown signal, the current pipeline finishes (it's in-process),
    but the next pipeline is not started and the sequence is marked failed
    with a recoverable message.
    """
    from ..engine.executor import execute_pipeline
    from ..services.registry import get_global_registry

    db = SessionLocal()
    try:
        sequence = db.query(PipelineSequence).filter(PipelineSequence.id == sequence_id).first()
        if not sequence:
            return

        pipeline_ids = sequence.pipeline_ids or []
        total = len(pipeline_ids)

        for idx, pipeline_id in enumerate(pipeline_ids):
            # ── Check shutdown signal before starting next pipeline ──
            if _sequence_shutdown.is_set():
                _logger.info("Sequence %s interrupted by shutdown at index %d", sequence_id[:8], idx)
                sequence.status = "failed"
                sequence.error_message = "Interrupted: server shutdown while sequence was running"
                db.commit()
                _emit_sequence_event(sequence, pipeline_name="", total=total)
                return

            # Update current index
            sequence.current_index = idx
            sequence.status = "running"
            db.commit()

            pipeline = db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()
            if not pipeline:
                sequence.status = "failed"
                sequence.error_message = f"Pipeline {pipeline_id} not found"
                db.commit()
                _emit_sequence_event(sequence, pipeline_name="unknown", total=total)
                return

            pipeline_name = pipeline.name
            _emit_sequence_event(sequence, pipeline_name=pipeline_name, total=total)

            # Create run record
            run_id = str(uuid.uuid4())
            run = Run(
                id=run_id,
                pipeline_id=pipeline_id,
                project_id=sequence.project_id,
                status="pending",
            )
            db.add(run)
            db.commit()

            sequence.current_run_id = run_id
            db.commit()

            # Execute the pipeline
            try:
                definition = pipeline.definition or {}
                nodes = definition.get("nodes", [])
                edges = definition.get("edges", [])

                registry = get_global_registry()
                execute_pipeline(
                    run_id=run_id,
                    nodes=nodes,
                    edges=edges,
                    pipeline_id=pipeline_id,
                    registry=registry,
                )

                # Refresh run status from DB after execution
                db.refresh(run)
                if run.status != "complete":
                    sequence.status = "failed"
                    sequence.error_message = f"Pipeline '{pipeline_name}' did not complete (status: {run.status})"
                    db.commit()
                    _emit_sequence_event(sequence, pipeline_name=pipeline_name, total=total)
                    publish_project_event(sequence.project_id, "run_completed", {
                        "run_id": run_id,
                        "pipeline_id": pipeline_id,
                        "status": run.status,
                    })
                    return

                # Publish project-level event for dashboard refresh
                publish_project_event(sequence.project_id, "run_completed", {
                    "run_id": run_id,
                    "pipeline_id": pipeline_id,
                    "status": "complete",
                })

            except Exception as exc:
                _logger.error("Sequential run failed on pipeline %s: %s", pipeline_id, exc)
                sequence.status = "failed"
                sequence.error_message = str(exc)
                db.commit()
                _emit_sequence_event(sequence, pipeline_name=pipeline_name, total=total)
                return

        # All pipelines completed
        sequence.status = "completed"
        sequence.current_index = total
        db.commit()
        _emit_sequence_event(sequence, pipeline_name="", total=total)

    except Exception as exc:
        _logger.error("Sequential run error: %s", exc)
        try:
            sequence = db.query(PipelineSequence).filter(PipelineSequence.id == sequence_id).first()
            if sequence:
                sequence.status = "failed"
                sequence.error_message = str(exc)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
        # Deregister from active threads
        with _thread_lock:
            _active_sequence_threads.pop(sequence_id, None)


def _emit_sequence_event(sequence: PipelineSequence, pipeline_name: str, total: int):
    """Emit SSE event for sequence progress."""
    publish_project_event(sequence.project_id, "sequence_progress", {
        "sequence_id": sequence.id,
        "current_index": sequence.current_index,
        "total": total,
        "current_pipeline_name": pipeline_name,
        "current_status": sequence.status,
    })


# ── GET /api/projects/{id}/sequences ─────────────────────────────────

@router.get("/{project_id}/sequences")
def list_sequences(project_id: str, db: Session = Depends(get_db)):
    """List all pipeline sequences for a project."""
    sequences = db.query(PipelineSequence).filter(
        PipelineSequence.project_id == project_id
    ).order_by(PipelineSequence.created_at.desc()).all()

    result = []
    for seq in sequences:
        pipeline_names = []
        for pid in (seq.pipeline_ids or []):
            p = db.query(Pipeline).filter(Pipeline.id == pid).first()
            pipeline_names.append(p.name if p else pid)
        result.append({
            "sequence_id": seq.id,
            "status": seq.status,
            "current_index": seq.current_index,
            "total": len(seq.pipeline_ids or []),
            "pipeline_names": pipeline_names,
            "error_message": seq.error_message,
            "created_at": seq.created_at.isoformat() if seq.created_at else None,
        })
    return result


# ── GET /api/projects/{id}/events — project-level SSE ────────────────

@router.get("/{project_id}/events")
async def stream_project_events(project_id: str):
    """SSE endpoint for live project-wide events (run completions, sequence progress)."""
    queue: asyncio.Queue = asyncio.Queue()

    with _project_lock:
        if project_id not in _project_queues:
            _project_queues[project_id] = []
        _project_queues[project_id].append(queue)

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_TIMEOUT)
                    yield event
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
        except asyncio.CancelledError:
            pass
        finally:
            with _project_lock:
                queues = _project_queues.get(project_id)
                if queues is not None:
                    try:
                        queues.remove(queue)
                    except ValueError:
                        pass
                    if not queues:
                        del _project_queues[project_id]

    return EventSourceResponse(event_generator())
