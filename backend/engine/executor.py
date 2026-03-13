"""
Pipeline Execution Engine.

Takes a pipeline graph (nodes + edges), topologically sorts blocks,
and executes them sequentially, passing outputs between blocks.
"""

import json
import re
import traceback
import uuid
import time
import asyncio
import threading
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Path safety: block types must be simple identifiers
SAFE_BLOCK_TYPE = re.compile(r'^[a-zA-Z0-9_]+$')

# Backward-compat aliases for renamed blocks
BLOCK_ALIASES = {
    "model_prompt": "llm_inference",
    "huggingface_dataset_loader": "huggingface_loader",
    "huggingface_model": "huggingface_model_loader",
}

from sqlalchemy.orm import Session

from ..config import ARTIFACTS_DIR, BUILTIN_BLOCKS_DIR, BLOCKS_DIR, CUSTOM_BLOCKS_DIR
from ..models.run import Run, LiveRun
from ..block_sdk.context import BlockContext
from ..routers.events import publish_event
from ..utils.secrets import get_secret

# Cancel events: threading.Event per run_id
_cancel_events: dict[str, threading.Event] = {}


def request_cancel(run_id: str):
    """Signal a running pipeline to cancel. Called from the cancel endpoint."""
    event = _cancel_events.get(run_id)
    if event:
        event.set()


def _topological_sort(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Topological sort of pipeline DAG. Returns node IDs in execution order."""
    in_degree: dict[str, int] = {n["id"]: 0 for n in nodes}
    adj: dict[str, list[str]] = {n["id"]: [] for n in nodes}

    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in adj and tgt in in_degree:
            adj[src].append(tgt)
            in_degree[tgt] += 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    order = []

    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for neighbor in adj.get(nid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return order


def _find_block_module(block_type: str) -> Path | None:
    """Find the run.py for a given block type."""
    # Resolve aliases (e.g. model_prompt → llm_inference)
    block_type = BLOCK_ALIASES.get(block_type, block_type)
    # Validate block_type to prevent path traversal
    if not SAFE_BLOCK_TYPE.match(block_type):
        raise ValueError(f"Invalid block type: {block_type!r}")
    # Search built-in and user blocks (category/block_type/run.py structure)
    for base_dir in [BUILTIN_BLOCKS_DIR, BLOCKS_DIR]:
        if not base_dir.exists():
            continue
        for cat_dir in base_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            block_dir = cat_dir / block_type
            run_py = block_dir / "run.py"
            if run_py.exists():
                return block_dir
    # Search custom blocks (flat structure: custom_blocks/block_type/run.py)
    if CUSTOM_BLOCKS_DIR.exists():
        block_dir = CUSTOM_BLOCKS_DIR / block_type
        run_py = block_dir / "run.py"
        if run_py.exists():
            return block_dir
    return None


def _load_and_run_block(
    block_dir: Path,
    config: dict,
    inputs: dict[str, Any],
    run_dir: str,
    run_id: str,
    node_id: str,
    progress_cb=None,
    message_cb=None,
    metric_cb=None,
) -> dict[str, Any]:
    """Load a block's run.py and execute it."""
    run_py = block_dir / "run.py"
    spec = importlib.util.spec_from_file_location(f"block_{node_id}", str(run_py))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load block module from {run_py}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "run"):
        raise RuntimeError(f"Block {block_dir.name} missing run() function")

    ctx = BlockContext(
        run_dir=run_dir,
        block_dir=str(block_dir),
        config=config,
        inputs=inputs,
        progress_callback=progress_cb,
        message_callback=message_cb,
        metric_callback=metric_cb,
    )

    module.run(ctx)
    return ctx.get_outputs()


def _resolve_secrets(config: dict) -> dict:
    """Replace $secret:<name> references in config values with actual secrets."""
    resolved = {}
    for key, value in config.items():
        if isinstance(value, str) and value.startswith('$secret:'):
            secret_name = value[len('$secret:'):]
            secret_value = get_secret(secret_name)
            if secret_value is None:
                raise ValueError(f"Secret '{secret_name}' not found for config key '{key}'")
            resolved[key] = secret_value
        elif isinstance(value, dict):
            resolved[key] = _resolve_secrets(value)
        else:
            resolved[key] = value
    return resolved


def _check_cancelled(run_id: str) -> bool:
    """Check if a run has been cancelled."""
    event = _cancel_events.get(run_id)
    return event is not None and event.is_set()


def _collect_system_metrics() -> dict | None:
    """Collect CPU/memory/GPU metrics. Returns None if psutil unavailable."""
    try:
        import psutil
    except ImportError:
        return None
    metrics: dict[str, float] = {
        "cpu_pct": psutil.cpu_percent(interval=None),
        "mem_pct": psutil.virtual_memory().percent,
        "mem_gb": round(psutil.virtual_memory().used / (1024 ** 3), 2),
    }
    # GPU memory via nvidia-smi (optional)
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            used, total = result.stdout.strip().split(",")
            metrics["gpu_mem_pct"] = round(float(used) / float(total) * 100, 1)
    except Exception:
        pass
    return metrics


def _safe_commit(db: Session):
    """Commit without raising — log and continue on failure."""
    try:
        db.commit()
    except Exception:
        db.rollback()


async def execute_pipeline(
    pipeline_id: str,
    run_id: str,
    definition: dict,
    db: Session,
):
    """Execute a full pipeline. Called in a background thread."""
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    if not nodes:
        return

    # Register cancel event for this run
    _cancel_events[run_id] = threading.Event()

    run = Run(
        id=run_id,
        pipeline_id=pipeline_id,
        status="running",
        started_at=datetime.now(timezone.utc),
        last_heartbeat=datetime.now(timezone.utc),
        config_snapshot=definition,
    )
    db.add(run)

    live = LiveRun(
        run_id=run_id,
        pipeline_name="",
        total_blocks=len(nodes),
        status="running",
    )
    db.add(live)
    db.commit()

    # Topological sort
    order = _topological_sort(nodes, edges)
    node_map = {n["id"]: n for n in nodes}
    outputs: dict[str, dict[str, Any]] = {}
    all_metrics: dict[str, Any] = {}

    # --- Layer 1: JSONL file failsafe ---
    metrics_dir = ARTIFACTS_DIR / run_id
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics_file = open(metrics_dir / "metrics.jsonl", "a")

    # --- Layer 2: In-memory buffer for SQLite checkpoints ---
    metrics_log_buffer: list[dict] = []
    last_checkpoint_time = time.time()
    CHECKPOINT_INTERVAL = 60  # seconds

    # --- System metrics publisher ---
    system_metrics_stop = threading.Event()

    def _system_metrics_loop():
        while not system_metrics_stop.is_set():
            system_metrics_stop.wait(10)
            if system_metrics_stop.is_set():
                break
            sm = _collect_system_metrics()
            if sm is None:
                continue
            event_data = {"type": "system_metric", "timestamp": time.time(), **sm}
            # Layer 1: JSONL
            try:
                metrics_file.write(json.dumps(event_data) + "\n")
                metrics_file.flush()
            except Exception:
                pass
            # Layer 2: buffer
            metrics_log_buffer.append(event_data)
            # SSE
            publish_event(run_id, "system_metric", event_data)

    system_thread = threading.Thread(target=_system_metrics_loop, daemon=True)
    system_thread.start()

    start_time = time.time()

    try:
        for idx, node_id in enumerate(order):
            node = node_map.get(node_id)
            if not node:
                continue

            # Skip visual grouping nodes
            if node.get("type") == "groupNode":
                continue

            # Check for cancellation before each block
            if _check_cancelled(run_id):
                run.status = "cancelled"
                run.error_message = "Cancelled by user"
                run.finished_at = datetime.now(timezone.utc)
                run.duration_seconds = time.time() - start_time
                run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                live.status = "cancelled"
                db.commit()
                try:
                    publish_event(run_id, "run_cancelled", {
                        "run_id": run_id,
                        "duration": run.duration_seconds,
                        "completed_blocks": idx,
                    })
                except Exception:
                    pass
                return

            node_data = node.get("data", {})
            block_type = node_data.get("type", "")
            config = node_data.get("config", {})

            # Update live run
            live.current_block = node_data.get("label", block_type)
            live.current_block_index = idx
            live.block_progress = 0.0
            live.overall_progress = idx / len(nodes)
            db.commit()

            category = node_data.get("category", "flow")

            started_event = {
                "node_id": node_id,
                "block_type": block_type,
                "category": category,
                "index": idx,
                "total": len(nodes),
            }
            try:
                publish_event(run_id, "node_started", started_event)
            except Exception:
                pass
            metrics_log_buffer.append({"type": "node_started", "timestamp": time.time(), **started_event})
            metrics_file.write(json.dumps({"type": "node_started", "timestamp": time.time(), **started_event}) + "\n")
            metrics_file.flush()

            # Gather inputs from upstream edges
            # When multiple edges connect to the same target handle, collect values into a list
            node_inputs: dict[str, Any] = {}
            _multi_counts: dict[str, int] = {}
            for edge in edges:
                if edge.get("target") == node_id:
                    src_id = edge.get("source", "")
                    src_handle = edge.get("sourceHandle", "")
                    tgt_handle = edge.get("targetHandle", "")
                    if src_id in outputs and src_handle in outputs[src_id]:
                        value = outputs[src_id][src_handle]
                        _multi_counts[tgt_handle] = _multi_counts.get(tgt_handle, 0) + 1
                        if tgt_handle in node_inputs:
                            # Convert to list on second connection
                            if not isinstance(node_inputs[tgt_handle], list) or _multi_counts[tgt_handle] == 2:
                                node_inputs[tgt_handle] = [node_inputs[tgt_handle], value]
                            else:
                                node_inputs[tgt_handle].append(value)
                        else:
                            node_inputs[tgt_handle] = value

            # Find and run block
            block_dir = _find_block_module(block_type)

            # Custom block fallback: if no run.py found, try the baseType
            if block_dir is None:
                base_type = config.get("baseType", "")
                if base_type and SAFE_BLOCK_TYPE.match(base_type):
                    base_type = BLOCK_ALIASES.get(base_type, base_type)
                    block_dir = _find_block_module(base_type)

            run_dir = str(ARTIFACTS_DIR / run_id / node_id)

            # Resolve any $secret: references in config
            config = _resolve_secrets(config)

            if block_dir:
                # Progress commit throttling: commit at most every 2 seconds
                _last_progress_commit = time.time()

                def progress_cb(current, total):
                    nonlocal _last_progress_commit

                    # Check for cancellation in progress callback
                    if _check_cancelled(run_id):
                        raise InterruptedError("Run cancelled by user")

                    progress = current / total if total > 0 else 0
                    live.block_progress = progress
                    live.overall_progress = (idx + progress) / len(nodes)
                    elapsed = time.time() - start_time
                    if progress > 0:
                        live.eta_seconds = (elapsed / ((idx + progress) / len(nodes))) - elapsed

                    now = time.time()
                    if now - _last_progress_commit >= 2.0:
                        db.commit()
                        _last_progress_commit = now

                    try:
                        publish_event(run_id, "node_progress", {
                            "node_id": node_id,
                            "progress": progress,
                            "overall": live.overall_progress,
                            "eta": live.eta_seconds,
                        })
                    except Exception:
                        pass

                def message_cb(msg):
                    try:
                        publish_event(run_id, "node_log", {"node_id": node_id, "message": msg})
                    except Exception:
                        pass

                def metric_cb(name, value, step):
                    all_metrics[f"{block_type}.{name}"] = value
                    metric_event = {
                        "type": "metric",
                        "node_id": node_id,
                        "name": name,
                        "value": value,
                        "category": category,
                        "timestamp": time.time(),
                    }
                    try:
                        publish_event(run_id, "metric", {
                            "node_id": node_id,
                            "name": name,
                            "value": value,
                            "category": category,
                            "timestamp": metric_event["timestamp"],
                        })
                    except Exception:
                        pass
                    # Layer 1: JSONL
                    metrics_file.write(json.dumps(metric_event) + "\n")
                    metrics_file.flush()
                    # Layer 2: buffer
                    metrics_log_buffer.append(metric_event)

                try:
                    node_outputs = _load_and_run_block(
                        block_dir, config, node_inputs, run_dir,
                        run_id, node_id, progress_cb, message_cb, metric_cb,
                    )
                    outputs[node_id] = node_outputs
                except InterruptedError:
                    # Cancellation via progress_cb
                    run.status = "cancelled"
                    run.error_message = "Cancelled by user"
                    run.finished_at = datetime.now(timezone.utc)
                    run.duration_seconds = time.time() - start_time
                    run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                    live.status = "cancelled"
                    db.commit()
                    try:
                        publish_event(run_id, "run_cancelled", {
                            "run_id": run_id,
                            "duration": run.duration_seconds,
                        })
                    except Exception:
                        pass
                    return
                except Exception as e:
                    tb = traceback.format_exc()
                    try:
                        publish_event(run_id, "node_failed", {"node_id": node_id, "error": str(e)})
                    except Exception:
                        pass
                    run.status = "failed"
                    run.error_message = f"Block {block_type} failed: {str(e)}\n\n{tb}"
                    run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                    live.status = "failed"
                    db.commit()
                    # Write traceback to error.log
                    _write_error_log(run_id, tb)
                    return
            else:
                try:
                    publish_event(run_id, "node_failed", {"node_id": node_id, "error": f"Block type '{block_type}' not found"})
                except Exception:
                    pass
                run.status = "failed"
                run.error_message = f"Block type '{block_type}' not found. No run.py available."
                run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                live.status = "failed"
                db.commit()
                return

            # Heartbeat after each block completes
            run.last_heartbeat = datetime.now(timezone.utc)
            # Save partial outputs after each block
            run.outputs_snapshot = _safe_outputs_snapshot(outputs)
            db.commit()

            # Publish outputs so frontend can display them
            safe_outputs = {}
            for k, v in node_outputs.items():
                try:
                    json.dumps(v)
                    safe_outputs[k] = v if not isinstance(v, str) or len(v) < 200 else v[:200] + '...'
                except Exception:
                    safe_outputs[k] = str(v)[:200]
            try:
                publish_event(run_id, "node_output", {"node_id": node_id, "outputs": safe_outputs})
            except Exception:
                pass

            completed_event = {"node_id": node_id, "index": idx}
            try:
                publish_event(run_id, "node_completed", completed_event)
            except Exception:
                pass
            metrics_log_buffer.append({"type": "node_completed", "timestamp": time.time(), **completed_event})
            metrics_file.write(json.dumps({"type": "node_completed", "timestamp": time.time(), **completed_event}) + "\n")
            metrics_file.flush()

            # Layer 2: 60s checkpoint to SQLite
            now = time.time()
            if now - last_checkpoint_time >= CHECKPOINT_INTERVAL:
                run.metrics_log = list(metrics_log_buffer)
                _safe_commit(db)
                last_checkpoint_time = now

        # Pipeline complete
        run.status = "complete"
        run.finished_at = datetime.now(timezone.utc)
        run.duration_seconds = time.time() - start_time
        run.metrics = all_metrics
        run.outputs_snapshot = _safe_outputs_snapshot(outputs)
        run.metrics_log = list(metrics_log_buffer)
        live.status = "complete"
        live.overall_progress = 1.0
        db.commit()

        # Auto-lifecycle: update phase/project counters (never crashes execution)
        try:
            from ..services.project_lifecycle import on_run_completed
            on_run_completed(run_id, db)
        except Exception:
            pass

        try:
            publish_event(run_id, "run_completed", {
                "run_id": run_id,
                "duration": run.duration_seconds,
                "metrics": all_metrics,
            })
        except Exception:
            pass

    except Exception as e:
        tb = traceback.format_exc()
        run.status = "failed"
        run.error_message = f"{str(e)}\n\n{tb}"
        run.outputs_snapshot = _safe_outputs_snapshot(outputs)
        run.metrics_log = list(metrics_log_buffer)
        live.status = "failed"
        db.commit()
        _write_error_log(run_id, tb)

        # Auto-lifecycle: update counts only on failure (never crashes execution)
        try:
            from ..services.project_lifecycle import on_run_failed
            on_run_failed(run_id, db)
        except Exception:
            pass

        try:
            publish_event(run_id, "run_failed", {"run_id": run_id, "error": str(e)})
        except Exception:
            pass
    finally:
        # Clean up cancel event
        _cancel_events.pop(run_id, None)
        # Stop system metrics publisher
        system_metrics_stop.set()
        # Close JSONL file
        try:
            metrics_file.close()
        except Exception:
            pass


def _safe_outputs_snapshot(outputs: dict[str, dict[str, Any]]) -> dict:
    """Create a JSON-safe snapshot of outputs for persistence."""
    snapshot = {}
    for node_id, node_outputs in outputs.items():
        safe = {}
        for k, v in node_outputs.items():
            try:
                json.dumps(v)
                safe[k] = v if not isinstance(v, str) or len(v) < 500 else v[:500] + '...'
            except Exception:
                safe[k] = str(v)[:500]
        snapshot[node_id] = safe
    return snapshot


def _write_error_log(run_id: str, tb: str):
    """Write traceback to {ARTIFACTS_DIR}/{run_id}/error.log."""
    try:
        error_dir = ARTIFACTS_DIR / run_id
        error_dir.mkdir(parents=True, exist_ok=True)
        (error_dir / "error.log").write_text(tb)
    except Exception:
        pass
