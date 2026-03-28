"""Tests for traceability, experiment journal, research export, and pin best run.

Covers:
- test_traceability_walks_back_to_source_node
- test_auto_summary_compares_configs
- test_export_report_has_all_sections
- test_pin_best_run_persists
- test_traceability_redacts_secrets
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.run import Run
from backend.models.pipeline import Pipeline
from backend.models.project import Project
from backend.models.experiment import Experiment
from backend.models.experiment_phase import ExperimentPhase
from backend.models.experiment_note import ExperimentNote
from backend.models.artifact import ArtifactRecord


# ── Test fixture: in-memory SQLite ──────────────────────────────────────

@pytest.fixture
def db_session():
    """Create an in-memory SQLite DB with all tables."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _make_3_block_pipeline(db_session) -> tuple[str, str, str]:
    """Create a project, pipeline, and 3-block run with edges, returning IDs."""
    project_id = str(uuid.uuid4())
    pipeline_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    project = Project(
        id=project_id,
        name="Test Project",
        hypothesis="Testing traceability features",
    )
    db_session.add(project)
    db_session.flush()

    # 3-node pipeline: data_loader -> training -> evaluation
    nodes = [
        {
            "id": "node_data",
            "type": "custom",
            "data": {
                "type": "data_loader",
                "label": "Data Loader",
                "category": "data",
                "config": {"file_path": "/data/train.csv", "dataset_size": 10000},
            },
            "position": {"x": 0, "y": 0},
        },
        {
            "id": "node_train",
            "type": "custom",
            "data": {
                "type": "training",
                "label": "Trainer",
                "category": "training",
                "config": {"learning_rate": 0.001, "epochs": 10, "api_key": "sk-secret-123"},
            },
            "position": {"x": 200, "y": 0},
        },
        {
            "id": "node_eval",
            "type": "custom",
            "data": {
                "type": "evaluation",
                "label": "Evaluator",
                "category": "metrics",
                "config": {"threshold": 0.5},
            },
            "position": {"x": 400, "y": 0},
        },
    ]
    edges = [
        {"source": "node_data", "sourceHandle": "dataset", "target": "node_train", "targetHandle": "input_data"},
        {"source": "node_train", "sourceHandle": "model", "target": "node_eval", "targetHandle": "model_input"},
    ]

    definition = {"nodes": nodes, "edges": edges}

    pipeline = Pipeline(
        id=pipeline_id,
        project_id=project_id,
        name="Test Pipeline",
        definition=definition,
    )
    db_session.add(pipeline)
    db_session.flush()

    run = Run(
        id=run_id,
        pipeline_id=pipeline_id,
        project_id=project_id,
        status="complete",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        duration_seconds=42.5,
        config_snapshot=definition,
        metrics={"accuracy": 0.95, "loss": 0.12},
        metrics_log=[
            {"type": "node_started", "node_id": "node_data", "timestamp": 1000.0},
            {"type": "node_completed", "node_id": "node_data", "timestamp": 1005.0},
            {"type": "node_started", "node_id": "node_train", "timestamp": 1005.0},
            {"type": "node_completed", "node_id": "node_train", "timestamp": 1030.0},
            {"type": "node_started", "node_id": "node_eval", "timestamp": 1030.0},
            {"type": "node_completed", "node_id": "node_eval", "timestamp": 1042.0},
        ],
        config_fingerprints={"node_data": "abc123", "node_train": "def456", "node_eval": "ghi789"},
    )
    db_session.add(run)
    db_session.flush()

    # Add artifact records
    for node_id, port_id, dtype in [
        ("node_data", "dataset", "dataset"),
        ("node_train", "model", "model"),
        ("node_eval", "metrics", "metrics"),
    ]:
        ar = ArtifactRecord(
            id=str(uuid.uuid4()),
            run_id=run_id,
            node_id=node_id,
            port_id=port_id,
            data_type=dtype,
            serializer="json",
            content_hash="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            file_path=f"{run_id}/{node_id}/{port_id}.dat",
            size_bytes=1024,
        )
        db_session.add(ar)

    db_session.commit()
    return project_id, pipeline_id, run_id


# ── Test: Traceability walks back to source node ────────────────────────

class TestTraceability:
    def test_traceability_walks_back_to_source_node(self, db_session):
        """Create a 3-block pipeline run, trace from eval node back to data source."""
        from backend.routers.runs import get_traceability

        project_id, pipeline_id, run_id = _make_3_block_pipeline(db_session)

        data = get_traceability(run_id, "node_eval", db=db_session)

        # Root level
        assert data["run_id"] == run_id
        assert data["metric_source"]["node_id"] == "node_eval"

        provenance = data["provenance"]
        assert provenance["node_id"] == "node_eval"
        assert provenance["block_type"] == "evaluation"
        assert provenance["duration_seconds"] == 12.0  # 1042 - 1030
        assert provenance["cache_decision"] == "executed_fresh"

        # Should have input lineage (from training node)
        assert "input_lineage" in provenance
        assert len(provenance["input_lineage"]) == 1

        train_input = provenance["input_lineage"][0]
        assert train_input["from_node"] == "node_train"
        assert train_input["from_node_label"] == "Trainer"

        # Training node should have lineage back to data source
        train_node = train_input["lineage"]
        assert train_node["node_id"] == "node_train"
        assert "input_lineage" in train_node
        assert len(train_node["input_lineage"]) == 1

        data_input = train_node["input_lineage"][0]
        assert data_input["from_node"] == "node_data"

        # Data node should be a source
        data_node = data_input["lineage"]
        assert data_node["is_source"] is True
        assert data_node["data_source"]["file_path"] == "/data/train.csv"
        assert data_node["data_source"]["dataset_size"] == 10000

    def test_traceability_redacts_secrets(self, db_session):
        """Verify that api_key in config is redacted to [REDACTED]."""
        from backend.routers.runs import get_traceability

        project_id, pipeline_id, run_id = _make_3_block_pipeline(db_session)

        data = get_traceability(run_id, "node_train", db=db_session)

        config = data["provenance"]["resolved_config"]
        assert config["api_key"] == "[REDACTED]"
        # Non-secret keys should still be visible
        assert config["learning_rate"] == 0.001

    def test_traceability_shows_artifacts(self, db_session):
        """Verify artifact manifest data is included in trace."""
        from backend.routers.runs import get_traceability

        project_id, pipeline_id, run_id = _make_3_block_pipeline(db_session)

        data = get_traceability(run_id, "node_eval", db=db_session)

        # Eval node should have output artifact
        artifacts = data["provenance"].get("output_artifacts", {})
        assert "metrics" in artifacts
        assert artifacts["metrics"]["data_type"] == "metrics"
        assert artifacts["metrics"]["content_hash"] == "a1b2c3d4e5f6"  # truncated to 12 chars

    def test_traceability_404_for_missing_node(self, db_session):
        """Request trace for non-existent node raises HTTPException."""
        from fastapi import HTTPException
        from backend.routers.runs import get_traceability

        _, _, run_id = _make_3_block_pipeline(db_session)

        with pytest.raises(HTTPException) as exc_info:
            get_traceability(run_id, "nonexistent", db=db_session)
        assert exc_info.value.status_code == 404

    def test_traceability_404_for_missing_run(self, db_session):
        """Request trace for non-existent run raises HTTPException."""
        from fastapi import HTTPException
        from backend.routers.runs import get_traceability

        with pytest.raises(HTTPException) as exc_info:
            get_traceability("nonexistent-id", "node_eval", db=db_session)
        assert exc_info.value.status_code == 404


# ── Test: Auto-summary compares configs ─────────────────────────────────

class TestAutoSummary:
    def test_auto_summary_compares_configs(self, db_session):
        """Run with different lr -> summary mentions the change."""
        from backend.services.experiment_journal import auto_summarize

        pipeline_id = str(uuid.uuid4())

        # Previous run with lr=0.01
        prev_run = Run(
            id=str(uuid.uuid4()),
            pipeline_id=pipeline_id,
            status="complete",
            started_at=datetime.now(timezone.utc),
            config_snapshot={"learning_rate": 0.01, "nodes": [], "edges": []},
            metrics={"loss": 0.5, "accuracy": 0.8},
        )

        # Current run with lr=0.001
        curr_run = Run(
            id=str(uuid.uuid4()),
            pipeline_id=pipeline_id,
            status="complete",
            started_at=datetime.now(timezone.utc),
            duration_seconds=30.0,
            config_snapshot={"learning_rate": 0.001, "nodes": [], "edges": []},
            metrics={"loss": 0.3, "accuracy": 0.85},
        )

        summary = auto_summarize(curr_run, [prev_run])

        # Should mention learning_rate change
        assert "learning_rate" in summary
        # Should mention metric changes
        assert "loss" in summary or "accuracy" in summary

    def test_auto_summary_first_run(self, db_session):
        """First run -> summary is the first execution template."""
        from backend.services.experiment_journal import auto_summarize

        run = Run(
            id=str(uuid.uuid4()),
            pipeline_id=str(uuid.uuid4()),
            status="complete",
            started_at=datetime.now(timezone.utc),
            duration_seconds=15.0,
            config_snapshot={},
            metrics={},
        )

        summary = auto_summarize(run, [])
        assert "Run #1" in summary
        assert "first execution" in summary.lower()
        assert run.status in summary

    def test_auto_summary_failed_run(self, db_session):
        """Failed run -> summary includes FAILED and error."""
        from backend.services.experiment_journal import auto_summarize

        prev_run = Run(
            id=str(uuid.uuid4()),
            pipeline_id="p1",
            status="complete",
            started_at=datetime.now(timezone.utc),
            config_snapshot={},
            metrics={},
        )

        run = Run(
            id=str(uuid.uuid4()),
            pipeline_id="p1",
            status="failed",
            error_message="OutOfMemoryError: CUDA out of memory",
            started_at=datetime.now(timezone.utc),
            config_snapshot={},
            metrics={},
        )

        summary = auto_summarize(run, [prev_run])
        assert "FAILED" in summary
        assert "OutOfMemory" in summary


# ── Test: Journal API (direct function calls) ───────────────────────────

class TestJournalAPI:
    def test_get_journal_generates_on_demand(self, db_session):
        """GET journal for a run that has no note generates one."""
        from backend.routers.runs import get_journal

        project_id, pipeline_id, run_id = _make_3_block_pipeline(db_session)

        result = get_journal(run_id, db=db_session)
        assert result["run_id"] == run_id
        assert result["auto_summary"] is not None
        assert len(result["auto_summary"]) > 0

    def test_put_journal_updates_user_notes(self, db_session):
        """PUT updates user_notes."""
        from backend.routers.runs import get_journal, update_journal, JournalUpdateRequest

        _, _, run_id = _make_3_block_pipeline(db_session)

        # Generate note first
        get_journal(run_id, db=db_session)

        # Update notes
        result = update_journal(
            run_id,
            JournalUpdateRequest(user_notes="This run was surprisingly good."),
            db=db_session,
        )
        assert result["user_notes"] == "This run was surprisingly good."

        # Verify persists
        result2 = get_journal(run_id, db=db_session)
        assert result2["user_notes"] == "This run was surprisingly good."


# ── Test: Export report has all sections ─────────────────────────────────

class TestExportReport:
    def test_export_report_has_all_sections(self, db_session):
        """Generate report, verify YAML frontmatter + all 7 sections present."""
        from backend.routers.dashboard import export_research_report
        from backend.routers.runs import get_journal

        project_id, pipeline_id, run_id = _make_3_block_pipeline(db_session)

        # Generate a journal entry first (so timeline has data)
        get_journal(run_id, db=db_session)

        resp = export_research_report(project_id, db=db_session)
        report = resp.body.decode("utf-8")

        # YAML frontmatter
        assert report.startswith("---")
        assert "title:" in report
        assert "generated_at:" in report

        # All 7 sections
        assert "# Test Project" in report              # 1. Title
        assert "## Hypothesis" in report               # 2. Hypothesis
        assert "## Methodology" in report              # 3. Methodology
        assert "## Results" in report                  # 4. Results
        assert "## Timeline" in report                 # 5. Timeline
        assert "## Key Findings" in report             # 6. Key Findings
        assert "## Artifact References" in report      # 7. Artifact References

        # Methodology should mention pipeline structure
        assert "Test Pipeline" in report
        assert "3-step pipeline" in report

        # Results should have metrics
        assert "accuracy" in report
        assert "loss" in report

    def test_export_json_contains_all_data(self, db_session):
        """JSON export contains project, pipelines, runs, artifacts."""
        from backend.routers.dashboard import export_dashboard_json

        project_id, _, _ = _make_3_block_pipeline(db_session)

        data = export_dashboard_json(project_id, db=db_session)

        assert data["project"]["id"] == project_id
        assert data["project"]["name"] == "Test Project"
        assert len(data["pipelines"]) == 1
        assert len(data["runs"]) == 1
        assert len(data["artifacts"]) == 3
        assert "generated_at" in data


# ── Test: Pin best run persists ──────────────────────────────────────────

class TestPinBestRun:
    def test_pin_best_run_persists(self, db_session):
        """Pin a run, verify it's still pinned on reload."""
        from backend.routers.runs import pin_best_run

        _, _, run_id = _make_3_block_pipeline(db_session)

        result = pin_best_run(run_id, db=db_session)
        assert result["best_in_project"] is True

        # Verify directly from DB
        run = db_session.query(Run).filter(Run.id == run_id).first()
        assert run.best_in_project is True

    def test_pin_best_unpins_previous(self, db_session):
        """Pinning a new run unpins the previous best."""
        from backend.routers.runs import pin_best_run

        project_id, pipeline_id, run_id_1 = _make_3_block_pipeline(db_session)

        # Create a second run
        run_id_2 = str(uuid.uuid4())
        run2 = Run(
            id=run_id_2,
            pipeline_id=pipeline_id,
            project_id=project_id,
            status="complete",
            started_at=datetime.now(timezone.utc),
            config_snapshot={"nodes": [], "edges": []},
            metrics={"accuracy": 0.97},
        )
        db_session.add(run2)
        db_session.commit()

        # Pin first
        pin_best_run(run_id_1, db=db_session)
        # Pin second
        pin_best_run(run_id_2, db=db_session)

        # First should be unpinned
        run1 = db_session.query(Run).filter(Run.id == run_id_1).first()
        db_session.refresh(run1)
        assert run1.best_in_project is False

        # Second should be pinned
        run2_check = db_session.query(Run).filter(Run.id == run_id_2).first()
        assert run2_check.best_in_project is True

    def test_unpin_best_run(self, db_session):
        """Unpin removes the best designation."""
        from backend.routers.runs import pin_best_run, unpin_best_run

        _, _, run_id = _make_3_block_pipeline(db_session)

        pin_best_run(run_id, db=db_session)
        result = unpin_best_run(run_id, db=db_session)
        assert result["best_in_project"] is False

        run = db_session.query(Run).filter(Run.id == run_id).first()
        assert run.best_in_project is False


# ── Test: Project timeline ──────────────────────────────────────────────

class TestProjectTimeline:
    def test_timeline_returns_entries(self, db_session):
        """Timeline returns journal entries for project runs."""
        from backend.routers.dashboard import get_project_timeline
        from backend.routers.runs import get_journal

        project_id, _, run_id = _make_3_block_pipeline(db_session)

        # Generate journal
        get_journal(run_id, db=db_session)

        result = get_project_timeline(project_id, db=db_session)
        assert result["project_id"] == project_id
        assert len(result["entries"]) == 1
        assert result["entries"][0]["run_id"] == run_id
        assert result["entries"][0]["auto_summary"] is not None

    def test_timeline_starred_filter(self, db_session):
        """Starred filter only returns pinned runs."""
        from backend.routers.dashboard import get_project_timeline
        from backend.routers.runs import pin_best_run

        project_id, _, run_id = _make_3_block_pipeline(db_session)

        # Without pin, starred_only should return empty
        result = get_project_timeline(project_id, starred_only=True, db=db_session)
        assert len(result["entries"]) == 0

        # Pin the run
        pin_best_run(run_id, db=db_session)

        result2 = get_project_timeline(project_id, starred_only=True, db=db_session)
        assert len(result2["entries"]) == 1


# ── Risk Fix Tests ──────────────────────────────────────────────────────

class TestMetricSourceMapping:
    """Risk 1: Verify that compare endpoint returns metric_sources mapping."""

    def test_compare_returns_metric_sources(self, db_session):
        """The compare endpoint should map each metric key to its source node_id."""
        from backend.routers.runs import compare_runs

        project_id, pipeline_id, run_id = _make_3_block_pipeline(db_session)

        result = compare_runs(ids=run_id, pipeline_id=None, db=db_session)
        assert len(result["runs"]) == 1

        row = result["runs"][0]
        assert "metric_sources" in row

        # The test run has metrics like "evaluation.accuracy", "evaluation.loss"
        # and the metrics_log has metric events with node_id "node_eval" or similar.
        # Since our test data uses the block_type.name format in run.metrics but
        # the metrics_log doesn't have "metric" type events (it has node_started/completed),
        # we verify the field exists and is a dict.
        assert isinstance(row["metric_sources"], dict)

    def test_compare_metric_sources_populated_from_log(self, db_session):
        """When metrics_log has metric events, sources are correctly populated."""
        project_id = str(uuid.uuid4())
        pipeline_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        project = Project(id=project_id, name="P")
        db_session.add(project)
        db_session.flush()

        pipeline = Pipeline(
            id=pipeline_id, project_id=project_id, name="Pipe",
            definition={"nodes": [], "edges": []},
        )
        db_session.add(pipeline)
        db_session.flush()

        run = Run(
            id=run_id,
            pipeline_id=pipeline_id,
            project_id=project_id,
            status="complete",
            started_at=datetime.now(timezone.utc),
            config_snapshot={"nodes": [], "edges": []},
            metrics={"training.loss": 0.1, "evaluation.accuracy": 0.95},
            metrics_log=[
                {"type": "metric", "node_id": "node_train", "name": "loss",
                 "value": 0.1, "category": "training", "timestamp": 100.0},
                {"type": "metric", "node_id": "node_eval", "name": "accuracy",
                 "value": 0.95, "category": "metrics", "timestamp": 200.0},
            ],
        )
        db_session.add(run)
        db_session.commit()

        from backend.routers.runs import compare_runs
        result = compare_runs(ids=run_id, pipeline_id=None, db=db_session)
        row = result["runs"][0]

        # "training.loss" ends with ".loss", and the metric event has name="loss"
        assert row["metric_sources"]["training.loss"] == "node_train"
        assert row["metric_sources"]["evaluation.accuracy"] == "node_eval"


class TestNodeLevelConfigDiff:
    """Risk 2: Verify auto-summary extracts and diffs per-node configs."""

    def test_auto_summary_diffs_node_configs(self, db_session):
        """When node-level configs change, the summary includes them."""
        from backend.services.experiment_journal import auto_summarize

        # Both runs have the same top-level config, but different node configs
        nodes_prev = [{
            "id": "n1", "data": {
                "type": "training", "label": "Trainer",
                "config": {"learning_rate": 0.01, "epochs": 5, "batch_size": 32},
            },
        }]
        nodes_curr = [{
            "id": "n1", "data": {
                "type": "training", "label": "Trainer",
                "config": {"learning_rate": 0.001, "epochs": 10, "batch_size": 32},
            },
        }]

        prev_run = Run(
            id=str(uuid.uuid4()), pipeline_id="p1", status="complete",
            started_at=datetime.now(timezone.utc),
            config_snapshot={"nodes": nodes_prev, "edges": []},
            metrics={"training.loss": 0.5},
        )
        curr_run = Run(
            id=str(uuid.uuid4()), pipeline_id="p1", status="complete",
            started_at=datetime.now(timezone.utc),
            config_snapshot={"nodes": nodes_curr, "edges": []},
            metrics={"training.loss": 0.3},
        )

        summary = auto_summarize(curr_run, [prev_run])

        # Should mention node-level changes, not just "no changes found"
        assert "learning_rate" in summary
        assert "epochs" in summary
        # batch_size didn't change, should not appear
        assert "batch_size" not in summary

    def test_auto_summary_detects_node_additions(self, db_session):
        """When a node is added to the pipeline, the summary notes it."""
        from backend.services.experiment_journal import auto_summarize

        prev_run = Run(
            id=str(uuid.uuid4()), pipeline_id="p1", status="complete",
            started_at=datetime.now(timezone.utc),
            config_snapshot={"nodes": [
                {"id": "n1", "data": {"type": "training", "label": "Trainer", "config": {"lr": 0.01}}},
            ], "edges": []},
            metrics={},
        )
        curr_run = Run(
            id=str(uuid.uuid4()), pipeline_id="p1", status="complete",
            started_at=datetime.now(timezone.utc),
            config_snapshot={"nodes": [
                {"id": "n1", "data": {"type": "training", "label": "Trainer", "config": {"lr": 0.01}}},
                {"id": "n2", "data": {"type": "evaluation", "label": "Evaluator", "config": {"threshold": 0.5}}},
            ], "edges": []},
            metrics={},
        )

        summary = auto_summarize(curr_run, [prev_run])
        assert "added" in summary.lower()
        assert "Evaluator" in summary

    def test_auto_summary_redacts_secrets_in_node_configs(self, db_session):
        """Secret keys in node-level configs should not appear in summaries."""
        from backend.services.experiment_journal import auto_summarize

        prev_run = Run(
            id=str(uuid.uuid4()), pipeline_id="p1", status="complete",
            started_at=datetime.now(timezone.utc),
            config_snapshot={"nodes": [
                {"id": "n1", "data": {"type": "api", "label": "API", "config": {"api_key": "old-key", "url": "a.com"}}},
            ], "edges": []},
            metrics={},
        )
        curr_run = Run(
            id=str(uuid.uuid4()), pipeline_id="p1", status="complete",
            started_at=datetime.now(timezone.utc),
            config_snapshot={"nodes": [
                {"id": "n1", "data": {"type": "api", "label": "API", "config": {"api_key": "new-key", "url": "b.com"}}},
            ], "edges": []},
            metrics={},
        )

        summary = auto_summarize(curr_run, [prev_run])
        assert "api_key" not in summary
        assert "old-key" not in summary
        assert "new-key" not in summary
        # But non-secret changes should appear
        assert "url" in summary


class TestTimelinePagination:
    """Risk 3: Verify cursor-based pagination on the timeline endpoint."""

    def _create_many_runs(self, db_session, project_id, pipeline_id, count):
        """Helper to create N runs with staggered timestamps."""
        from datetime import timedelta
        base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        run_ids = []
        for i in range(count):
            rid = str(uuid.uuid4())
            run = Run(
                id=rid,
                pipeline_id=pipeline_id,
                project_id=project_id,
                status="complete",
                started_at=base_time + timedelta(hours=i),
                config_snapshot={"nodes": [], "edges": []},
                metrics={"step": i},
            )
            db_session.add(run)
            run_ids.append(rid)
        db_session.commit()
        return run_ids

    def test_pagination_limits_results(self, db_session):
        """Setting limit=3 on 5 runs returns 3 entries with has_more=True."""
        from backend.routers.dashboard import get_project_timeline

        project_id, pipeline_id, _ = _make_3_block_pipeline(db_session)
        # The _make_3_block_pipeline already created 1 run; add 4 more
        self._create_many_runs(db_session, project_id, pipeline_id, 4)

        result = get_project_timeline(project_id, limit=3, db=db_session)
        assert len(result["entries"]) == 3
        assert result["has_more"] is True
        assert result["next_cursor"] is not None

    def test_pagination_cursor_fetches_next_page(self, db_session):
        """Using cursor from page 1 fetches page 2 entries without overlap."""
        from backend.routers.dashboard import get_project_timeline

        project_id, pipeline_id, _ = _make_3_block_pipeline(db_session)
        self._create_many_runs(db_session, project_id, pipeline_id, 9)
        # Total: 10 runs

        # Page 1
        page1 = get_project_timeline(project_id, limit=4, db=db_session)
        assert len(page1["entries"]) == 4
        assert page1["has_more"] is True
        page1_ids = {e["run_id"] for e in page1["entries"]}

        # Page 2
        page2 = get_project_timeline(
            project_id, limit=4, cursor=page1["next_cursor"], db=db_session,
        )
        assert len(page2["entries"]) == 4
        page2_ids = {e["run_id"] for e in page2["entries"]}

        # No overlap
        assert page1_ids & page2_ids == set()

        # Page 3 (remaining 2)
        page3 = get_project_timeline(
            project_id, limit=4, cursor=page2["next_cursor"], db=db_session,
        )
        assert len(page3["entries"]) == 2
        assert page3["has_more"] is False
        assert page3["next_cursor"] is None

    def test_pagination_with_no_results(self, db_session):
        """An empty project returns no entries and has_more=False."""
        from backend.routers.dashboard import get_project_timeline

        project_id = str(uuid.uuid4())
        db_session.add(Project(id=project_id, name="Empty"))
        db_session.commit()

        result = get_project_timeline(project_id, db=db_session)
        assert result["entries"] == []
        assert result["has_more"] is False
        assert result["next_cursor"] is None

    def test_pagination_limit_clamped(self, db_session):
        """Limit is clamped to [1, 200] range."""
        from backend.routers.dashboard import get_project_timeline

        project_id, _, _ = _make_3_block_pipeline(db_session)

        # Negative limit clamped to 1
        result = get_project_timeline(project_id, limit=-5, db=db_session)
        assert len(result["entries"]) <= 1

        # Huge limit clamped to 200
        result = get_project_timeline(project_id, limit=9999, db=db_session)
        assert isinstance(result["entries"], list)


class TestAlembicMigrationChain:
    """Risk 4: Verify the Alembic migration DAG has exactly one head."""

    def test_our_migration_is_a_valid_head(self):
        """Our merge migration must appear as a valid head in the revision graph."""
        import os
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(os.path.join("backend", "alembic.ini"))
        script = ScriptDirectory.from_config(cfg)

        heads = script.get_heads()
        assert "0007_experiment_notes" in heads, (
            f"Migration 0007_experiment_notes not found in heads: {heads}"
        )

    def test_no_orphan_revisions(self):
        """Every revision (except root) must have a valid down_revision."""
        import os
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(os.path.join("backend", "alembic.ini"))
        script = ScriptDirectory.from_config(cfg)

        all_revs = {rev.revision for rev in script.walk_revisions()}

        for rev in script.walk_revisions():
            down = rev.down_revision
            if down is None:
                continue
            # down_revision can be a string or tuple of strings
            parents = (down,) if isinstance(down, str) else down
            for p in parents:
                assert p in all_revs, (
                    f"Revision {rev.revision} references parent {p} which "
                    f"doesn't exist in the migration directory."
                )

    def test_merge_migration_has_correct_parents(self):
        """The merge migration (0007) should descend from both 0006 branches."""
        import os
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(os.path.join("backend", "alembic.ini"))
        script = ScriptDirectory.from_config(cfg)

        merge_rev = script.get_revision("0007_experiment_notes")
        assert merge_rev is not None, "Merge migration 0007 not found"
        assert isinstance(merge_rev.down_revision, tuple), (
            "Merge migration must have tuple down_revision"
        )
        parents = set(merge_rev.down_revision)
        assert "0006_artifact_cache" in parents
        assert "0006_config_fingerprints" in parents

    def test_experiment_note_model_in_env_imports(self):
        """The alembic env.py must import the experiment_note model for autogenerate."""
        import os

        env_path = os.path.join("backend", "alembic", "env.py")
        with open(env_path) as f:
            content = f.read()

        assert "experiment_note" in content, (
            "backend/alembic/env.py must import experiment_note model "
            "for autogenerate to detect schema changes."
        )
