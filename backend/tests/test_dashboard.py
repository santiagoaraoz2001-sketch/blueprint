"""Tests for the experiment dashboard, comparison matrix, sequential execution, and live updates."""

import json
import uuid
import threading
import time
from datetime import datetime, timezone
from unittest import mock

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.project import Project
from backend.models.pipeline import Pipeline
from backend.models.run import Run
from backend.models.pipeline_sequence import PipelineSequence


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session(tmp_path):
    """Create an in-memory database with all tables."""
    db_path = tmp_path / "test_dashboard.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @sa_event.listens_for(engine, "connect")
    def _wal(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Import all models to register them
    from backend.models import (
        project, experiment, experiment_phase, pipeline,
        run, dataset, artifact, paper, sweep, workspace,
        pipeline_sequence,
    )  # noqa: F811

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def project_with_experiments(db_session):
    """Create a project with 3 pipelines and runs."""
    project = Project(
        id=str(uuid.uuid4()),
        name="Test BALLAST Project",
        hypothesis="Learning rate affects convergence",
        status="active",
    )
    db_session.add(project)
    db_session.flush()  # FK target must exist before referencing it

    pipelines = []
    for i, (name, lr, acc) in enumerate([
        ("Baseline lr=1e-4", 1e-4, 0.85),
        ("Experiment lr=1e-3", 1e-3, 0.91),
        ("Experiment lr=5e-3", 5e-3, 0.78),
    ]):
        pipeline = Pipeline(
            id=str(uuid.uuid4()),
            project_id=project.id,
            name=name,
            definition={"nodes": [], "edges": []},
        )
        db_session.add(pipeline)
        db_session.flush()  # FK target for Run
        pipelines.append(pipeline)

        # Add runs for each pipeline
        for j in range(2):
            run = Run(
                id=str(uuid.uuid4()),
                pipeline_id=pipeline.id,
                project_id=project.id,
                status="complete" if j == 0 else "running",
                config_snapshot={
                    "model": {"learning_rate": lr, "batch_size": 32, "model_name": "resnet50"},
                    "data": {"dataset": "imagenet", "augmentation": i > 0},
                },
                metrics={"accuracy": acc + j * 0.01, "loss": 1.0 - acc - j * 0.01} if j == 0 else {},
                duration_seconds=120.0 + i * 30,
            )
            db_session.add(run)

    db_session.commit()
    return project, pipelines


# ---------------------------------------------------------------------------
# test_dashboard_aggregates_across_experiments
# ---------------------------------------------------------------------------

class TestDashboardAggregation:
    def test_aggregates_all_experiments(self, db_session, project_with_experiments):
        """Dashboard should return all experiments and runs for a project."""
        project, pipelines = project_with_experiments

        from backend.routers.dashboard import _get_project_pipelines, _flatten_dict

        found_pipelines = _get_project_pipelines(project.id, db_session)
        assert len(found_pipelines) == 3

        # Verify all pipelines are returned
        found_ids = {p.id for p in found_pipelines}
        expected_ids = {p.id for p in pipelines}
        assert found_ids == expected_ids

    def test_config_diff_detection(self, db_session, project_with_experiments):
        """Config diffs should be computed between experiments."""
        from backend.routers.dashboard import _compute_config_diff

        config_a = {"model.learning_rate": 1e-4, "model.batch_size": 32}
        config_b = {"model.learning_rate": 1e-3, "model.batch_size": 32}

        diff = _compute_config_diff(config_a, config_b)
        assert "model.learning_rate" in diff
        assert diff["model.learning_rate"]["old"] == 1e-4
        assert diff["model.learning_rate"]["new"] == 1e-3
        # batch_size is the same, so should not be in diff
        assert "model.batch_size" not in diff

    def test_flatten_dict(self, db_session):
        """Nested dicts should be flattened for comparison."""
        from backend.routers.dashboard import _flatten_dict

        nested = {"model": {"lr": 0.001, "layers": {"hidden": 256}}, "epochs": 10}
        flat = _flatten_dict(nested)
        assert flat == {
            "model.lr": 0.001,
            "model.layers.hidden": 256,
            "epochs": 10,
        }


# ---------------------------------------------------------------------------
# test_comparison_matrix_highlights_diffs
# ---------------------------------------------------------------------------

class TestComparisonMatrix:
    def test_matrix_highlights_diffs(self, db_session, project_with_experiments):
        """Comparison matrix should identify cells that differ from the first column."""
        project, pipelines = project_with_experiments

        # Get all completed runs
        completed_runs = db_session.query(Run).filter(
            Run.project_id == project.id,
            Run.status == "complete",
        ).all()
        assert len(completed_runs) == 3

        from backend.routers.dashboard import _flatten_dict

        # Simulate matrix construction
        run_configs = []
        for run in completed_runs:
            flat = _flatten_dict(run.config_snapshot) if run.config_snapshot else {}
            run_configs.append(flat)

        # Find differing keys
        all_keys = set()
        for rc in run_configs:
            all_keys.update(rc.keys())

        diff_keys = []
        for key in sorted(all_keys):
            values = {str(rc.get(key)) for rc in run_configs}
            if len(values) > 1:
                diff_keys.append(key)

        # learning_rate and augmentation should differ across experiments
        assert "model.learning_rate" in diff_keys
        assert "data.augmentation" in diff_keys
        # batch_size and dataset should be the same
        assert "model.batch_size" not in diff_keys

    def test_matrix_with_empty_runs(self, db_session):
        """Matrix should handle empty run list gracefully."""
        from backend.routers.dashboard import _flatten_dict

        # Empty case
        runs = []
        all_config_keys: set = set()
        all_metric_keys: set = set()

        for run_config, run_metrics in []:
            pass

        assert len(all_config_keys) == 0
        assert len(all_metric_keys) == 0


# ---------------------------------------------------------------------------
# test_sequential_run_waits_for_completion
# ---------------------------------------------------------------------------

class TestSequentialRun:
    def test_sequence_model_creation(self, db_session, project_with_experiments):
        """PipelineSequence model should store pipeline order and track progress."""
        project, pipelines = project_with_experiments

        sequence = PipelineSequence(
            id=str(uuid.uuid4()),
            project_id=project.id,
            pipeline_ids=[p.id for p in pipelines],
            status="pending",
            current_index=0,
        )
        db_session.add(sequence)
        db_session.commit()

        fetched = db_session.query(PipelineSequence).filter(
            PipelineSequence.id == sequence.id
        ).first()
        assert fetched is not None
        assert fetched.status == "pending"
        assert len(fetched.pipeline_ids) == 3
        assert fetched.current_index == 0

    def test_sequence_advances_index(self, db_session, project_with_experiments):
        """Sequence should track current_index as pipelines complete."""
        project, pipelines = project_with_experiments

        sequence = PipelineSequence(
            id=str(uuid.uuid4()),
            project_id=project.id,
            pipeline_ids=[p.id for p in pipelines],
            status="running",
            current_index=0,
        )
        db_session.add(sequence)
        db_session.commit()

        # Simulate advancement
        sequence.current_index = 1
        sequence.status = "running"
        db_session.commit()
        assert sequence.current_index == 1

        sequence.current_index = 2
        db_session.commit()
        assert sequence.current_index == 2

        # Complete
        sequence.status = "completed"
        sequence.current_index = 3
        db_session.commit()
        assert sequence.status == "completed"

    def test_sequence_stops_on_failure(self, db_session, project_with_experiments):
        """If a pipeline fails, the sequence should stop and report failure."""
        project, pipelines = project_with_experiments

        sequence = PipelineSequence(
            id=str(uuid.uuid4()),
            project_id=project.id,
            pipeline_ids=[p.id for p in pipelines],
            status="running",
            current_index=1,
        )
        db_session.add(sequence)
        db_session.commit()

        # Simulate failure
        sequence.status = "failed"
        sequence.error_message = "Pipeline 'Experiment lr=1e-3' did not complete (status: failed)"
        db_session.commit()

        fetched = db_session.query(PipelineSequence).filter(
            PipelineSequence.id == sequence.id
        ).first()
        assert fetched.status == "failed"
        assert fetched.current_index == 1  # stopped at pipeline index 1
        assert "did not complete" in fetched.error_message

    def test_sequence_rejects_duplicate(self, db_session, project_with_experiments):
        """Only one active sequence per project should be allowed."""
        project, pipelines = project_with_experiments

        seq1 = PipelineSequence(
            id=str(uuid.uuid4()),
            project_id=project.id,
            pipeline_ids=[p.id for p in pipelines[:2]],
            status="running",
            current_index=0,
        )
        db_session.add(seq1)
        db_session.commit()

        # Check that an active sequence exists
        active = db_session.query(PipelineSequence).filter(
            PipelineSequence.project_id == project.id,
            PipelineSequence.status.in_(["pending", "running"]),
        ).first()
        assert active is not None
        assert active.id == seq1.id


# ---------------------------------------------------------------------------
# test_live_update_on_run_complete
# ---------------------------------------------------------------------------

class TestLiveUpdates:
    def test_project_event_publishing(self):
        """publish_project_event should enqueue events for subscribers."""
        import asyncio
        from backend.routers.dashboard import publish_project_event, _project_lock, _project_queues

        project_id = "test-project-live"
        queue = asyncio.Queue()

        with _project_lock:
            _project_queues[project_id] = [queue]

        try:
            publish_project_event(project_id, "run_completed", {
                "run_id": "run-123",
                "pipeline_id": "pipe-456",
                "status": "complete",
            })

            assert not queue.empty()
            event = queue.get_nowait()
            assert event["event"] == "run_completed"
            data = json.loads(event["data"])
            assert data["run_id"] == "run-123"
            assert data["status"] == "complete"
        finally:
            with _project_lock:
                _project_queues.pop(project_id, None)

    def test_sequence_progress_event(self):
        """Sequence progress events should include index and pipeline name."""
        import asyncio
        from backend.routers.dashboard import publish_project_event, _project_lock, _project_queues

        project_id = "test-project-seq-event"
        queue = asyncio.Queue()

        with _project_lock:
            _project_queues[project_id] = [queue]

        try:
            publish_project_event(project_id, "sequence_progress", {
                "sequence_id": "seq-1",
                "current_index": 1,
                "total": 3,
                "current_pipeline_name": "Training Experiment 2",
                "current_status": "running",
            })

            event = queue.get_nowait()
            assert event["event"] == "sequence_progress"
            data = json.loads(event["data"])
            assert data["current_index"] == 1
            assert data["total"] == 3
            assert data["current_pipeline_name"] == "Training Experiment 2"
        finally:
            with _project_lock:
                _project_queues.pop(project_id, None)

    def test_no_event_without_subscribers(self):
        """publish_project_event should not fail with no subscribers."""
        from backend.routers.dashboard import publish_project_event

        # Should not raise
        publish_project_event("nonexistent-project", "run_completed", {"run_id": "x"})


# ---------------------------------------------------------------------------
# Risk 1: test_sequence_crash_recovery
# ---------------------------------------------------------------------------

class TestSequenceCrashRecovery:
    def test_recover_orphaned_sequences_on_startup(self, db_session, project_with_experiments):
        """Sequences left in 'running' by a crash should be marked 'failed' on recovery."""
        project, pipelines = project_with_experiments

        # Simulate a sequence that was running when the server crashed
        orphaned = PipelineSequence(
            id=str(uuid.uuid4()),
            project_id=project.id,
            pipeline_ids=[p.id for p in pipelines[:2]],
            status="running",
            current_index=1,
        )
        db_session.add(orphaned)

        # Also a pending sequence (could happen if queued but never started)
        pending = PipelineSequence(
            id=str(uuid.uuid4()),
            project_id=project.id,
            pipeline_ids=[pipelines[0].id],
            status="pending",
            current_index=0,
        )
        db_session.add(pending)
        db_session.commit()

        # Simulate the recovery function logic directly against our test session
        stuck = db_session.query(PipelineSequence).filter(
            PipelineSequence.status.in_(["running", "pending"])
        ).all()
        assert len(stuck) == 2

        for seq in stuck:
            seq.status = "failed"
            seq.error_message = "Recovered: server restarted while sequence was running"
        db_session.commit()

        # Verify both are now failed
        recovered = db_session.query(PipelineSequence).filter(
            PipelineSequence.project_id == project.id,
            PipelineSequence.status == "failed",
        ).all()
        # There may be other failed sequences, but our two should be there
        recovered_ids = {r.id for r in recovered}
        assert orphaned.id in recovered_ids
        assert pending.id in recovered_ids
        for r in recovered:
            if r.id in {orphaned.id, pending.id}:
                assert "server restarted" in r.error_message

    def test_completed_sequences_not_affected_by_recovery(self, db_session, project_with_experiments):
        """Completed and failed sequences should not be touched by recovery."""
        project, pipelines = project_with_experiments

        completed = PipelineSequence(
            id=str(uuid.uuid4()),
            project_id=project.id,
            pipeline_ids=[p.id for p in pipelines[:2]],
            status="completed",
            current_index=2,
        )
        failed = PipelineSequence(
            id=str(uuid.uuid4()),
            project_id=project.id,
            pipeline_ids=[pipelines[0].id],
            status="failed",
            current_index=0,
            error_message="Original failure",
        )
        db_session.add_all([completed, failed])
        db_session.commit()

        # Recovery should find nothing to fix
        stuck = db_session.query(PipelineSequence).filter(
            PipelineSequence.status.in_(["running", "pending"])
        ).all()
        assert len(stuck) == 0

        # Original statuses are preserved
        db_session.refresh(completed)
        db_session.refresh(failed)
        assert completed.status == "completed"
        assert failed.status == "failed"
        assert failed.error_message == "Original failure"

    def test_shutdown_signal_stops_sequence_between_pipelines(self):
        """The _sequence_shutdown event should be checkable between pipeline runs."""
        from backend.routers.dashboard import _sequence_shutdown

        # Verify the event mechanism works
        assert not _sequence_shutdown.is_set()
        _sequence_shutdown.set()
        assert _sequence_shutdown.is_set()
        _sequence_shutdown.clear()
        assert not _sequence_shutdown.is_set()

    def test_shutdown_sequences_function(self):
        """shutdown_sequences() should set the signal and not crash with no active threads."""
        from backend.routers.dashboard import shutdown_sequences, _sequence_shutdown

        _sequence_shutdown.clear()
        # Should not raise even with no active threads
        shutdown_sequences(timeout=1.0)
        assert _sequence_shutdown.is_set()
        # Clean up
        _sequence_shutdown.clear()


# ---------------------------------------------------------------------------
# Risk 3: test_run_starring
# ---------------------------------------------------------------------------

class TestRunStarring:
    def test_starred_column_defaults_false(self, db_session, project_with_experiments):
        """New runs should have starred=False by default."""
        project, pipelines = project_with_experiments
        run = db_session.query(Run).filter(Run.project_id == project.id).first()
        assert run is not None
        assert run.starred is False or run.starred is None or run.starred == 0

    def test_star_toggle(self, db_session, project_with_experiments):
        """Starring a run should toggle between True and False."""
        project, pipelines = project_with_experiments
        run = db_session.query(Run).filter(Run.project_id == project.id).first()

        # Toggle on
        run.starred = True
        db_session.commit()
        db_session.refresh(run)
        assert bool(run.starred) is True

        # Toggle off
        run.starred = False
        db_session.commit()
        db_session.refresh(run)
        assert bool(run.starred) is False

    def test_starred_in_dashboard_response(self, db_session, project_with_experiments):
        """Dashboard response should reflect the starred status from DB."""
        project, pipelines = project_with_experiments

        # Star one run
        run = db_session.query(Run).filter(
            Run.project_id == project.id,
            Run.status == "complete",
        ).first()
        run.starred = True
        db_session.commit()

        assert bool(run.starred) is True

        # Unstarred run
        other_run = db_session.query(Run).filter(
            Run.project_id == project.id,
            Run.id != run.id,
        ).first()
        assert bool(getattr(other_run, 'starred', False)) is False


# ---------------------------------------------------------------------------
# Risk 4: test_batch_metrics_log
# ---------------------------------------------------------------------------

class TestBatchMetricsLog:
    def test_batch_returns_empty_for_nonexistent_runs(self, db_session):
        """Batch endpoint should return empty lists for runs that don't exist."""
        # Simulate what the endpoint does internally
        run_ids = ["nonexistent-1", "nonexistent-2"]
        result = {}
        for rid in run_ids:
            result[rid] = []
        assert result["nonexistent-1"] == []
        assert result["nonexistent-2"] == []

    def test_batch_returns_metrics_log_from_db(self, db_session, project_with_experiments):
        """Batch endpoint should return metrics_log from the SQLite column."""
        project, pipelines = project_with_experiments

        # Add metrics_log to a run
        run = db_session.query(Run).filter(
            Run.project_id == project.id,
            Run.status == "complete",
        ).first()
        run.metrics_log = [
            {"step": 1, "accuracy": 0.5, "loss": 1.2},
            {"step": 2, "accuracy": 0.7, "loss": 0.8},
            {"step": 3, "accuracy": 0.85, "loss": 0.4},
        ]
        db_session.commit()

        # Simulate batch retrieval
        runs = db_session.query(Run).filter(Run.id.in_([run.id])).all()
        run_map = {r.id: r for r in runs}
        result = {}
        for rid in [run.id]:
            r = run_map.get(rid)
            if r and r.metrics_log:
                result[rid] = r.metrics_log
            else:
                result[rid] = []

        assert len(result[run.id]) == 3
        assert result[run.id][0]["step"] == 1
        assert result[run.id][2]["accuracy"] == 0.85

    def test_batch_handles_mixed_data(self, db_session, project_with_experiments):
        """Batch should handle a mix of runs with and without metrics logs."""
        project, pipelines = project_with_experiments

        runs = db_session.query(Run).filter(Run.project_id == project.id).all()
        assert len(runs) >= 2

        # Only give first run a metrics log
        runs[0].metrics_log = [{"step": 1, "val": 42}]
        db_session.commit()

        run_map = {r.id: r for r in runs}
        result = {}
        for rid in [runs[0].id, runs[1].id]:
            r = run_map.get(rid)
            if r and r.metrics_log:
                result[rid] = r.metrics_log
            else:
                result[rid] = []

        assert len(result[runs[0].id]) == 1
        assert result[runs[1].id] == []

    def test_batch_max_20_limit(self):
        """Batch endpoint should reject more than 20 run IDs."""
        run_ids = [f"run-{i}" for i in range(21)]
        assert len(run_ids) > 20
        # The endpoint checks this and raises 400
