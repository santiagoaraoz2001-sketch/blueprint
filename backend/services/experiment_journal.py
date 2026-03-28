"""
Experiment Journal — auto-generated run summaries with config/metric diffs.

After each run completes, generates a one-sentence summary comparing configs
and metrics with the most recent previous run of the same pipeline.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models.run import Run
from ..models.pipeline import Pipeline
from ..models.experiment_note import ExperimentNote

logger = logging.getLogger("blueprint.journal")

# Config keys that should never appear in summaries
_SECRET_PATTERNS = {"api_key", "secret", "token", "password", "credential", "auth"}


def _is_secret_key(key: str) -> bool:
    """Check if a config key likely contains sensitive data."""
    lower = key.lower()
    return any(pat in lower for pat in _SECRET_PATTERNS)


def _flatten_dict(d: dict, prefix: str = "") -> dict:
    """Flatten nested dicts: {"a": {"b": 1}} -> {"a.b": 1}"""
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


def _format_value(v) -> str:
    """Format a value for display, truncating long strings."""
    if isinstance(v, float):
        return f"{v:.6g}"
    if isinstance(v, str) and len(v) > 50:
        return v[:47] + "..."
    return str(v)


def _pct_change(old, new) -> str | None:
    """Compute percent change between two numeric values."""
    try:
        old_f = float(old)
        new_f = float(new)
        if old_f == 0:
            return None
        pct = ((new_f - old_f) / abs(old_f)) * 100
        sign = "+" if pct > 0 else ""
        return f"{sign}{pct:.1f}%"
    except (TypeError, ValueError):
        return None


def _extract_node_configs(config_snapshot: dict | None) -> dict[str, dict]:
    """Extract per-node configs from a config_snapshot, keyed by a stable node identity.

    Nodes are identified by their block_type + label combination to allow matching
    across runs even if node_ids differ (e.g. after pipeline edits). Falls back to
    node_id if no label is available.

    Returns: {"BlockLabel (block_type)": {flat_config_dict}}
    """
    if not isinstance(config_snapshot, dict):
        return {}

    nodes = config_snapshot.get("nodes", [])
    if not isinstance(nodes, list):
        return {}

    result = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        data = node.get("data", {})
        if not isinstance(data, dict):
            continue

        block_type = data.get("type", "unknown")
        label = data.get("label", block_type)
        config = data.get("config", {})
        if not isinstance(config, dict):
            continue

        # Build a stable key from label + block_type
        node_key = f"{label} ({block_type})"

        # Flatten the config and filter secrets
        flat = _flatten_dict(config)
        filtered = {k: v for k, v in flat.items() if not _is_secret_key(k)}
        if filtered:
            result[node_key] = filtered

    return result


def auto_summarize(run: Run, previous_runs: list[Run]) -> str:
    """Generate a one-sentence summary comparing this run with the previous one.

    If no previous runs exist, generates a first-run summary.

    Compares at two levels:
      1. Top-level config keys (pipeline-wide settings like workspace config)
      2. Per-node block configs (learning_rate, epochs, etc.) — the main source
         of experiment variation
    """
    run_number = len(previous_runs) + 1

    if not previous_runs:
        duration_str = ""
        if run.duration_seconds is not None:
            mins = run.duration_seconds / 60
            duration_str = f" Duration: {mins:.1f}m." if mins >= 1 else f" Duration: {run.duration_seconds:.0f}s."
        return (
            f"Run #{run_number}: first execution of pipeline. "
            f"Status: {run.status}.{duration_str}"
        )

    prev = previous_runs[0]  # Most recent previous run

    # ── Level 1: Top-level config keys (non-node, non-edge) ──
    curr_top = _flatten_dict(run.config_snapshot or {})
    prev_top = _flatten_dict(prev.config_snapshot or {})

    skip_prefixes = {"nodes", "edges", "workspace_config"}
    top_changes = []
    for key in sorted(set(curr_top.keys()) | set(prev_top.keys())):
        top_level = key.split(".")[0]
        if top_level in skip_prefixes:
            continue
        if _is_secret_key(key):
            continue
        cv = curr_top.get(key)
        pv = prev_top.get(key)
        if cv != pv and cv is not None and pv is not None:
            top_changes.append(f"{key.split('.')[-1]}={_format_value(cv)} (vs {_format_value(pv)})")

    # ── Level 2: Per-node config changes ──
    curr_nodes = _extract_node_configs(run.config_snapshot)
    prev_nodes = _extract_node_configs(prev.config_snapshot)

    node_changes = []
    # Check nodes present in both runs
    for node_key in sorted(set(curr_nodes.keys()) & set(prev_nodes.keys())):
        curr_cfg = curr_nodes[node_key]
        prev_cfg = prev_nodes[node_key]

        for k in sorted(set(curr_cfg.keys()) | set(prev_cfg.keys())):
            cv = curr_cfg.get(k)
            pv = prev_cfg.get(k)
            if cv != pv and cv is not None and pv is not None:
                # Use short node label (first part before the parenthesized type)
                short_label = node_key.split(" (")[0]
                node_changes.append(
                    f"{short_label}.{k}={_format_value(cv)} (vs {_format_value(pv)})"
                )

    # Check for added/removed nodes
    added_nodes = set(curr_nodes.keys()) - set(prev_nodes.keys())
    removed_nodes = set(prev_nodes.keys()) - set(curr_nodes.keys())

    structural_changes = []
    if added_nodes:
        structural_changes.append(f"added {', '.join(sorted(added_nodes))}")
    if removed_nodes:
        structural_changes.append(f"removed {', '.join(sorted(removed_nodes))}")

    # Merge changes: prioritize node-level changes (more informative), then top-level
    all_changes = node_changes + top_changes

    # ── Metric comparisons ──
    curr_metrics = run.metrics if isinstance(run.metrics, dict) else {}
    prev_metrics = prev.metrics if isinstance(prev.metrics, dict) else {}

    metric_diffs = []
    for name in sorted(set(curr_metrics.keys()) & set(prev_metrics.keys())):
        pct = _pct_change(prev_metrics[name], curr_metrics[name])
        if pct:
            metric_diffs.append(f"{name}: {pct}")

    # ── Build summary ──
    parts = [f"Run #{run_number}"]

    if structural_changes:
        parts.append(f"pipeline changes: {'; '.join(structural_changes)}")

    if all_changes:
        parts.append(f"used {', '.join(all_changes[:4])}")

    if metric_diffs:
        parts.append(f"Results: {'; '.join(metric_diffs[:4])}")

    if run.status == "failed":
        err = (run.error_message or "unknown error")[:80]
        parts.append(f"FAILED: {err}")

    return ". ".join(parts) + "."


def generate_journal_entry(run_id: str, db: Session) -> ExperimentNote | None:
    """Generate and persist a journal entry for a completed run.

    Returns the created ExperimentNote, or None if the run doesn't exist.
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        return None

    # Get previous runs of the same pipeline, ordered by start time desc
    previous_runs = (
        db.query(Run)
        .filter(
            Run.pipeline_id == run.pipeline_id,
            Run.id != run.id,
            Run.status.in_(["complete", "failed"]),
        )
        .order_by(Run.started_at.desc())
        .limit(10)
        .all()
    )

    summary = auto_summarize(run, previous_runs)

    note = ExperimentNote(
        id=str(uuid.uuid4()),
        run_id=run_id,
        auto_summary=summary,
        created_at=datetime.now(timezone.utc),
    )
    db.add(note)
    db.commit()

    return note


def on_run_journal(run_id: str, db: Session) -> None:
    """Hook called after run completion to generate journal entry.

    Never crashes the executor — all errors are caught.
    """
    try:
        generate_journal_entry(run_id, db)
    except Exception as e:
        logger.warning("Journal generation failed for run %s: %s", run_id, e)
