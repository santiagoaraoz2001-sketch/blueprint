"""
Partial Executor — re-run a pipeline from a specific node.

Reuses cached outputs from a previous run for all nodes upstream of the
target node.  Only executes the target node and its downstream dependencies.
"""

import collections
import json
import time
import traceback
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..config import ARTIFACTS_DIR
from ..models.run import Run, LiveRun
from ..routers.events import publish_event
from ..utils.redact import scrub_traceback
from .executor import (
    _topological_sort,
    _detect_loops,
    _find_block_module,
    _load_and_run_block,
    _resolve_secrets,
    _check_cancelled,
    _check_memory_pressure,
    _safe_outputs_snapshot,
    _safe_commit,
    _write_error_log,
    _collect_system_metrics,
    _cancel_events,
    _cancel_lock,
    BLOCK_ALIASES,
    CONFIG_MIGRATIONS,
    SAFE_BLOCK_TYPE,
    MEMORY_PRESSURE_THRESHOLD,
)
from .config_resolver import resolve_configs
from .block_registry import resolve_output_handle
from .composite import CompositeBlockContext
from .schema_validator import load_block_schema
from .graph_utils import is_cache_valid
from .artifact_registry import register_block_artifacts, _sha256_file
from ..models.artifact import Artifact


def _get_downstream_nodes(start_id: str, nodes: list, edges: list) -> set[str]:
    """BFS from start_id to find all downstream nodes (inclusive)."""
    adj: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    for e in edges:
        src, tgt = e.get("source", ""), e.get("target", "")
        if src in adj:
            adj[src].append(tgt)

    visited: set[str] = set()
    queue: collections.deque[str] = collections.deque([start_id])
    while queue:
        nid = queue.popleft()
        if nid in visited:
            continue
        visited.add(nid)
        queue.extend(adj.get(nid, []))
    return visited


def _validate_upstream_definitions(
    current_nodes: dict[str, dict],
    source_nodes: dict[str, dict],
    upstream_ids: set[str],
) -> list[str]:
    """Check that upstream node definitions match between current and source.

    Skips visual groupNode entries (they carry no block logic).
    Returns a list of mismatched node IDs (empty = all good).
    """
    mismatched = []
    for nid in sorted(upstream_ids):  # sorted for deterministic error messages
        cur = current_nodes.get(nid)
        src = source_nodes.get(nid)
        if cur is None or src is None:
            mismatched.append(nid)
            continue
        # Skip visual grouping nodes — they have no block type
        if cur.get("type") == "groupNode":
            continue
        # Compare block type
        cur_data = cur.get("data", {})
        src_data = src.get("data", {})
        if cur_data.get("type") != src_data.get("type"):
            mismatched.append(nid)
    return mismatched


# Files larger than this skip hash verification (50 MB) — existence + size is
# sufficient for large artifacts to keep partial-rerun startup fast.
_VERIFY_HASH_MAX_SIZE = 50 * 1024 * 1024


def _verify_node_artifacts(
    source_run_id: str,
    node_id: str,
    db: Session,
) -> tuple[bool, str]:
    """Verify integrity of artifacts for a cached node.

    Two-tier check:
      1. Fast path (all files): existence + size match via os.stat (O(1) per file)
      2. Slow path (files < 50 MB with a stored hash): SHA-256 verification

    Returns (ok, reason). If no artifacts exist for the node, returns True
    (some blocks produce in-memory outputs only).
    """
    artifacts = (
        db.query(Artifact)
        .filter(Artifact.run_id == source_run_id, Artifact.node_id == node_id)
        .all()
    )
    if not artifacts:
        return True, ""

    import os
    for art in artifacts:
        # Fast path: existence check
        try:
            stat = os.stat(art.file_path)
        except OSError:
            return False, f"Artifact file missing: {art.name} ({art.file_path})"

        # Fast path: size mismatch catches truncated or replaced files
        if art.size_bytes and stat.st_size != art.size_bytes:
            return False, (
                f"Artifact size mismatch for {art.name}: "
                f"expected {art.size_bytes} bytes, got {stat.st_size} bytes"
            )

        # Slow path: hash only for small files (< 50 MB) that have a stored hash
        if art.hash and stat.st_size <= _VERIFY_HASH_MAX_SIZE:
            current_hash = _sha256_file(art.file_path)
            if current_hash and current_hash != art.hash:
                return False, (
                    f"Artifact hash mismatch for {art.name}: "
                    f"expected {art.hash[:12]}…, got {current_hash[:12]}…"
                )
    return True, ""


async def execute_partial_pipeline(
    pipeline_id: str,
    run_id: str,
    source_run_id: str,
    start_node_id: str,
    definition: dict,
    config_overrides: dict[str, dict],
    db: Session,
    *,
    project_id: str | None = None,
):
    """
    Execute a pipeline starting from a specific node.

    1. Create Run record immediately (so the client can always query status)
    2. Load outputs_snapshot from source_run
    3. Topologically sort the pipeline
    4. For nodes BEFORE start_node_id: use cached outputs
    5. For start_node_id and downstream: execute normally
    6. Apply config_overrides to affected nodes
    """
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])

    if not nodes:
        return

    # --- Register cancel event ---
    with _cancel_lock:
        _cancel_events[run_id] = threading.Event()

    # --- Create Run and LiveRun records FIRST ---
    # This ensures the client can always query run status, even if
    # validation fails below (the outer except marks it as "failed").
    run = Run(
        id=run_id,
        pipeline_id=pipeline_id,
        project_id=project_id,
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

    outputs: dict[str, dict[str, Any]] = {}
    all_metrics: dict[str, Any] = {}
    all_fingerprints: dict[str, dict] = {}

    # --- Layer 1: JSONL file failsafe ---
    metrics_dir = ARTIFACTS_DIR / run_id
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics_file = open(metrics_dir / "metrics.jsonl", "a")  # noqa: SIM115

    # --- Layer 2: In-memory buffer for SQLite checkpoints ---
    metrics_log_buffer: list[dict] = []
    last_checkpoint_time = time.time()
    CHECKPOINT_INTERVAL = 60

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
            try:
                metrics_file.write(json.dumps(event_data) + "\n")
                metrics_file.flush()
            except Exception:
                pass
            metrics_log_buffer.append(event_data)
            publish_event(run_id, "system_metric", event_data)

    system_thread = threading.Thread(target=_system_metrics_loop, daemon=True)
    system_thread.start()

    start_time = time.time()

    try:
        # --- Validate source run (defense-in-depth; endpoint also checks) ---
        source_run = db.query(Run).filter(Run.id == source_run_id).first()
        if not source_run:
            raise ValueError(f"Source run '{source_run_id}' not found")
        if source_run.status != "complete":
            raise ValueError(
                f"Source run has status '{source_run.status}', expected 'complete'"
            )
        if not source_run.outputs_snapshot:
            raise ValueError("Source run has no cached outputs")

        cached_outputs = source_run.outputs_snapshot

        # --- Validate start node exists ---
        node_map = {n["id"]: n for n in nodes}
        if start_node_id not in node_map:
            raise ValueError(f"Start node '{start_node_id}' not found in pipeline")

        # --- Validate config_overrides reference real nodes ---
        if config_overrides:
            unknown_overrides = set(config_overrides.keys()) - set(node_map.keys())
            if unknown_overrides:
                raise ValueError(
                    f"config_overrides reference unknown node IDs: {sorted(unknown_overrides)}"
                )

        # --- Topological sort ---
        order = _topological_sort(nodes, edges)

        # --- Refuse partial re-run for pipelines with loops ---
        try:
            loops = _detect_loops(nodes, edges)
        except ValueError:
            loops = []  # Illegal cycle — will surface via other validation
        if loops:
            raise ValueError(
                "Partial re-run is not supported for pipelines containing "
                "loop controllers. Please use full execution instead."
            )

        # --- Resolve config inheritance across the DAG ---
        resolved_configs = resolve_configs(
            nodes, edges, order, find_block_dir_fn=_find_block_module,
        )

        # --- Find downstream nodes (inclusive of start) ---
        downstream = _get_downstream_nodes(start_node_id, nodes, edges)
        upstream_ids = set(order) - downstream

        # --- Validate upstream definitions match ---
        if source_run.config_snapshot:
            source_nodes_list = source_run.config_snapshot.get("nodes", [])
            source_node_map = {n["id"]: n for n in source_nodes_list}
            mismatched = _validate_upstream_definitions(
                node_map, source_node_map, upstream_ids
            )
            if mismatched:
                raise ValueError(
                    f"Upstream node definitions changed since source run: {mismatched}. "
                    "Cannot safely reuse cached outputs."
                )

        # --- Validate cached outputs exist for all upstream nodes ---
        for nid in upstream_ids:
            node = node_map.get(nid)
            if node and node.get("type") == "groupNode":
                continue  # Visual-only nodes have no outputs
            if nid not in cached_outputs:
                raise ValueError(
                    f"Source run missing cached outputs for upstream node '{nid}'. "
                    "Cannot perform partial re-run; use full execution instead."
                )

        # --- Execution loop ---
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

            # Memory pressure circuit breaker
            is_critical, mem_pct = _check_memory_pressure()
            if is_critical:
                error_msg = (
                    f"Execution halted: Out of Memory Protection triggered. "
                    f"{mem_pct}% of unified memory in use "
                    f"(threshold: {MEMORY_PRESSURE_THRESHOLD}%)."
                )
                run.status = "failed"
                run.error_message = error_msg
                run.finished_at = datetime.now(timezone.utc)
                run.duration_seconds = time.time() - start_time
                run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                live.status = "failed"
                db.commit()
                try:
                    publish_event(run_id, "run_failed", {
                        "run_id": run_id,
                        "error": error_msg,
                        "memory_percent": mem_pct,
                        "threshold": MEMORY_PRESSURE_THRESHOLD,
                    })
                except Exception:
                    pass
                return

            node_data = node.get("data", {})
            block_type = node_data.get("type", "")
            # Use resolved config (with inheritance) instead of raw node config
            config = dict(resolved_configs.get(node_id, node_data.get("config", {})))
            # Strip provenance metadata
            config.pop("_inherited", None)
            category = node_data.get("category", "flow")

            # Apply CONFIG_MIGRATIONS for aliased block types
            original_type = block_type
            if original_type in CONFIG_MIGRATIONS:
                for mig_key, mig_val in CONFIG_MIGRATIONS[original_type].items():
                    config.setdefault(mig_key, mig_val)

            # ---- CACHED NODE: use outputs from source run ----
            if node_id not in downstream:
                # Kill switch: validate cache before reuse
                if not is_cache_valid(node_id, pipeline_id, config, db):
                    import sys as _sys
                    reason = "config_changed"
                    _last_run = db.query(Run).filter(
                        Run.pipeline_id == pipeline_id
                    ).order_by(Run.started_at.desc()).first()
                    if _last_run and _last_run.status != "complete":
                        reason = "run_incomplete"
                    print(
                        f"[kill-switch] Cache invalidated for node {node_id}: {reason}",
                        file=_sys.stderr,
                    )
                    try:
                        publish_event(run_id, "cache_invalidated", {
                            "node_id": node_id,
                            "reason": reason,
                        })
                    except Exception:
                        pass
                    downstream.add(node_id)

                # Verify artifact integrity before reusing cached outputs
                if node_id not in downstream:
                    art_ok, art_reason = _verify_node_artifacts(
                        source_run_id, node_id, db,
                    )
                    if not art_ok:
                        import logging
                        logging.getLogger("blueprint.partial_executor").warning(
                            "Artifact verification failed for node %s: %s. "
                            "Forcing re-execution from this node forward.",
                            node_id, art_reason,
                        )
                        downstream.add(node_id)
                        downstream |= _get_downstream_nodes(node_id, nodes, edges)

                if node_id not in downstream:
                    outputs[node_id] = cached_outputs.get(node_id, {})

                    cache_event = {
                        "node_id": node_id,
                        "block_type": block_type,
                        "category": category,
                        "index": idx,
                        "total": len(nodes),
                        "source_run_id": source_run_id,
                    }
                    try:
                        publish_event(run_id, "node_cached", cache_event)
                    except Exception:
                        pass
                    metrics_log_buffer.append({
                        "type": "node_cached", "timestamp": time.time(), **cache_event
                    })
                    metrics_file.write(
                        json.dumps({
                            "type": "node_cached",
                            "timestamp": time.time(),
                            **cache_event,
                        }) + "\n"
                    )
                    metrics_file.flush()

                    # Update live run progress
                    live.current_block = node_data.get("label", block_type)
                    live.current_block_index = idx
                    live.block_progress = 1.0
                    live.overall_progress = (idx + 1) / len(nodes)
                    db.commit()
                    continue

            # ---- EXECUTE NODE: run normally ----

            # Apply config overrides for this node
            if node_id in config_overrides:
                config.update(config_overrides[node_id])

            # Update live run
            live.current_block = node_data.get("label", block_type)
            live.current_block_index = idx
            live.block_progress = 0.0
            live.overall_progress = idx / len(nodes)
            db.commit()

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
            metrics_log_buffer.append({
                "type": "node_started", "timestamp": time.time(), **started_event
            })
            metrics_file.write(
                json.dumps({
                    "type": "node_started", "timestamp": time.time(), **started_event
                }) + "\n"
            )
            metrics_file.flush()

            # Gather inputs from upstream edges
            node_inputs: dict[str, Any] = {}
            _multi_counts: dict[str, int] = {}
            for edge in edges:
                if edge.get("target") == node_id:
                    src_id = edge.get("source", "")
                    src_handle = edge.get("sourceHandle", "")
                    tgt_handle = edge.get("targetHandle", "")
                    # Resolve aliased output handle IDs from renamed ports
                    if src_id in outputs and src_handle not in outputs[src_id]:
                        src_node = node_map.get(src_id)
                        if src_node:
                            src_type = src_node.get("data", {}).get("type", src_node.get("type", ""))
                            src_handle = resolve_output_handle(src_type, src_handle)
                    if src_id in outputs and src_handle in outputs[src_id]:
                        value = outputs[src_id][src_handle]
                        _multi_counts[tgt_handle] = _multi_counts.get(tgt_handle, 0) + 1
                        if tgt_handle in node_inputs:
                            if not isinstance(node_inputs[tgt_handle], list) or _multi_counts[tgt_handle] == 2:
                                node_inputs[tgt_handle] = [node_inputs[tgt_handle], value]
                            else:
                                node_inputs[tgt_handle].append(value)
                        else:
                            node_inputs[tgt_handle] = value

            # Find and run block
            block_dir = _find_block_module(block_type)

            # Custom block fallback
            if block_dir is None:
                base_type = config.get("baseType", "")
                if base_type and SAFE_BLOCK_TYPE.match(base_type):
                    base_type = BLOCK_ALIASES.get(base_type, base_type)
                    block_dir = _find_block_module(base_type)

            run_dir = str(ARTIFACTS_DIR / run_id / node_id)

            # Resolve secrets
            config = _resolve_secrets(config)

            if block_dir:
                _last_progress_commit = time.time()

                def progress_cb(current, total):
                    nonlocal _last_progress_commit
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
                        publish_event(run_id, "node_log", {
                            "node_id": node_id, "message": msg,
                        })
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
                    metrics_file.write(json.dumps(metric_event) + "\n")
                    metrics_file.flush()
                    metrics_log_buffer.append(metric_event)

                # Detect composite blocks + read timeout from schema
                block_schema = load_block_schema(block_dir)
                is_composite = block_schema.get("composite", False) if block_schema else False
                context_cls = CompositeBlockContext if is_composite else None
                timeout_seconds = block_schema.get("timeout") if block_schema else None

                # Embed block version into config_snapshot for cache validation
                if block_schema and block_schema.get("version"):
                    node_data["block_version"] = block_schema["version"]

                try:
                    node_outputs, data_fingerprints = _load_and_run_block(
                        block_dir, config, node_inputs, run_dir,
                        run_id, node_id, progress_cb, message_cb, metric_cb,
                        context_cls=context_cls,
                    )
                    outputs[node_id] = node_outputs
                    if data_fingerprints:
                        all_fingerprints[node_id] = data_fingerprints
                except InterruptedError:
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
                        publish_event(run_id, "node_failed", {
                            "node_id": node_id, "error": str(e),
                        })
                    except Exception:
                        pass
                    run.status = "failed"
                    run.error_message = scrub_traceback(f"Block {block_type} failed: {str(e)}\n\n{tb}")
                    run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                    live.status = "failed"
                    db.commit()
                    _write_error_log(run_id, tb)
                    return
            else:
                try:
                    publish_event(run_id, "node_failed", {
                        "node_id": node_id,
                        "error": f"Block type '{block_type}' not found",
                    })
                except Exception:
                    pass
                run.status = "failed"
                run.error_message = f"Block type '{block_type}' not found. No run.py available."
                run.outputs_snapshot = _safe_outputs_snapshot(outputs)
                live.status = "failed"
                db.commit()
                return

            # Register artifacts produced by this block (best-effort)
            artifact_ids: list[str] = []
            try:
                artifact_ids = register_block_artifacts(
                    pipeline_id=pipeline_id,
                    run_id=run_id,
                    node_id=node_id,
                    block_type=block_type,
                    outputs=node_outputs,
                    run_dir=run_dir,
                )
            except Exception:
                pass

            # Determine primary output data type for canvas indicators
            primary_output_type = None
            try:
                if block_schema and block_schema.get("outputs"):
                    primary_output_type = block_schema["outputs"][0].get("data_type")
            except Exception:
                pass

            # Heartbeat + partial outputs (preview-only, not authoritative)
            run.last_heartbeat = datetime.now(timezone.utc)
            run.outputs_snapshot = _safe_outputs_snapshot(outputs)
            db.commit()

            # Publish outputs
            safe_outputs = {}
            for k, v in node_outputs.items():
                try:
                    json.dumps(v)
                    safe_outputs[k] = v if not isinstance(v, str) or len(v) < 200 else v[:200] + '...'
                except Exception:
                    safe_outputs[k] = str(v)[:200]
            try:
                publish_event(run_id, "node_output", {
                    "node_id": node_id, "outputs": safe_outputs,
                })
            except Exception:
                pass

            completed_event = {
                "node_id": node_id,
                "index": idx,
                "primary_output_type": primary_output_type,
                "artifact_count": len(artifact_ids),
            }
            try:
                publish_event(run_id, "node_completed", completed_event)
            except Exception:
                pass
            metrics_log_buffer.append({
                "type": "node_completed", "timestamp": time.time(), **completed_event
            })
            metrics_file.write(
                json.dumps({
                    "type": "node_completed", "timestamp": time.time(), **completed_event
                }) + "\n"
            )
            metrics_file.flush()

            # Layer 2: 60s checkpoint
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
        run.data_fingerprints = all_fingerprints
        live.status = "complete"
        live.overall_progress = 1.0
        db.commit()

        # Auto-generate run export JSON (parity with main executor)
        try:
            from .run_export import generate_run_export
            from ..config import ARTIFACTS_DIR as _ARTIFACTS_DIR
            export = generate_run_export(run, _ARTIFACTS_DIR)
            export_path = _ARTIFACTS_DIR / run_id / "run-export.json"
            export_path.parent.mkdir(parents=True, exist_ok=True)
            with open(export_path, "w") as f:
                json.dump(export, f, indent=2)
        except Exception:
            pass

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
                "partial": True,
                "source_run_id": source_run_id,
                "start_node_id": start_node_id,
            })
        except Exception:
            pass

    except Exception as e:
        tb = traceback.format_exc()
        run.status = "failed"
        run.error_message = scrub_traceback(f"{str(e)}\n\n{tb}")
        run.finished_at = datetime.now(timezone.utc)
        run.duration_seconds = time.time() - start_time
        run.outputs_snapshot = _safe_outputs_snapshot(outputs)
        run.metrics_log = list(metrics_log_buffer)
        run.data_fingerprints = all_fingerprints
        live.status = "failed"
        db.commit()
        _write_error_log(run_id, tb)

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
        with _cancel_lock:
            _cancel_events.pop(run_id, None)
        system_metrics_stop.set()
        try:
            metrics_file.close()
        except Exception:
            pass
