"""
Structured Logger — JSON event logging for Blueprint.

Every executor event is logged as a JSON line to a rotating log file.
Human-readable logs continue via standard Python logging.
"""

import json
import logging
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from ..config import BASE_DIR

LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "blueprint.jsonl"
MAX_LOG_SIZE = 50 * 1024 * 1024  # 50MB
BACKUP_COUNT = 5

_json_handler = None
_logger = logging.getLogger("blueprint.structured")
_logger.propagate = False  # Don't duplicate structured events into console/root logger
_initialized = False


def init_structured_logging():
    """Initialize the structured JSON log file. Safe to call multiple times."""
    global _json_handler, _initialized
    if _initialized:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    _json_handler = RotatingFileHandler(
        str(LOG_FILE),
        maxBytes=MAX_LOG_SIZE,
        backupCount=BACKUP_COUNT,
    )
    _json_handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_json_handler)
    _logger.setLevel(logging.INFO)
    _initialized = True


def _safe_json_dumps(obj: dict) -> str:
    """Serialize dict to JSON, falling back to str() for non-serializable values."""
    try:
        return json.dumps(obj)
    except (TypeError, ValueError, OverflowError):
        # Fallback: convert non-serializable values to strings
        sanitized = {}
        for k, v in obj.items():
            if isinstance(v, dict):
                try:
                    json.dumps(v)
                    sanitized[k] = v
                except (TypeError, ValueError, OverflowError):
                    sanitized[k] = str(v)
            else:
                try:
                    json.dumps(v)
                    sanitized[k] = v
                except (TypeError, ValueError, OverflowError):
                    sanitized[k] = str(v)
        return json.dumps(sanitized)


def log_event(
    event_type: str,
    run_id: str = "",
    node_id: str = "",
    message: str = "",
    data: dict | None = None,
    level: str = "info",
):
    """Log a structured event as a JSON line."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "epoch": time.time(),
        "event": event_type,
        "level": level,
    }
    if run_id:
        entry["run_id"] = run_id
    if node_id:
        entry["node_id"] = node_id
    if message:
        entry["msg"] = message
    if data:
        entry["data"] = data

    try:
        _logger.info(_safe_json_dumps(entry))
    except Exception:
        pass  # Structured logging must never crash the caller


def log_run_start(run_id: str, pipeline_id: str, node_count: int):
    log_event("run_start", run_id=run_id, data={
        "pipeline_id": pipeline_id,
        "node_count": node_count,
    })


def log_run_complete(run_id: str, duration: float, metrics: dict):
    log_event("run_complete", run_id=run_id, data={
        "duration_s": round(duration, 2),
        "metric_count": len(metrics),
    })


def log_run_failed(run_id: str, error: str, node_id: str = ""):
    log_event("run_failed", run_id=run_id, node_id=node_id,
              message=error[:500], level="error")


def log_block_start(run_id: str, node_id: str, block_type: str, index: int, total: int):
    log_event("block_start", run_id=run_id, node_id=node_id, data={
        "block_type": block_type,
        "index": index,
        "total": total,
    })


def log_block_complete(run_id: str, node_id: str, block_type: str, duration: float):
    log_event("block_complete", run_id=run_id, node_id=node_id, data={
        "block_type": block_type,
        "duration_s": round(duration, 2),
    })


def log_block_failed(run_id: str, node_id: str, block_type: str, error: str, traceback: str = ""):
    log_event("block_failed", run_id=run_id, node_id=node_id,
              message=error[:500], level="error", data={
                  "block_type": block_type,
                  "traceback": traceback[:2000],
              })


def log_recovery(run_id: str, original_status: str):
    log_event("stale_recovery", run_id=run_id, data={
        "original_status": original_status,
    }, level="warning")


def log_config_resolution(run_id: str, inherited_keys: dict):
    log_event("config_resolved", run_id=run_id, data={
        "inherited_keys": inherited_keys,
    })
