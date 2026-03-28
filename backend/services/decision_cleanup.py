"""Decision Log Retention — periodic cleanup of old execution decision records.

Configurable via environment variables:
- BLUEPRINT_DECISION_RETENTION_DAYS: Number of days to retain decisions (default: 30).
  Decisions associated with runs older than this threshold are deleted.
- BLUEPRINT_DECISION_MAX_RUNS: Maximum number of recent runs to always retain
  decisions for, regardless of age (default: 200). This prevents cleanup from
  deleting decisions for the N most recent runs even if they're older than the
  retention period.

The cleanup is idempotent and safe to call from multiple threads or processes.
It deletes in batches to avoid holding long transactions on SQLite.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, func
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models.execution_decision import ExecutionDecision
from ..models.run import Run

logger = logging.getLogger("blueprint.decision_cleanup")

# Configurable retention thresholds
RETENTION_DAYS = int(os.environ.get("BLUEPRINT_DECISION_RETENTION_DAYS", "30"))
MAX_RETAINED_RUNS = int(os.environ.get("BLUEPRINT_DECISION_MAX_RUNS", "200"))

# Batch size for deletion to avoid holding the WAL lock too long
_DELETE_BATCH_SIZE = 500


def cleanup_old_decisions(db: Session | None = None) -> dict:
    """Delete execution decisions for runs older than the retention threshold.

    Always retains the most recent MAX_RETAINED_RUNS runs' decisions regardless
    of age.  Returns a summary dict with counts of deleted and retained records.

    Args:
        db: Optional active session.  If ``None``, opens and closes its own session.

    Returns:
        ``{"deleted": int, "retained": int, "cutoff": str, "protected_runs": int}``
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        return _do_cleanup(db)
    except Exception as exc:
        logger.warning("Decision cleanup failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return {"deleted": 0, "retained": 0, "error": str(exc)}
    finally:
        if own_session:
            db.close()


def _do_cleanup(db: Session) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)

    # Step 1: Identify run_ids that are unconditionally protected
    # (the N most recent runs by started_at, regardless of age)
    protected_subq = (
        select(Run.id)
        .where(Run.started_at.isnot(None))
        .order_by(Run.started_at.desc())
        .limit(MAX_RETAINED_RUNS)
    )
    protected_ids = {row[0] for row in db.execute(protected_subq).fetchall()}

    # Step 2: Find run_ids with decisions that are older than the cutoff
    # AND not in the protected set
    old_run_ids_q = (
        select(Run.id)
        .where(Run.started_at < cutoff)
        .where(Run.id.notin_(protected_ids) if protected_ids else True)
    )
    old_run_ids = {row[0] for row in db.execute(old_run_ids_q).fetchall()}

    if not old_run_ids:
        # Count total retained
        total_retained = db.execute(
            select(func.count()).select_from(ExecutionDecision)
        ).scalar() or 0
        return {
            "deleted": 0,
            "retained": total_retained,
            "cutoff": cutoff.isoformat(),
            "protected_runs": len(protected_ids),
        }

    # Step 3: Delete in batches
    total_deleted = 0
    old_run_list = list(old_run_ids)

    for i in range(0, len(old_run_list), _DELETE_BATCH_SIZE):
        batch = old_run_list[i : i + _DELETE_BATCH_SIZE]
        result = db.execute(
            delete(ExecutionDecision).where(ExecutionDecision.run_id.in_(batch))
        )
        total_deleted += result.rowcount
        db.commit()

    total_retained = db.execute(
        select(func.count()).select_from(ExecutionDecision)
    ).scalar() or 0

    logger.info(
        "Decision cleanup: deleted %d records across %d old runs "
        "(cutoff=%s, protected=%d runs, retained=%d records)",
        total_deleted,
        len(old_run_ids),
        cutoff.isoformat(),
        len(protected_ids),
        total_retained,
    )

    return {
        "deleted": total_deleted,
        "retained": total_retained,
        "cutoff": cutoff.isoformat(),
        "protected_runs": len(protected_ids),
        "expired_runs": len(old_run_ids),
    }


def get_decision_stats(db: Session | None = None) -> dict:
    """Return statistics about the decision log.

    Useful for admin monitoring and UI display.
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()

    try:
        total = db.execute(
            select(func.count()).select_from(ExecutionDecision)
        ).scalar() or 0

        distinct_runs = db.execute(
            select(func.count(func.distinct(ExecutionDecision.run_id)))
        ).scalar() or 0

        oldest = db.execute(
            select(func.min(ExecutionDecision.timestamp))
        ).scalar()

        newest = db.execute(
            select(func.max(ExecutionDecision.timestamp))
        ).scalar()

        return {
            "total_decisions": total,
            "distinct_runs": distinct_runs,
            "oldest": oldest.isoformat() if oldest else None,
            "newest": newest.isoformat() if newest else None,
            "retention_days": RETENTION_DAYS,
            "max_retained_runs": MAX_RETAINED_RUNS,
        }
    finally:
        if own_session:
            db.close()
