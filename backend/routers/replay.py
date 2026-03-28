"""Replay Inspector API — returns detailed per-node execution data for
completed or failed runs, plus support bundle generation.
"""

from __future__ import annotations

import io
import json
import logging
import platform as plat
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from ..config import ARTIFACTS_DIR
from ..database import get_db
from ..models.artifact import ArtifactRecord
from ..models.execution_decision import ExecutionDecision
from ..models.run import Run
from ..utils.redact import redact_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/runs", tags=["replay"])

# Keys whose values should be redacted in support bundles
_SECRET_KEY_PATTERNS = (
    "_key", "_token", "_secret", "_password",
    "api_key", "hf_token", "apikey", "auth_token",
)


def _is_secret_key(key: str) -> bool:
    """Check if a key name looks like it holds a secret value."""
    lower = key.lower()
    return any(pat in lower for pat in _SECRET_KEY_PATTERNS)


def _deep_redact(obj: Any) -> Any:
    """Recursively redact secret-like values in nested dicts/lists."""
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if (_is_secret_key(k) and isinstance(v, str)) else _deep_redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_deep_redact(item) for item in obj]
    if isinstance(obj, str):
        # Redact strings that look like secret references
        if obj.startswith("$secret:"):
            return "[REDACTED]"
    return obj


# ── Replay Data ──────────────────────────────────────────────────────────


def _build_node_replay(
    decision: ExecutionDecision,
    input_artifacts: list[ArtifactRecord],
    output_artifacts: list[ArtifactRecord],
) -> dict:
    """Build replay data for a single node."""
    error = None
    if decision.error_json:
        err = decision.error_json
        error = {
            "title": err.get("title", "Error"),
            "message": err.get("message", ""),
            "action": err.get("action", ""),
        }

    def _artifact_entry(rec: ArtifactRecord, include_size: bool = False) -> dict:
        entry: dict[str, Any] = {
            "port_id": rec.port_id,
            "artifact_id": rec.id,
            "data_type": rec.data_type,
            "preview": json.loads(rec.preview_json) if rec.preview_json else None,
        }
        if include_size:
            entry["size_bytes"] = rec.size_bytes
        return entry

    return {
        "node_id": decision.node_id,
        "block_type": decision.block_type,
        "status": decision.status,
        "started_at": decision.started_at.isoformat() if decision.started_at else None,
        "duration_ms": decision.duration_ms,
        "resolved_config": decision.resolved_config or {},
        "config_sources": decision.config_sources or {},
        "decision": decision.decision,
        "decision_reason": decision.decision_reason,
        "error": error,
        "input_artifacts": [_artifact_entry(a) for a in input_artifacts],
        "output_artifacts": [_artifact_entry(a, include_size=True) for a in output_artifacts],
        "execution_order": decision.execution_order,
        "iteration": decision.iteration,
        "loop_id": decision.loop_id,
        "memory_peak_mb": decision.memory_peak_mb,
    }


@router.get("/{run_id}/replay")
def get_run_replay(run_id: str, db: Session = Depends(get_db)):
    """Return full replay data for a completed or failed run.

    Response shape: {run_id, status, started_at, completed_at, duration_ms,
    nodes: [{node_id, block_type, status, ...}]}
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status not in ("complete", "failed", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"Run is {run.status} — replay is only available for completed, failed, or cancelled runs",
        )

    # Fetch all decisions for this run, ordered by execution_order
    decisions = (
        db.query(ExecutionDecision)
        .filter(ExecutionDecision.run_id == run_id)
        .order_by(ExecutionDecision.execution_order)
        .all()
    )

    # If no decisions recorded (older run before this feature), synthesize from config_snapshot
    if not decisions:
        return _synthesize_replay_from_snapshot(run, db)

    # Fetch all artifact records for this run
    all_artifacts = (
        db.query(ArtifactRecord)
        .filter(ArtifactRecord.run_id == run_id)
        .all()
    )

    # Index artifacts by node_id
    artifacts_by_node: dict[str, list[ArtifactRecord]] = {}
    for art in all_artifacts:
        artifacts_by_node.setdefault(art.node_id, []).append(art)

    # Build edges from config_snapshot to determine input artifacts
    edges = []
    snapshot = run.config_snapshot or {}
    if isinstance(snapshot, dict):
        edges = snapshot.get("edges", [])

    # Map: target_node_id -> list of (source_node_id, source_port, target_port)
    input_map: dict[str, list[tuple[str, str, str]]] = {}
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        src_handle = edge.get("sourceHandle", "output")
        tgt_handle = edge.get("targetHandle", "input")
        input_map.setdefault(tgt, []).append((src, src_handle, tgt_handle))

    # Build replay nodes
    nodes = []
    for dec in decisions:
        # Output artifacts: belong to this node
        output_arts = artifacts_by_node.get(dec.node_id, [])

        # Input artifacts: outputs of upstream nodes connected to this node
        input_arts = []
        for src_node, src_port, _tgt_port in input_map.get(dec.node_id, []):
            for art in artifacts_by_node.get(src_node, []):
                if art.port_id == src_port:
                    input_arts.append(art)

        nodes.append(_build_node_replay(dec, input_arts, output_arts))

    duration_ms = None
    if run.duration_seconds is not None:
        duration_ms = round(run.duration_seconds * 1000, 1)

    # Build loop iteration summary
    loop_iterations: dict[str, dict] = {}
    for dec in decisions:
        if dec.loop_id and dec.iteration is not None:
            if dec.loop_id not in loop_iterations:
                loop_iterations[dec.loop_id] = {
                    "controller_id": dec.loop_id,
                    "iterations": set(),
                    "body_node_ids": set(),
                }
            loop_iterations[dec.loop_id]["iterations"].add(dec.iteration)
            loop_iterations[dec.loop_id]["body_node_ids"].add(dec.node_id)

    loops_summary = [
        {
            "controller_id": info["controller_id"],
            "iterations": sorted(info["iterations"]),
            "body_node_ids": sorted(info["body_node_ids"]),
            "iteration_count": len(info["iterations"]),
        }
        for info in loop_iterations.values()
    ]

    return {
        "run_id": run.id,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": duration_ms,
        "nodes": nodes,
        "loops": loops_summary,
    }


def _synthesize_replay_from_snapshot(run: Run, db: Session) -> dict:
    """Synthesize minimal replay data from config_snapshot for older runs
    that don't have ExecutionDecision records.
    """
    snapshot = run.config_snapshot or {}
    nodes_data = snapshot.get("nodes", []) if isinstance(snapshot, dict) else []
    edges = snapshot.get("edges", []) if isinstance(snapshot, dict) else []

    # Fetch artifacts
    all_artifacts = (
        db.query(ArtifactRecord)
        .filter(ArtifactRecord.run_id == run.id)
        .all()
    )
    artifacts_by_node: dict[str, list[ArtifactRecord]] = {}
    for art in all_artifacts:
        artifacts_by_node.setdefault(art.node_id, []).append(art)

    nodes = []
    for idx, node in enumerate(nodes_data):
        node_id = node.get("id", "")
        block_type = node.get("data", {}).get("blockType", node.get("type", "unknown"))

        # Skip visual-only nodes
        if block_type in ("groupNode", "stickyNote"):
            continue

        has_artifacts = node_id in artifacts_by_node
        status = "completed" if has_artifacts else ("failed" if run.status == "failed" and idx == len(nodes_data) - 1 else "completed")

        nodes.append({
            "node_id": node_id,
            "block_type": block_type,
            "status": status,
            "started_at": None,
            "duration_ms": None,
            "resolved_config": node.get("data", {}).get("config", {}),
            "config_sources": {},
            "decision": "execute",
            "decision_reason": "synthesized from snapshot (no decision records available)",
            "error": None,
            "input_artifacts": [],
            "output_artifacts": [
                {
                    "port_id": a.port_id,
                    "artifact_id": a.id,
                    "data_type": a.data_type,
                    "preview": json.loads(a.preview_json) if a.preview_json else None,
                    "size_bytes": a.size_bytes,
                }
                for a in artifacts_by_node.get(node_id, [])
            ],
            "execution_order": idx,
            "iteration": None,
            "loop_id": None,
            "memory_peak_mb": None,
        })

    duration_ms = None
    if run.duration_seconds is not None:
        duration_ms = round(run.duration_seconds * 1000, 1)

    return {
        "run_id": run.id,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": duration_ms,
        "nodes": nodes,
    }


# ── Support Bundle ───────────────────────────────────────────────────────


def _collect_environment() -> dict[str, Any]:
    """Collect runtime environment info for the support bundle."""
    env: dict[str, Any] = {
        "python_version": sys.version.split()[0],
        "os": plat.platform(),
        "blueprint_version": "0.2.2",
    }

    # GPU info
    try:
        import torch
        env["torch_version"] = torch.__version__
        env["gpu_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            env["gpu_name"] = torch.cuda.get_device_name(0)
    except ImportError:
        env["gpu_available"] = False

    # Apple Silicon GPU
    try:
        import mlx.core as mx
        env["mlx_available"] = True
    except ImportError:
        env["mlx_available"] = False

    # Ollama
    try:
        import subprocess
        result = subprocess.run(
            ["ollama", "--version"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            env["ollama_version"] = result.stdout.strip()
    except Exception:
        pass

    # Installed packages (top-level only)
    try:
        import pkg_resources
        env["installed_packages"] = {
            d.project_name: d.version
            for d in sorted(pkg_resources.working_set, key=lambda x: x.project_name.lower())
        }
    except Exception:
        pass

    return env


def _collect_events_jsonl(run_id: str) -> list[dict]:
    """Collect key SSE events from the metrics log."""
    events = []
    metrics_file = ARTIFACTS_DIR / run_id / "metrics.jsonl"
    if metrics_file.exists():
        try:
            for line in metrics_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                    event_type = evt.get("event", evt.get("type", ""))
                    if event_type in (
                        "node_started", "node_completed", "node_failed",
                        "node_cached", "loop_iteration", "node_iteration",
                        "run_completed", "run_failed",
                    ):
                        events.append(evt)
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass
    return events


@router.post("/{run_id}/support-bundle")
def generate_support_bundle(run_id: str, db: Session = Depends(get_db)):
    """Generate a support bundle .zip for a run and return it as a streaming download.

    The bundle contains:
    - pipeline.json: Full pipeline definition
    - execution_plan.json: Planner output with execution order
    - resolved_configs.json: Per-node resolved config with sources
    - artifact_manifests.json: All ArtifactRecord entries for the run
    - execution_decisions.json: All ExecutionDecision records
    - classified_errors.json: Any errors with classification
    - environment.json: Python, OS, GPU, packages, Ollama status
    - events.jsonl: Key SSE events
    - run_metadata.json: Run ID, status, timestamps, duration

    All secret-like values are redacted.
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Collect all data
    snapshot = run.config_snapshot or {}

    # Pipeline definition (redacted)
    pipeline_json = _deep_redact(snapshot)

    # Execution decisions
    decisions = (
        db.query(ExecutionDecision)
        .filter(ExecutionDecision.run_id == run_id)
        .order_by(ExecutionDecision.execution_order)
        .all()
    )

    execution_plan: dict[str, Any] = {
        "execution_order": [d.node_id for d in decisions],
        "loop_boundaries": [],
    }

    # Collect loop boundaries from decisions
    loop_nodes: dict[str, list[str]] = {}
    for d in decisions:
        if d.loop_id:
            loop_nodes.setdefault(d.loop_id, []).append(d.node_id)
    if loop_nodes:
        execution_plan["loop_boundaries"] = [
            {"controller_id": lid, "body_node_ids": nids}
            for lid, nids in loop_nodes.items()
        ]

    resolved_configs: dict[str, Any] = {}
    for d in decisions:
        resolved_configs[d.node_id] = _deep_redact({
            "block_type": d.block_type,
            "resolved_config": d.resolved_config or {},
            "config_sources": d.config_sources or {},
        })

    # Artifact manifests
    all_artifacts = (
        db.query(ArtifactRecord)
        .filter(ArtifactRecord.run_id == run_id)
        .all()
    )
    artifact_manifests = [
        {
            "artifact_id": a.id,
            "node_id": a.node_id,
            "port_id": a.port_id,
            "data_type": a.data_type,
            "serializer": a.serializer,
            "content_hash": a.content_hash,
            "file_path": a.file_path,
            "size_bytes": a.size_bytes,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in all_artifacts
    ]

    execution_decisions_json = [
        _deep_redact({
            "node_id": d.node_id,
            "block_type": d.block_type,
            "execution_order": d.execution_order,
            "decision": d.decision,
            "decision_reason": d.decision_reason,
            "status": d.status,
            "started_at": d.started_at.isoformat() if d.started_at else None,
            "duration_ms": d.duration_ms,
            "resolved_config": d.resolved_config or {},
            "error": d.error_json,
            "iteration": d.iteration,
            "loop_id": d.loop_id,
        })
        for d in decisions
    ]

    # Classified errors
    classified_errors = []
    for d in decisions:
        if d.error_json:
            classified_errors.append({
                "node_id": d.node_id,
                "block_type": d.block_type,
                "error": d.error_json,
            })

    # Environment
    environment = _collect_environment()

    # Events
    events = _collect_events_jsonl(run_id)

    # Run metadata
    run_metadata = {
        "run_id": run.id,
        "pipeline_id": run.pipeline_id,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_seconds": run.duration_seconds,
        "error_message": run.error_message,
    }

    # Build the zip in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        def _write_json(name: str, data: Any):
            content = json.dumps(data, indent=2, ensure_ascii=False, default=str)
            # Final pass: scan for any remaining secrets
            content = _final_secret_scan(content)
            zf.writestr(name, content)

        _write_json("pipeline.json", pipeline_json)
        _write_json("execution_plan.json", execution_plan)
        _write_json("resolved_configs.json", resolved_configs)
        _write_json("artifact_manifests.json", artifact_manifests)
        _write_json("execution_decisions.json", execution_decisions_json)
        _write_json("classified_errors.json", classified_errors)
        _write_json("environment.json", environment)
        _write_json("run_metadata.json", run_metadata)

        # events.jsonl — one JSON object per line
        events_content = "\n".join(
            json.dumps(evt, ensure_ascii=False, default=str) for evt in events
        )
        events_content = _final_secret_scan(events_content)
        zf.writestr("events.jsonl", events_content)

    buf.seek(0)
    filename = f"blueprint-support-bundle-{run_id[:8]}.zip"

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _final_secret_scan(content: str) -> str:
    """Final pass: scan serialized JSON text for any remaining secret-like
    values that might have slipped through structural redaction.

    Matches patterns like: "api_key": "sk-12345" and replaces the value.
    """
    import re
    # Match JSON key-value pairs where key contains secret-like patterns
    pattern = re.compile(
        r'("(?:[^"]*(?:' + "|".join(
            p.replace("_", "[_-]?") for p in _SECRET_KEY_PATTERNS
        ) + r')[^"]*)")\s*:\s*"([^"]+)"',
        re.IGNORECASE,
    )
    def _replacer(m: re.Match) -> str:
        return f'{m.group(1)}: "[REDACTED]"'
    return pattern.sub(_replacer, content)
