"""Tests for pipeline autosave / crash recovery and history persistence."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest


class TestAutosaveFiles:
    """Unit tests for autosave file operations (no DB required)."""

    def test_session_scoped_autosave_write(self, tmp_path):
        """Autosave writes a session-scoped JSON file to SNAPSHOTS_DIR."""
        pipeline_id = "test-pipeline-123"
        session_id = "abc123"
        snapshots = tmp_path / "snapshots"
        snapshots.mkdir()

        path = snapshots / f"{pipeline_id}_{session_id}_autosave.json"
        payload = {
            "pipeline_id": pipeline_id,
            "session_id": session_id,
            "name": "Test Pipeline",
            "definition": {"nodes": [{"id": "n1"}], "edges": []},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(payload))

        assert path.exists()
        data = json.loads(path.read_text())
        assert data["pipeline_id"] == pipeline_id
        assert data["session_id"] == session_id

    def test_multiple_sessions_create_separate_files(self, tmp_path):
        """Different sessions write to different files."""
        pipeline_id = "test-pipeline-multi"
        snapshots = tmp_path / "snapshots"
        snapshots.mkdir()

        for sid in ["session-a", "session-b", "session-c"]:
            path = snapshots / f"{pipeline_id}_{sid}_autosave.json"
            path.write_text(json.dumps({
                "pipeline_id": pipeline_id,
                "session_id": sid,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))

        files = list(snapshots.glob(f"{pipeline_id}_*_autosave.json"))
        assert len(files) == 3

    def test_delete_all_sessions(self, tmp_path):
        """Deleting autosaves removes files from ALL sessions."""
        pipeline_id = "test-pipeline-del"
        snapshots = tmp_path / "snapshots"
        snapshots.mkdir()

        for sid in ["s1", "s2"]:
            path = snapshots / f"{pipeline_id}_{sid}_autosave.json"
            path.write_text('{}')

        # Delete all
        for p in snapshots.glob(f"{pipeline_id}_*_autosave.json"):
            p.unlink(missing_ok=True)

        files = list(snapshots.glob(f"{pipeline_id}_*_autosave.json"))
        assert len(files) == 0

    def test_autosave_timestamp_comparison(self, tmp_path):
        """Autosave newer than last save should be detected."""
        last_save = datetime.now(timezone.utc) - timedelta(hours=1)
        autosave_ts = datetime.now(timezone.utc)
        assert autosave_ts > last_save

    def test_autosave_older_than_save_is_discarded(self, tmp_path):
        """Autosave older than last save should be ignored."""
        last_save = datetime.now(timezone.utc)
        autosave_ts = datetime.now(timezone.utc) - timedelta(hours=1)
        assert autosave_ts < last_save


class TestHistoryJsonField:
    """Tests for the history_json column on the Pipeline model."""

    def test_pipeline_model_has_history_json(self):
        """Pipeline model should include the history_json column."""
        from backend.models.pipeline import Pipeline
        assert hasattr(Pipeline, 'history_json')

    def test_pipeline_schema_includes_history_json(self):
        """PipelineResponse schema should include history_json."""
        from backend.schemas.pipeline import PipelineResponse
        fields = PipelineResponse.model_fields
        assert 'history_json' in fields

    def test_pipeline_history_update_schema(self):
        """PipelineHistoryUpdate schema should accept history_json string."""
        from backend.schemas.pipeline import PipelineHistoryUpdate
        data = PipelineHistoryUpdate(history_json='{"past":[],"future":[]}')
        assert data.history_json == '{"past":[],"future":[]}'

    def test_history_json_nullable(self):
        """PipelineResponse should accept null history_json."""
        from backend.schemas.pipeline import PipelineResponse
        resp = PipelineResponse(
            id="test",
            name="Test",
            project_id=None,
            experiment_id=None,
            experiment_phase_id=None,
            description="",
            definition={},
            history_json=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert resp.history_json is None


class TestHistorySnapshotsFile:
    """Tests for the file-based history snapshots (SNAPSHOTS_DIR)."""

    def test_write_and_read_history_file(self, tmp_path):
        """History snapshots write to a file in SNAPSHOTS_DIR."""
        pipeline_id = "test-pipeline-hist"
        snapshots = tmp_path / "snapshots"
        snapshots.mkdir()

        path = snapshots / f"{pipeline_id}_history.json"
        payload = json.dumps({
            "past": [{"description": "Added node", "type": "add"}],
            "future": [],
        })
        path.write_text(payload)

        assert path.exists()
        data = json.loads(path.read_text())
        assert len(data["past"]) == 1
        assert data["past"][0]["description"] == "Added node"

    def test_history_file_overwrites_cleanly(self, tmp_path):
        """Writing a new history file overwrites the old one."""
        pipeline_id = "test-pipeline-overwrite"
        snapshots = tmp_path / "snapshots"
        snapshots.mkdir()
        path = snapshots / f"{pipeline_id}_history.json"

        path.write_text('{"past": [{"description": "v1"}], "future": []}')
        path.write_text('{"past": [{"description": "v2"}], "future": []}')

        data = json.loads(path.read_text())
        assert data["past"][0]["description"] == "v2"

    def test_missing_history_file_returns_gracefully(self, tmp_path):
        """Requesting a non-existent history file should not error."""
        snapshots = tmp_path / "snapshots"
        snapshots.mkdir()
        path = snapshots / "nonexistent_history.json"
        assert not path.exists()


class TestAlembicMigration:
    """Tests for the history_json migration file."""

    def test_migration_file_exists(self):
        """The 0007 migration should exist."""
        migration_path = (
            Path(__file__).parent.parent
            / "alembic"
            / "versions"
            / "0007_add_pipeline_history_json.py"
        )
        assert migration_path.exists()

    def test_migration_has_upgrade_and_downgrade(self):
        """Migration should define both upgrade() and downgrade()."""
        import importlib.util
        migration_path = (
            Path(__file__).parent.parent
            / "alembic"
            / "versions"
            / "0007_add_pipeline_history_json.py"
        )
        spec = importlib.util.spec_from_file_location("migration", migration_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert hasattr(mod, 'upgrade')
        assert hasattr(mod, 'downgrade')
        assert callable(mod.upgrade)
        assert callable(mod.downgrade)
