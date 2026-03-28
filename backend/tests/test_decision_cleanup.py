"""Tests for the decision cleanup service (Risk 2 fix)."""

import pytest
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.run import Run
from backend.models.execution_decision import ExecutionDecision
from backend.services import decision_cleanup


@pytest.fixture
def db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _make_run(db, run_id: str, started_at: datetime) -> Run:
    """Create a run record."""
    run = Run(
        id=run_id,
        pipeline_id="pipe-1",
        status="complete",
        started_at=started_at,
    )
    db.add(run)
    db.commit()
    return run


def _make_decision(db, run_id: str, node_id: str = "node-1") -> ExecutionDecision:
    """Create a decision record."""
    d = ExecutionDecision(
        id=str(uuid.uuid4()),
        run_id=run_id,
        node_id=node_id,
        decision="execute",
        reason="test",
        timestamp=datetime.now(timezone.utc),
    )
    db.add(d)
    db.commit()
    return d


class TestCleanupOldDecisions:
    """Test the cleanup_old_decisions function."""

    def test_no_decisions_is_noop(self, db):
        """Empty database returns zero deleted."""
        result = decision_cleanup.cleanup_old_decisions(db)
        assert result["deleted"] == 0
        assert result["retained"] == 0

    def test_recent_decisions_kept(self, db):
        """Decisions from recent runs are not deleted."""
        now = datetime.now(timezone.utc)
        _make_run(db, "run-1", now - timedelta(days=1))
        _make_decision(db, "run-1")
        _make_decision(db, "run-1", "node-2")

        result = decision_cleanup.cleanup_old_decisions(db)
        assert result["deleted"] == 0
        assert result["retained"] == 2

    def test_old_decisions_deleted(self, db, monkeypatch):
        """Decisions from runs older than retention period are deleted."""
        monkeypatch.setattr(decision_cleanup, "RETENTION_DAYS", 7)
        monkeypatch.setattr(decision_cleanup, "MAX_RETAINED_RUNS", 0)

        now = datetime.now(timezone.utc)

        # Old run (10 days ago)
        _make_run(db, "old-run", now - timedelta(days=10))
        _make_decision(db, "old-run")
        _make_decision(db, "old-run", "node-2")

        # Recent run (1 day ago)
        _make_run(db, "new-run", now - timedelta(days=1))
        _make_decision(db, "new-run")

        result = decision_cleanup.cleanup_old_decisions(db)
        assert result["deleted"] == 2
        assert result["retained"] == 1

    def test_protected_runs_never_deleted(self, db, monkeypatch):
        """The most recent N runs are always protected regardless of age."""
        monkeypatch.setattr(decision_cleanup, "RETENTION_DAYS", 1)
        monkeypatch.setattr(decision_cleanup, "MAX_RETAINED_RUNS", 5)

        now = datetime.now(timezone.utc)

        # Create 3 old runs
        for i in range(3):
            run_id = f"protected-{i}"
            _make_run(db, run_id, now - timedelta(days=30 + i))
            _make_decision(db, run_id)

        result = decision_cleanup.cleanup_old_decisions(db)
        # All 3 runs are within the top 5 most recent → protected
        assert result["deleted"] == 0
        assert result["retained"] == 3
        assert result["protected_runs"] == 3

    def test_mixed_protection_and_cleanup(self, db, monkeypatch):
        """Some runs are protected, others are cleaned up."""
        monkeypatch.setattr(decision_cleanup, "RETENTION_DAYS", 7)
        monkeypatch.setattr(decision_cleanup, "MAX_RETAINED_RUNS", 2)

        now = datetime.now(timezone.utc)

        # 2 recent runs → protected by recency
        _make_run(db, "recent-1", now - timedelta(days=1))
        _make_decision(db, "recent-1")
        _make_run(db, "recent-2", now - timedelta(days=2))
        _make_decision(db, "recent-2")

        # 2 old runs → one protected by MAX_RETAINED_RUNS, one deleted
        # Actually, MAX_RETAINED_RUNS=2 means top 2 by started_at are protected
        # recent-1 and recent-2 are the top 2
        _make_run(db, "old-1", now - timedelta(days=20))
        _make_decision(db, "old-1")
        _make_decision(db, "old-1", "node-2")

        result = decision_cleanup.cleanup_old_decisions(db)
        assert result["deleted"] == 2  # old-1's 2 decisions
        assert result["retained"] == 2  # recent-1 + recent-2


class TestGetDecisionStats:
    """Test the get_decision_stats function."""

    def test_empty_stats(self, db):
        """Empty database returns zero counts."""
        stats = decision_cleanup.get_decision_stats(db)
        assert stats["total_decisions"] == 0
        assert stats["distinct_runs"] == 0
        assert stats["oldest"] is None
        assert stats["newest"] is None

    def test_stats_with_data(self, db):
        """Stats reflect actual data."""
        now = datetime.now(timezone.utc)
        _make_run(db, "run-1", now - timedelta(days=1))
        _make_run(db, "run-2", now)
        _make_decision(db, "run-1")
        _make_decision(db, "run-1", "node-2")
        _make_decision(db, "run-2")

        stats = decision_cleanup.get_decision_stats(db)
        assert stats["total_decisions"] == 3
        assert stats["distinct_runs"] == 2
        assert stats["oldest"] is not None
        assert stats["newest"] is not None
        assert stats["retention_days"] == decision_cleanup.RETENTION_DAYS
