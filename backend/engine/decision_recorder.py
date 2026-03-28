"""Decision Recorder — writes ExecutionDecision rows during pipeline execution.

Lightweight helper called from executor.py and partial_executor.py to record
per-node decisions without polluting the main execution logic.

Architecture:
  - Uses a SEPARATE database session for decision writes so that failures
    in decision recording never contaminate the executor's main session.
  - All writes go through a per-run buffer that is flushed periodically
    (every 5 seconds) and on explicit flush_decisions() calls.
  - If a write fails, it is retried once on the next flush cycle.
  - The deferred-write pattern means decision records may lag a few seconds
    behind execution events, but they will always be committed before the
    run completes (flush_decisions is called in the finally block).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from ..database import SessionLocal
from ..models.execution_decision import ExecutionDecision

logger = logging.getLogger(__name__)

# Flush interval in seconds
_FLUSH_INTERVAL = float(os.environ.get("BLUEPRINT_DECISION_FLUSH_INTERVAL", "5"))

# Max retries for a single decision write
_MAX_RETRIES = 2


# ── Per-run buffer ──────────────────────────────────────────────────────

class _DecisionBuffer:
    """Thread-safe buffer of pending ExecutionDecision records for a single run."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._lock = threading.Lock()
        self._pending: list[dict[str, Any]] = []
        self._retries: list[tuple[dict[str, Any], int]] = []  # (kwargs, attempt_count)
        self._records: dict[str, ExecutionDecision] = {}  # node_id -> record (for updates)
        self._updates: list[tuple[str, dict[str, Any]]] = []  # (node_key, field updates)
        self._last_flush = time.monotonic()

    def add(self, kwargs: dict[str, Any]) -> str:
        """Queue a new decision record. Returns a node_key for later updates."""
        node_key = f"{kwargs['node_id']}:{kwargs.get('iteration', '')}"
        with self._lock:
            self._pending.append(kwargs)
        return node_key

    def update(self, node_key: str, fields: dict[str, Any]) -> None:
        """Queue field updates for a previously added decision."""
        with self._lock:
            self._updates.append((node_key, fields))

    def flush(self) -> None:
        """Commit all pending decisions and updates to the database.

        Uses a dedicated DB session. On failure, moves items to the retry
        queue for the next flush cycle. Called periodically by the executor
        and once in the finally block.
        """
        with self._lock:
            pending = list(self._pending)
            self._pending.clear()
            retries = list(self._retries)
            self._retries.clear()
            updates = list(self._updates)
            self._updates.clear()
            records_snapshot = dict(self._records)
            self._last_flush = time.monotonic()

        if not pending and not retries and not updates:
            return

        session = SessionLocal()
        try:
            # 1. Insert new records (including retries)
            all_inserts = [(kw, 0) for kw in pending] + retries
            failed_inserts: list[tuple[dict[str, Any], int]] = []

            for kwargs, attempt in all_inserts:
                try:
                    rec = ExecutionDecision(**kwargs)
                    session.add(rec)
                    session.flush()
                    node_key = f"{kwargs['node_id']}:{kwargs.get('iteration', '')}"
                    with self._lock:
                        self._records[node_key] = rec
                except Exception:
                    session.rollback()
                    if attempt < _MAX_RETRIES:
                        failed_inserts.append((kwargs, attempt + 1))
                    else:
                        logger.warning(
                            "Dropping decision record for %s/%s after %d attempts",
                            self.run_id, kwargs.get("node_id"), attempt + 1,
                        )

            # 2. Apply updates to committed records
            # Re-query records in this session to avoid DetachedInstanceError
            for node_key, fields in updates:
                rec = None
                with self._lock:
                    rec = self._records.get(node_key)
                if rec is None:
                    continue
                try:
                    # Merge into this session if needed
                    merged = session.merge(rec)
                    for k, v in fields.items():
                        setattr(merged, k, v)
                    session.flush()
                    with self._lock:
                        self._records[node_key] = merged
                except Exception:
                    session.rollback()
                    logger.debug(
                        "Failed to update decision for %s (key=%s)",
                        self.run_id, node_key, exc_info=True,
                    )

            session.commit()

            # Re-queue failed inserts for next flush
            if failed_inserts:
                with self._lock:
                    self._retries.extend(failed_inserts)

        except Exception:
            logger.warning(
                "Decision flush failed for run %s, %d pending items deferred",
                self.run_id, len(pending), exc_info=True,
            )
            try:
                session.rollback()
            except Exception:
                pass
            # Re-queue everything for retry
            with self._lock:
                for kw in pending:
                    self._retries.append((kw, 1))
        finally:
            session.close()

    def should_flush(self) -> bool:
        """Check if enough time has passed since last flush."""
        return time.monotonic() - self._last_flush >= _FLUSH_INTERVAL


# ── Global buffer registry ──────────────────────────────────────────────

_buffers_lock = threading.Lock()
_buffers: dict[str, _DecisionBuffer] = {}


def _get_buffer(run_id: str) -> _DecisionBuffer:
    with _buffers_lock:
        if run_id not in _buffers:
            _buffers[run_id] = _DecisionBuffer(run_id)
        return _buffers[run_id]


def _remove_buffer(run_id: str) -> None:
    with _buffers_lock:
        _buffers.pop(run_id, None)


# ── Public API ──────────────────────────────────────────────────────────


def record_decision(
    db: Any,  # Accepted for backward compat but NOT used — we use our own session
    *,
    run_id: str,
    node_id: str,
    block_type: str,
    execution_order: int,
    decision: str,
    decision_reason: str | None = None,
    status: str = "pending",
    started_at: datetime | None = None,
    duration_ms: float | None = None,
    memory_peak_mb: float | None = None,
    resolved_config: dict[str, Any] | None = None,
    config_sources: dict[str, str] | None = None,
    error_json: dict | None = None,
    iteration: int | None = None,
    loop_id: str | None = None,
) -> str:
    """Queue an ExecutionDecision for insertion.

    Returns a node_key string that can be passed to update_decision().
    The record is written to the database on the next flush cycle
    (every ~5 seconds) or when flush_decisions() is called explicitly.

    The `db` parameter is accepted for API compatibility but ignored —
    decisions are written via a separate database session to avoid
    contaminating the executor's main session.
    """
    kwargs: dict[str, Any] = dict(
        run_id=run_id,
        node_id=node_id,
        block_type=block_type,
        execution_order=execution_order,
        decision=decision,
        decision_reason=decision_reason,
        status=status,
        started_at=started_at,
        duration_ms=duration_ms,
        memory_peak_mb=memory_peak_mb,
        resolved_config=resolved_config,
        config_sources=config_sources,
        error_json=error_json,
        iteration=iteration,
        loop_id=loop_id,
    )

    buf = _get_buffer(run_id)
    node_key = buf.add(kwargs)

    # Auto-flush if interval has elapsed
    if buf.should_flush():
        buf.flush()

    return node_key


def update_decision(
    db: Any,  # Accepted for backward compat but NOT used
    node_key: str | None,
    **kwargs: Any,
) -> None:
    """Queue field updates for an existing decision record.

    The `node_key` is the string returned by record_decision().
    If node_key is None, this is a no-op.
    """
    if node_key is None:
        return

    # Extract run_id from the buffer that contains this key
    # The node_key format is "node_id:iteration"
    with _buffers_lock:
        for run_id, buf in _buffers.items():
            buf.update(node_key, kwargs)
            if buf.should_flush():
                buf.flush()
            return


def flush_decisions(run_id: str) -> None:
    """Force-flush all pending decisions for a run.

    Must be called in the finally block of execute_pipeline /
    execute_partial_pipeline to ensure all decisions are committed
    before the run is marked complete/failed.
    """
    buf = _get_buffer(run_id)
    buf.flush()


def cleanup_decisions(run_id: str) -> None:
    """Remove the buffer for a completed run.

    Called after flush_decisions in the finally block.
    """
    _remove_buffer(run_id)


# ── Memory measurement ──────────────────────────────────────────────────


def measure_memory_mb() -> float | None:
    """Measure current process memory usage in MB.

    Uses psutil for RSS (resident set size) which is the most accurate
    measure of actual memory consumption.  On Apple Silicon, also includes
    MLX Metal allocations which live in unified memory but may not be
    reflected in RSS immediately.

    Returns None if psutil is not available.
    """
    total_mb = None

    # RSS via psutil
    try:
        import psutil
        process = psutil.Process()
        rss_bytes = process.memory_info().rss
        total_mb = rss_bytes / (1024 * 1024)
    except (ImportError, Exception):
        return None

    # Add MLX Metal allocations (Apple Silicon GPU memory)
    try:
        import mlx.core.metal as metal
        active = metal.get_active_memory()    # bytes held by tensors
        cache = metal.get_cache_memory()      # bytes in allocator cache
        metal_mb = (active + cache) / (1024 * 1024)
        # Only add metal allocation if it's significant (> 100 MB)
        # to avoid double-counting shared unified memory
        if metal_mb > 100:
            total_mb = max(total_mb or 0, (total_mb or 0) + metal_mb * 0.5)
    except (ImportError, AttributeError):
        pass

    return round(total_mb, 1) if total_mb is not None else None
