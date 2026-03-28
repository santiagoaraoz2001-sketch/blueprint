"""Dashboard routes — traceability, experiment journal, research export, pin best run."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import ARTIFACTS_DIR
from ..database import get_db
from ..models.run import Run
from ..models.pipeline import Pipeline
from ..models.project import Project
from ..models.experiment_phase import ExperimentPhase
from ..models.experiment_note import ExperimentNote
from ..models.artifact import ArtifactRecord

router = APIRouter(prefix="/api", tags=["dashboard"])


# ── Secret redaction ────────────────────────────────────────────────────

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


# ── Traceability ────────────────────────────────────────────────────────

@router.get("/runs/{run_id}/traceability/{node_id}")
def get_traceability(run_id: str, node_id: str, db: Session = Depends(get_db)):
    """Walk the execution plan edges backwards from a node to build a full provenance chain.

    Returns the complete lineage: metric source, node execution details,
    input lineage with upstream artifact manifests, and data source nodes.
    """
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

    # Build adjacency: target -> list of (source_id, source_handle, target_handle)
    incoming: dict[str, list[dict]] = {}
    for edge in edges:
        tgt = edge.get("target")
        if tgt:
            incoming.setdefault(tgt, []).append({
                "source_id": edge.get("source", ""),
                "source_handle": edge.get("sourceHandle", ""),
                "target_handle": edge.get("targetHandle", ""),
            })

    # Get artifact records for this run
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

    # Metrics for the target node
    run_metrics = run.metrics if isinstance(run.metrics, dict) else {}

    # Source block types (data loaders, model selectors)
    SOURCE_BLOCK_TYPES = {
        "data_loader", "csv_loader", "json_loader", "dataset_loader",
        "model_selector", "model_loader", "huggingface_loader",
        "file_reader", "api_source",
    }

    def _is_source_node(n: dict) -> bool:
        bt = n.get("data", {}).get("type", "")
        cat = n.get("data", {}).get("category", "")
        return bt in SOURCE_BLOCK_TYPES or cat in ("data", "external")

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

        # Duration from metrics log
        duration = _get_node_duration(nid)

        # Config fingerprint
        fingerprint = None
        if isinstance(run.config_fingerprints, dict):
            fingerprint = run.config_fingerprints.get(nid)

        # Build resolved config (redacted)
        resolved_config = _redact_config(config)

        # Check if this was a cache hit (no execution record in metrics log)
        cache_decision = _get_cache_decision(nid)

        result: dict[str, Any] = {
            "node_id": nid,
            "block_type": block_type,
            "label": label,
            "category": category,
            "resolved_config": resolved_config,
            "config_fingerprint": fingerprint,
            "duration_seconds": duration,
            "cache_decision": cache_decision,
            "is_source": _is_source_node(node),
        }

        # If source node, add data source info
        if _is_source_node(node):
            source_info = {}
            if "file_path" in config:
                source_info["file_path"] = config["file_path"]
            if "model_name" in config or "model_id" in config:
                source_info["model_identifier"] = config.get("model_name") or config.get("model_id", "")
            if "dataset_name" in config:
                source_info["dataset_name"] = config["dataset_name"]
            if "dataset_size" in config:
                source_info["dataset_size"] = config["dataset_size"]
            result["data_source"] = source_info

        # Output artifacts for this node
        node_artifacts = {}
        for ar_key, ar_val in artifact_by_node_port.items():
            ar_nid, ar_port = ar_key.split(":", 1)
            if ar_nid == nid:
                node_artifacts[ar_port] = ar_val
        if node_artifacts:
            result["output_artifacts"] = node_artifacts

        # Input lineage: trace upstream
        upstream = incoming.get(nid, [])
        if upstream:
            inputs = []
            for edge_info in upstream:
                src_id = edge_info["source_id"]
                src_handle = edge_info["source_handle"]
                tgt_handle = edge_info["target_handle"]

                # Get upstream artifact
                artifact_key = f"{src_id}:{src_handle}"
                upstream_artifact = artifact_by_node_port.get(artifact_key)

                src_node = node_map.get(src_id, {})
                src_label = src_node.get("data", {}).get("label", src_id)

                input_entry: dict[str, Any] = {
                    "input_port": tgt_handle,
                    "from_node": src_id,
                    "from_node_label": src_label,
                    "from_port": src_handle,
                }
                if upstream_artifact:
                    input_entry["upstream_artifact"] = upstream_artifact

                # Recursively trace upstream
                input_entry["lineage"] = _trace_node(src_id, depth + 1, visited.copy())

                inputs.append(input_entry)

            result["input_lineage"] = inputs

        return result

    # Helper functions that use metrics log
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

    # Build the trace starting from the requested node
    target_node = node_map[node_id]
    target_data = target_node.get("data", {})

    trace = {
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

    return trace


# ── Experiment Journal ──────────────────────────────────────────────────

class JournalUpdateRequest(BaseModel):
    user_notes: str | None = None


@router.get("/runs/{run_id}/journal")
def get_journal(run_id: str, db: Session = Depends(get_db)):
    """Get the experiment journal entry for a run."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    note = db.query(ExperimentNote).filter(ExperimentNote.run_id == run_id).first()
    if not note:
        # Generate on-demand if missing (for pre-existing runs)
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


@router.put("/runs/{run_id}/journal")
def update_journal(run_id: str, data: JournalUpdateRequest, db: Session = Depends(get_db)):
    """Update user_notes on a journal entry."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    note = db.query(ExperimentNote).filter(ExperimentNote.run_id == run_id).first()
    if not note:
        # Create one with empty auto_summary if none exists
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


@router.get("/projects/{project_id}/timeline")
def get_project_timeline(
    project_id: str,
    experiment_id: str | None = None,
    starred_only: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    db: Session = Depends(get_db),
):
    """Get the experiment timeline for a project — chronological journal entries across all runs.

    Supports cursor-based pagination for efficient traversal of large histories.

    Args:
        limit: Max entries to return (1-200, default 50).
        cursor: ISO 8601 timestamp of the last entry seen. Only entries with
                started_at strictly *before* this cursor are returned. Pass the
                ``next_cursor`` value from the previous response to fetch the
                next page.

    Returns:
        project_id, entries, next_cursor (null when no more pages), has_more.
    """
    # Clamp limit to sane range
    limit = max(1, min(limit, 200))

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    # Get all runs for this project
    run_query = db.query(Run).filter(Run.project_id == project_id)

    if experiment_id:
        # Filter by experiment through pipeline -> experiment linkage
        pipeline_ids = [
            p.id for p in db.query(Pipeline.id).filter(Pipeline.experiment_id == experiment_id).all()
        ]
        if pipeline_ids:
            run_query = run_query.filter(Run.pipeline_id.in_(pipeline_ids))
        else:
            return {"project_id": project_id, "entries": [], "next_cursor": None, "has_more": False}

    if starred_only:
        run_query = run_query.filter(Run.best_in_project == True)

    # Date range filters — pushed into SQL for efficiency
    if date_from:
        try:
            from_dt = datetime.fromisoformat(date_from)
            run_query = run_query.filter(Run.started_at >= from_dt)
        except ValueError:
            pass
    if date_to:
        try:
            to_dt = datetime.fromisoformat(date_to)
            run_query = run_query.filter(Run.started_at <= to_dt)
        except ValueError:
            pass

    # Cursor-based keyset pagination: fetch runs with started_at < cursor.
    # We order by started_at DESC so the most recent entries come first;
    # the cursor marks the boundary of the last page.
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            run_query = run_query.filter(Run.started_at < cursor_dt)
        except ValueError:
            pass

    # Fetch limit + 1 to detect whether a next page exists
    runs = (
        run_query
        .order_by(Run.started_at.desc())
        .limit(limit + 1)
        .all()
    )

    has_more = len(runs) > limit
    if has_more:
        runs = runs[:limit]

    run_ids = [r.id for r in runs]
    if not run_ids:
        return {"project_id": project_id, "entries": [], "next_cursor": None, "has_more": False}

    # Batch-load related data in two queries (not N+1)
    notes = db.query(ExperimentNote).filter(ExperimentNote.run_id.in_(run_ids)).all()
    note_by_run = {n.run_id: n for n in notes}

    pipeline_ids_list = list(set(r.pipeline_id for r in runs))
    pipelines = db.query(Pipeline).filter(Pipeline.id.in_(pipeline_ids_list)).all()
    pipeline_map = {p.id: p for p in pipelines}

    entries = []
    for run in runs:
        note = note_by_run.get(run.id)
        pipeline = pipeline_map.get(run.pipeline_id)
        created_at = note.created_at if note else run.started_at

        entries.append({
            "run_id": run.id,
            "run_status": run.status,
            "best_in_project": run.best_in_project,
            "timestamp": created_at.isoformat() if created_at else None,
            "experiment_name": pipeline.name if pipeline else None,
            "auto_summary": note.auto_summary if note else None,
            "user_notes": note.user_notes if note else None,
            "note_id": note.id if note else None,
            "duration_seconds": run.duration_seconds,
            "metrics": run.metrics if isinstance(run.metrics, dict) else {},
        })

    # Compute cursor for the next page from the last entry's started_at
    next_cursor = None
    if has_more and runs:
        last_run = runs[-1]
        if last_run.started_at:
            next_cursor = last_run.started_at.isoformat()

    return {
        "project_id": project_id,
        "entries": entries,
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


# ── Pin Best Run ────────────────────────────────────────────────────────

@router.post("/runs/{run_id}/pin-best")
def pin_best_run(run_id: str, db: Session = Depends(get_db)):
    """Pin a run as the best result in its project. Unpins the previous best."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    # Unpin any existing best run for the same project
    if run.project_id:
        db.query(Run).filter(
            Run.project_id == run.project_id,
            Run.best_in_project == True,
            Run.id != run_id,
        ).update({"best_in_project": False})

    run.best_in_project = True
    db.commit()

    # Add journal entry about pinning
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


@router.post("/runs/{run_id}/unpin-best")
def unpin_best_run(run_id: str, db: Session = Depends(get_db)):
    """Remove the best-run pin from a run."""
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")

    run.best_in_project = False
    db.commit()

    return {"status": "unpinned", "run_id": run_id, "best_in_project": False}


# ── Research Export ─────────────────────────────────────────────────────

def _flatten_dict(d: dict, prefix: str = "") -> dict:
    items = {}
    if not isinstance(d, dict):
        return items
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            items.update(_flatten_dict(v, key))
        else:
            items[key] = v
    return items


@router.get("/projects/{project_id}/export/report")
def export_research_report(project_id: str, db: Session = Depends(get_db)):
    """Generate a structured Markdown research report with YAML frontmatter."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    # Gather all runs for this project
    runs = (
        db.query(Run)
        .filter(Run.project_id == project_id)
        .order_by(Run.started_at.asc())
        .all()
    )

    # Gather pipelines
    pipeline_ids = list(set(r.pipeline_id for r in runs))
    pipelines = db.query(Pipeline).filter(Pipeline.id.in_(pipeline_ids)).all() if pipeline_ids else []
    pipeline_map = {p.id: p for p in pipelines}

    # Gather journal entries
    run_ids = [r.id for r in runs]
    notes = db.query(ExperimentNote).filter(ExperimentNote.run_id.in_(run_ids)).all() if run_ids else []
    note_by_run = {n.run_id: n for n in notes}

    # Gather artifacts
    artifacts = db.query(ArtifactRecord).filter(ArtifactRecord.run_id.in_(run_ids)).all() if run_ids else []

    # Find best run
    best_run = next((r for r in runs if r.best_in_project), None)

    # Build report
    lines = []

    # YAML frontmatter
    lines.append("---")
    lines.append(f"title: \"{project.name}\"")
    lines.append(f"project_id: \"{project.id}\"")
    lines.append(f"generated_at: \"{datetime.now(timezone.utc).isoformat()}\"")
    lines.append(f"total_runs: {len(runs)}")
    if best_run:
        lines.append(f"best_run_id: \"{best_run.id}\"")
    lines.append("---")
    lines.append("")

    # 1. Title
    lines.append(f"# {project.name}")
    lines.append("")

    # 2. Hypothesis
    lines.append("## Hypothesis")
    lines.append("")
    lines.append(project.hypothesis or "_No hypothesis specified._")
    lines.append("")

    # 3. Methodology
    lines.append("## Methodology")
    lines.append("")
    for pipeline in pipelines:
        defn = pipeline.definition if isinstance(pipeline.definition, dict) else {}
        nodes = defn.get("nodes", [])
        block_count = len(nodes)
        block_list = ", ".join(
            n.get("data", {}).get("label", n.get("data", {}).get("type", "unknown"))
            for n in nodes[:10]
        )
        if len(nodes) > 10:
            block_list += f", ... (+{len(nodes) - 10} more)"

        # Top config keys from first run of this pipeline
        first_run = next((r for r in runs if r.pipeline_id == pipeline.id), None)
        config_summary = ""
        if first_run and isinstance(first_run.config_snapshot, dict):
            flat = _flatten_dict(first_run.config_snapshot)
            # Filter to interesting keys
            interesting = {k: v for k, v in flat.items()
                          if not k.startswith(("nodes.", "edges.", "workspace_config."))
                          and not any(pat in k.lower() for pat in _SECRET_PATTERNS)}
            top_keys = list(interesting.items())[:3]
            if top_keys:
                config_summary = " Key configuration: " + ", ".join(f"`{k}={v}`" for k, v in top_keys) + "."

        lines.append(
            f"- **{pipeline.name}**: {block_count}-step pipeline: {block_list}.{config_summary}"
        )
    lines.append("")

    # 4. Results — comparison matrix as markdown table
    lines.append("## Results")
    lines.append("")

    if runs:
        # Collect all metric keys
        all_metric_keys: set[str] = set()
        for r in runs:
            if isinstance(r.metrics, dict):
                all_metric_keys.update(r.metrics.keys())
        sorted_metrics = sorted(all_metric_keys)

        if sorted_metrics:
            # Table header
            header = "| Run | Status | Duration |"
            separator = "|-----|--------|----------|"
            for mk in sorted_metrics:
                header += f" {mk} |"
                separator += "------|"
            lines.append(header)
            lines.append(separator)

            # Find best values for diff annotations
            best_values: dict[str, tuple] = {}  # metric -> (best_value, direction)
            for mk in sorted_metrics:
                values = []
                for r in runs:
                    m = r.metrics if isinstance(r.metrics, dict) else {}
                    if mk in m and isinstance(m[mk], (int, float)):
                        values.append(m[mk])
                if values:
                    # Heuristic: "loss" metrics are better lower, others better higher
                    if "loss" in mk.lower() or "error" in mk.lower():
                        best_values[mk] = (min(values), "lower")
                    else:
                        best_values[mk] = (max(values), "higher")

            for r in runs:
                pipeline = pipeline_map.get(r.pipeline_id)
                name = (pipeline.name if pipeline else r.id[:8])
                duration = f"{r.duration_seconds:.1f}s" if r.duration_seconds else "-"
                pin = " **[BEST]**" if r.best_in_project else ""

                row = f"| {name}{pin} | {r.status} | {duration} |"
                metrics = r.metrics if isinstance(r.metrics, dict) else {}
                for mk in sorted_metrics:
                    val = metrics.get(mk)
                    if val is None:
                        row += " - |"
                    elif isinstance(val, float):
                        cell = f"{val:.6g}"
                        # Diff annotation
                        if mk in best_values and val == best_values[mk][0]:
                            cell = f"**{cell}** (best)"
                        row += f" {cell} |"
                    else:
                        row += f" {val} |"
                lines.append(row)
        else:
            lines.append("_No metrics recorded._")
    else:
        lines.append("_No runs completed._")
    lines.append("")

    # 5. Timeline
    lines.append("## Timeline")
    lines.append("")
    for r in runs:
        note = note_by_run.get(r.id)
        ts = r.started_at.strftime("%Y-%m-%d %H:%M") if r.started_at else "?"
        summary = note.auto_summary if note else f"Run {r.status}"
        user_note = f"\n  > {note.user_notes}" if note and note.user_notes else ""
        pin_marker = " [BEST]" if r.best_in_project else ""
        lines.append(f"- **{ts}**{pin_marker}: {summary}{user_note}")
    lines.append("")

    # 6. Key Findings
    lines.append("## Key Findings")
    lines.append("")
    if best_run:
        best_note = note_by_run.get(best_run.id)
        if best_note:
            lines.append(f"_{best_note.auto_summary}_")
        else:
            lines.append(f"_Best run: {best_run.id[:8]} (status: {best_run.status})_")
    else:
        lines.append("_[Fill in key findings before export]_")
    lines.append("")

    # 7. Artifact References
    lines.append("## Artifact References")
    lines.append("")
    if artifacts:
        lines.append("| Artifact ID | Node | Port | Data Type | Size | Hash |")
        lines.append("|-------------|------|------|-----------|------|------|")
        for ar in artifacts[:50]:  # Cap at 50
            hash_short = ar.content_hash[:12] if ar.content_hash else "-"
            size_kb = f"{ar.size_bytes / 1024:.1f}KB" if ar.size_bytes else "-"
            lines.append(f"| {ar.id[:12]} | {ar.node_id} | {ar.port_id} | {ar.data_type} | {size_kb} | {hash_short} |")
    else:
        lines.append("_No artifacts recorded._")
    lines.append("")

    report = "\n".join(lines)
    return Response(content=report, media_type="text/markdown", headers={
        "Content-Disposition": f'attachment; filename="blueprint-report-{project.id[:8]}.md"',
    })


@router.get("/projects/{project_id}/export/json")
def export_dashboard_json(project_id: str, db: Session = Depends(get_db)):
    """Export raw dashboard data as JSON for programmatic consumption."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    runs = (
        db.query(Run)
        .filter(Run.project_id == project_id)
        .order_by(Run.started_at.asc())
        .all()
    )

    pipeline_ids = list(set(r.pipeline_id for r in runs))
    pipelines = db.query(Pipeline).filter(Pipeline.id.in_(pipeline_ids)).all() if pipeline_ids else []

    run_ids = [r.id for r in runs]
    notes = db.query(ExperimentNote).filter(ExperimentNote.run_id.in_(run_ids)).all() if run_ids else []
    note_by_run = {n.run_id: n for n in notes}

    artifacts = db.query(ArtifactRecord).filter(ArtifactRecord.run_id.in_(run_ids)).all() if run_ids else []

    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "hypothesis": project.hypothesis,
            "status": project.status,
            "created_at": project.created_at.isoformat() if project.created_at else None,
        },
        "pipelines": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "block_count": len((p.definition or {}).get("nodes", [])),
            }
            for p in pipelines
        ],
        "runs": [
            {
                "id": r.id,
                "pipeline_id": r.pipeline_id,
                "status": r.status,
                "best_in_project": r.best_in_project,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "duration_seconds": r.duration_seconds,
                "metrics": r.metrics if isinstance(r.metrics, dict) else {},
                "config_fingerprints": r.config_fingerprints if isinstance(r.config_fingerprints, dict) else {},
                "journal": {
                    "auto_summary": note_by_run[r.id].auto_summary if r.id in note_by_run else None,
                    "user_notes": note_by_run[r.id].user_notes if r.id in note_by_run else None,
                },
            }
            for r in runs
        ],
        "artifacts": [
            {
                "id": ar.id,
                "run_id": ar.run_id,
                "node_id": ar.node_id,
                "port_id": ar.port_id,
                "data_type": ar.data_type,
                "size_bytes": ar.size_bytes,
                "content_hash": ar.content_hash,
            }
            for ar in artifacts
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
