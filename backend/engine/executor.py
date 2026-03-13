"""
Pipeline Execution Engine.

Takes a pipeline graph (nodes + edges), topologically sorts blocks,
and executes them sequentially, passing outputs between blocks.
"""

import re
import uuid
import time
import asyncio
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

    start_time = time.time()

    try:
        for idx, node_id in enumerate(order):
            node = node_map.get(node_id)
            if not node:
                continue
            
            # Skip visual grouping nodes
            if node.get("type") == "groupNode":
                continue

            node_data = node.get("data", {})
            block_type = node_data.get("type", "")
            config = node_data.get("config", {})

            # Update live run
            live.current_block = node_data.get("label", block_type)
            live.current_block_index = idx
            live.block_progress = 0.0
            live.overall_progress = idx / len(nodes)
            db.commit()

            publish_event(run_id, "node_started", {
                "node_id": node_id,
                "block_type": block_type,
                "index": idx,
                "total": len(nodes),
            })

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
                def progress_cb(current, total):
                    progress = current / total if total > 0 else 0
                    live.block_progress = progress
                    live.overall_progress = (idx + progress) / len(nodes)
                    elapsed = time.time() - start_time
                    if progress > 0:
                        live.eta_seconds = (elapsed / ((idx + progress) / len(nodes))) - elapsed
                    db.commit()
                    publish_event(run_id, "node_progress", {
                        "node_id": node_id,
                        "progress": progress,
                        "overall": live.overall_progress,
                        "eta": live.eta_seconds,
                    })

                def message_cb(msg):
                    publish_event(run_id, "node_log", {"node_id": node_id, "message": msg})

                def metric_cb(name, value, step):
                    all_metrics[f"{block_type}.{name}"] = value
                    publish_event(run_id, "metric", {"node_id": node_id, "name": name, "value": value})

                try:
                    node_outputs = _load_and_run_block(
                        block_dir, config, node_inputs, run_dir,
                        run_id, node_id, progress_cb, message_cb, metric_cb,
                    )
                    outputs[node_id] = node_outputs
                except Exception as e:
                    publish_event(run_id, "node_failed", {"node_id": node_id, "error": str(e)})
                    run.status = "failed"
                    run.error_message = f"Block {block_type} failed: {str(e)}"
                    live.status = "failed"
                    db.commit()
                    return
            else:
                publish_event(run_id, "node_failed", {"node_id": node_id, "error": f"Block type '{block_type}' not found"})
                run.status = "failed"
                run.error_message = f"Block type '{block_type}' not found. No run.py available."
                live.status = "failed"
                db.commit()
                return

            # Heartbeat after each block completes
            run.last_heartbeat = datetime.now(timezone.utc)
            db.commit()

            # Publish outputs so frontend can display them
            safe_outputs = {}
            for k, v in node_outputs.items():
                try:
                    import json
                    json.dumps(v)
                    safe_outputs[k] = v if not isinstance(v, str) or len(v) < 200 else v[:200] + '...'
                except Exception:
                    safe_outputs[k] = str(v)[:200]
            publish_event(run_id, "node_output", {"node_id": node_id, "outputs": safe_outputs})
            publish_event(run_id, "node_completed", {"node_id": node_id, "index": idx})

        # Pipeline complete
        run.status = "complete"
        run.finished_at = datetime.now(timezone.utc)
        run.duration_seconds = time.time() - start_time
        run.metrics = all_metrics
        live.status = "complete"
        live.overall_progress = 1.0
        db.commit()

        # Auto-lifecycle: update phase/project counters (never crashes execution)
        try:
            from ..services.project_lifecycle import on_run_completed
            on_run_completed(run_id, db)
        except Exception:
            pass

        publish_event(run_id, "run_completed", {
            "run_id": run_id,
            "duration": run.duration_seconds,
            "metrics": all_metrics,
        })

    except Exception as e:
        run.status = "failed"
        run.error_message = str(e)
        live.status = "failed"
        db.commit()

        # Auto-lifecycle: update counts only on failure (never crashes execution)
        try:
            from ..services.project_lifecycle import on_run_failed
            on_run_failed(run_id, db)
        except Exception:
            pass

        publish_event(run_id, "run_failed", {"run_id": run_id, "error": str(e)})
