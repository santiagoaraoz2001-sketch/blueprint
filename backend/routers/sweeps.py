import copy
import os
import uuid
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from ..models.pipeline import Pipeline
from ..models.run import Run
from ..models.sweep import Sweep
from ..engine.sweep import (
    generate_grid, generate_random, SweepManager,
    MAX_GRID_COMBINATIONS, MAX_RANDOM_SAMPLES,
)
from ..engine.executor import execute_pipeline
from ..routers.events import publish_event

router = APIRouter(prefix="/api/sweeps", tags=["sweeps"])
_logger = logging.getLogger("blueprint.sweeps")

# Configurable parallelism via env var; capped at 8 to protect resources
_MAX_SWEEP_WORKERS = min(int(os.environ.get("BLUEPRINT_SWEEP_WORKERS", "4")), 8)
_sweep_executor = ThreadPoolExecutor(
    max_workers=_MAX_SWEEP_WORKERS, thread_name_prefix="sweep-run",
)

# In-memory sweep managers for live tracking
_active_sweeps: dict[str, SweepManager] = {}

# Lock for serialising DB writes to sweep.results (SQLite JSON column
# is not atomic — concurrent read-modify-write from worker threads will
# lose updates without serialisation).
_results_lock = threading.Lock()


# ── Request Models ──────────────────────────────────────────────────

class CreateSweepRequest(BaseModel):
    pipeline_id: str
    target_node_id: str
    metric_name: str = Field(default="eval_loss", min_length=1, max_length=128)
    search_type: Literal["grid", "random"] = "grid"
    ranges: dict[str, Any] = Field(...)
    n_samples: int = Field(default=10, ge=1, le=MAX_RANDOM_SAMPLES)

    @field_validator("ranges")
    @classmethod
    def ranges_not_empty(cls, v: dict) -> dict:
        if not v:
            raise ValueError("ranges must contain at least one parameter")
        return v


# ── Lifecycle ───────────────────────────────────────────────────────

def shutdown_sweep_executor():
    """Gracefully shut down the sweep executor pool.

    cancel_futures=True prevents queued sweeps from starting during shutdown.
    """
    _logger.info("Shutting down sweep executor pool...")
    _sweep_executor.shutdown(wait=True, cancel_futures=True)
    _logger.info("Sweep executor pool shut down.")


# ── Helpers ─────────────────────────────────────────────────────────

def _apply_config_to_definition(
    definition: dict, target_node_id: str, config: dict,
) -> dict:
    """Clone a pipeline definition and apply config overrides to the target node."""
    new_def = copy.deepcopy(definition)
    for node in new_def.get("nodes", []):
        if node["id"] == target_node_id:
            if "data" not in node:
                node["data"] = {}
            if "config" not in node["data"]:
                node["data"]["config"] = {}
            node["data"]["config"].update(config)
            break
    return new_def


def _persist_sweep_result(
    sweep_id: str,
    run_id: str,
    config: dict,
    config_index: int,
    metric_value: float | None,
    error: str | None = None,
) -> tuple[int, int, str]:
    """Atomically append a result to the sweep record in the DB.

    Returns (completed_count, total_count, new_status).
    Uses a module-level lock to prevent lost-update race conditions
    when multiple executor threads finish concurrently.
    """
    session = SessionLocal()
    try:
        with _results_lock:
            sweep = session.query(Sweep).filter(Sweep.id == sweep_id).first()
            if not sweep:
                return (0, 0, "unknown")

            results = list(sweep.results or [])
            entry: dict[str, Any] = {
                "config": config,
                "metric": metric_value,
                "run_id": run_id,
                "config_index": config_index,
            }
            if error:
                entry["error"] = error
            results.append(entry)
            sweep.results = results

            total = len(sweep.configs or [])
            completed = len(results)
            new_status = sweep.status
            if completed >= total:
                sweep.status = "complete"
                new_status = "complete"

            session.commit()
            return (completed, total, new_status)
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        raise
    finally:
        session.close()


def _execute_sweep_run(
    sweep_id: str,
    pipeline_id: str,
    run_id: str,
    definition: dict,
    config: dict,
    config_index: int,
    metric_name: str,
):
    """Execute a single sweep run in a background thread."""
    session = SessionLocal()
    error_msg: str | None = None
    metric_value: float | None = None
    loop = None
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        loop.run_until_complete(
            execute_pipeline(pipeline_id, run_id, definition, session)
        )

        # Extract the metric from the completed run
        run = session.query(Run).filter(Run.id == run_id).first()
        if run and run.metrics:
            metric_value = run.metrics.get(metric_name)
    except Exception as e:
        _logger.error("Sweep run %s failed: %s", run_id, e)
        error_msg = str(e)
    finally:
        if loop is not None:
            loop.close()
        session.close()

    # Persist result (thread-safe)
    try:
        completed, total, new_status = _persist_sweep_result(
            sweep_id, run_id, config, config_index, metric_value, error_msg,
        )
    except Exception as e:
        _logger.error("Failed to persist sweep result for run %s: %s", run_id, e)
        completed, total, new_status = 0, 0, "unknown"

    # Update in-memory manager
    mgr = _active_sweeps.get(sweep_id)
    if mgr:
        mgr.record_result(run_id, config, metric_value)

    # Publish SSE event for live frontend updates (crash-safe)
    event_type = "sweep_run_failed" if error_msg else "sweep_run_completed"
    try:
        publish_event(sweep_id, event_type, {
            "sweep_id": sweep_id,
            "run_id": run_id,
            "config": config,
            "config_index": config_index,
            "metric": metric_value,
            "completed": completed,
            "total": total,
            **({"error": error_msg} if error_msg else {}),
        })
    except Exception:
        pass

    if new_status == "complete":
        # Clean up in-memory manager
        _active_sweeps.pop(sweep_id, None)
        try:
            publish_event(sweep_id, "sweep_completed", {
                "sweep_id": sweep_id,
                "total": total,
            })
        except Exception:
            pass


# ── Endpoints ───────────────────────────────────────────────────────

@router.post("/create")
def create_sweep(body: CreateSweepRequest, db: Session = Depends(get_db)):
    """Create a new parameter sweep. Generates configs but does not start execution."""
    pipeline = db.query(Pipeline).filter(Pipeline.id == body.pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")

    definition = pipeline.definition or {}
    nodes = definition.get("nodes", [])
    node_ids = {n["id"] for n in nodes}

    if body.target_node_id not in node_ids:
        raise HTTPException(
            400,
            f"target_node_id '{body.target_node_id}' not found in pipeline",
        )

    # Generate configs — both functions raise ValueError on invalid input
    try:
        if body.search_type == "grid":
            configs = generate_grid(body.ranges)
        else:
            configs = generate_random(body.ranges, body.n_samples)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if not configs:
        raise HTTPException(400, "No configurations generated from provided ranges")

    sweep_id = str(uuid.uuid4())

    sweep = Sweep(
        id=sweep_id,
        pipeline_id=body.pipeline_id,
        target_node_id=body.target_node_id,
        metric_name=body.metric_name,
        search_type=body.search_type,
        configs=configs,
        run_ids=[],
        results=[],
        status="pending",
    )
    db.add(sweep)
    db.commit()
    db.refresh(sweep)

    return {
        "sweep_id": sweep_id,
        "pipeline_id": body.pipeline_id,
        "search_type": body.search_type,
        "num_configs": len(configs),
        "configs": configs,
        "status": "pending",
    }


@router.post("/{sweep_id}/start")
def start_sweep(sweep_id: str, db: Session = Depends(get_db)):
    """Execute all sweep runs. Each config becomes a separate pipeline execution."""
    sweep = db.query(Sweep).filter(Sweep.id == sweep_id).first()
    if not sweep:
        raise HTTPException(404, "Sweep not found")
    if sweep.status == "running":
        raise HTTPException(400, "Sweep is already running")
    if sweep.status == "complete":
        raise HTTPException(400, "Sweep is already complete")

    pipeline = db.query(Pipeline).filter(Pipeline.id == sweep.pipeline_id).first()
    if not pipeline:
        raise HTTPException(404, "Associated pipeline not found")

    definition = pipeline.definition or {}
    configs = sweep.configs or []
    if not configs:
        raise HTTPException(400, "Sweep has no configurations")

    # Generate a run ID for each config
    run_ids = [str(uuid.uuid4()) for _ in configs]

    sweep.run_ids = run_ids
    sweep.status = "running"
    sweep.results = []
    db.commit()

    # Create in-memory manager for live tracking
    mgr = SweepManager(
        sweep_id=sweep_id,
        pipeline_id=sweep.pipeline_id,
        configs=configs,
        target_node_id=sweep.target_node_id,
        metric_name=sweep.metric_name,
    )
    mgr.run_ids = run_ids
    _active_sweeps[sweep_id] = mgr

    # Submit runs to thread pool (ThreadPoolExecutor handles queueing
    # when there are more configs than workers)
    for i, config in enumerate(configs):
        modified_def = _apply_config_to_definition(
            definition, sweep.target_node_id, config,
        )
        try:
            _sweep_executor.submit(
                _execute_sweep_run,
                sweep_id,
                sweep.pipeline_id,
                run_ids[i],
                modified_def,
                config,
                i,
                sweep.metric_name,
            )
        except RuntimeError:
            raise HTTPException(503, "Sweep executor is shutting down")

    return {
        "sweep_id": sweep_id,
        "status": "running",
        "num_runs": len(run_ids),
        "run_ids": run_ids,
    }


@router.get("/{sweep_id}/results")
def get_sweep_results(
    sweep_id: str,
    x_param: str | None = Query(None, description="X-axis parameter for heatmap"),
    y_param: str | None = Query(None, description="Y-axis parameter for heatmap"),
    db: Session = Depends(get_db),
):
    """Get current results, optionally formatted as heatmap data."""
    sweep = db.query(Sweep).filter(Sweep.id == sweep_id).first()
    if not sweep:
        raise HTTPException(404, "Sweep not found")

    results = sweep.results or []

    # Heatmap mode: requires both axes
    if x_param and y_param:
        mgr = _active_sweeps.get(sweep_id)
        if not mgr:
            # Reconstruct manager from DB for completed sweeps
            mgr = SweepManager(
                sweep_id=sweep_id,
                pipeline_id=sweep.pipeline_id,
                configs=sweep.configs or [],
                target_node_id=sweep.target_node_id,
                metric_name=sweep.metric_name,
            )
            mgr.results = results
        return mgr.to_heatmap_data(x_param, y_param)

    # Full results mode
    scored = [r for r in results if r.get("metric") is not None]
    best = min(scored, key=lambda r: r["metric"]) if scored else None

    return {
        "sweep_id": sweep_id,
        "status": sweep.status,
        "results": results,
        "best": best,
        "configs": sweep.configs,
        "metric_name": sweep.metric_name,
    }


@router.get("/{sweep_id}/status")
def get_sweep_status(sweep_id: str, db: Session = Depends(get_db)):
    """Progress summary: how many runs complete, running, pending."""
    sweep = db.query(Sweep).filter(Sweep.id == sweep_id).first()
    if not sweep:
        raise HTTPException(404, "Sweep not found")

    total = len(sweep.configs or [])
    completed = len(sweep.results or [])

    return {
        "sweep_id": sweep_id,
        "status": sweep.status,
        "total": total,
        "completed": completed,
        "pending": total - completed,
        "percent": round(completed / total * 100, 1) if total > 0 else 0,
        "run_ids": sweep.run_ids or [],
        "metric_name": sweep.metric_name,
    }


@router.get("")
def list_sweeps(
    pipeline_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """List all sweeps, optionally filtered by pipeline."""
    query = db.query(Sweep).order_by(Sweep.created_at.desc())
    if pipeline_id:
        query = query.filter(Sweep.pipeline_id == pipeline_id)
    sweeps = query.all()

    return [
        {
            "sweep_id": s.id,
            "pipeline_id": s.pipeline_id,
            "target_node_id": s.target_node_id,
            "metric_name": s.metric_name,
            "search_type": s.search_type,
            "status": s.status,
            "num_configs": len(s.configs or []),
            "num_completed": len(s.results or []),
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in sweeps
    ]
