"""Tests for the artifact cache system (backend/engine/artifacts.py)
and executor integration (backend/engine/executor.py)."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from backend.engine.artifacts import (
    ArtifactCorruptionError,
    ArtifactManifest,
    ArtifactStore,
)


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(base_path=tmp_path)


# ── Core store/load ──────────────────────────────────────────────────────


def test_store_and_load_text(store: ArtifactStore):
    """Store a text artifact, load it back, verify content matches."""
    manifest = store.store("node_1", "output", "run_1", "hello", "text")
    assert manifest.data_type == "text"
    assert manifest.serializer == "text"
    assert manifest.size_bytes > 0

    loaded = store.load(manifest)
    assert loaded == "hello"


def test_store_and_load_json(store: ArtifactStore):
    """Store a JSON dict artifact, load it back, verify equality."""
    data = {"accuracy": 0.95, "loss": 0.05, "epochs": 10}
    manifest = store.store("node_2", "metrics", "run_1", data, "metrics")
    assert manifest.data_type == "metrics"
    assert manifest.serializer == "json"

    loaded = store.load(manifest)
    assert loaded == data


# ── Integrity verification ───────────────────────────────────────────────


def test_hash_verification_catches_corruption(store: ArtifactStore):
    """Manually corrupt the artifact file and verify load raises ArtifactCorruptionError."""
    manifest = store.store("node_3", "output", "run_2", "important data", "text")

    # Corrupt the file on disk
    abs_path = store.base_path / manifest.file_path
    abs_path.write_bytes(b"corrupted content")

    with pytest.raises(ArtifactCorruptionError):
        store.load(manifest)

    # verify() should also return False
    assert store.verify(manifest) is False


# ── Previews ─────────────────────────────────────────────────────────────


def test_preview_text(store: ArtifactStore):
    """Verify text preview contains 'text' and 'length' keys."""
    manifest = store.store("node_4", "output", "run_3", "hello world", "text")
    assert manifest.preview is not None
    assert "text" in manifest.preview
    assert "length" in manifest.preview
    assert manifest.preview["text"] == "hello world"
    assert manifest.preview["length"] == 11


def test_preview_dataset(store: ArtifactStore):
    """Verify dataset preview contains 'shape' and 'sample' keys."""
    data = [
        {"name": "Alice", "score": 95},
        {"name": "Bob", "score": 87},
        {"name": "Charlie", "score": 91},
        {"name": "Diana", "score": 88},
    ]
    manifest = store.store("node_5", "output", "run_3", data, "dataset")
    assert manifest.preview is not None
    assert "shape" in manifest.preview
    assert "sample" in manifest.preview
    assert manifest.preview["shape"][0] == 4  # 4 rows
    assert len(manifest.preview["sample"]) == 3  # first 3 rows


# ── Cleanup ──────────────────────────────────────────────────────────────


def test_cleanup_removes_files(store: ArtifactStore):
    """Store artifacts, cleanup the run, verify files are deleted."""
    store.store("node_a", "out1", "run_cleanup", "data1", "text")
    store.store("node_b", "out2", "run_cleanup", "data2", "text")

    run_dir = store.base_path / "run_cleanup"
    assert run_dir.is_dir()

    bytes_freed = store.cleanup_run("run_cleanup")
    assert bytes_freed > 0
    assert not run_dir.exists()


# ── Deterministic serialization ──────────────────────────────────────────


def test_deterministic_serialization(store: ArtifactStore):
    """Store the same data twice, verify identical content hashes."""
    data = {"z_key": 3, "a_key": 1, "m_key": 2}

    m1 = store.store("node_det", "out", "run_det_1", data, "metrics")
    m2 = store.store("node_det", "out", "run_det_2", data, "metrics")

    assert m1.content_hash == m2.content_hash
    assert m1.size_bytes == m2.size_bytes


# ── Executor Integration Tests ──────────────────────────────────────────


class TestInferPortDataType:
    """Tests for _infer_port_data_type used during executor integration."""

    def test_uses_block_schema_when_available(self):
        from backend.engine.executor import _infer_port_data_type

        schema = {
            "outputs": [
                {"id": "result", "data_type": "dataset"},
                {"id": "status", "data_type": "metrics"},
            ]
        }
        assert _infer_port_data_type("result", "anything", schema) == "dataset"
        assert _infer_port_data_type("status", {}, schema) == "metrics"

    def test_falls_back_to_heuristic_for_unknown_port(self):
        from backend.engine.executor import _infer_port_data_type

        schema = {"outputs": [{"id": "other", "data_type": "text"}]}
        # Port not in schema → heuristic
        assert _infer_port_data_type("unknown_port", "hello", schema) == "text"
        assert _infer_port_data_type("unknown_port", {"a": 1.0}, schema) == "metrics"
        assert _infer_port_data_type("unknown_port", [1, 2, 3], schema) == "dataset"

    def test_heuristic_with_no_schema(self):
        from backend.engine.executor import _infer_port_data_type

        assert _infer_port_data_type("out", "text value", None) == "text"
        assert _infer_port_data_type("out", {"key": "val"}, None) == "config"
        assert _infer_port_data_type("out", [{"a": 1}], None) == "dataset"
        assert _infer_port_data_type("out", b"raw bytes", None) == "artifact"


class TestCacheBlockOutputs:
    """Tests for _cache_block_outputs executor integration."""

    def test_caches_outputs_and_creates_db_records(self, tmp_path: Path):
        """Verify _cache_block_outputs writes artifacts to disk and flushes DB records."""
        import backend.engine.executor as executor_mod

        # Temporarily swap the artifact store to use tmp_path
        original_store = executor_mod._artifact_store
        executor_mod._artifact_store = ArtifactStore(base_path=tmp_path)
        try:
            mock_db = MagicMock()
            node_outputs = {
                "result": "hello world",
                "metrics": {"accuracy": 0.95},
            }
            schema = {
                "outputs": [
                    {"id": "result", "data_type": "text"},
                    {"id": "metrics", "data_type": "metrics"},
                ]
            }

            executor_mod._cache_block_outputs(
                "node_1", "run_test", node_outputs, schema, mock_db
            )

            # Verify files were written to disk
            assert (tmp_path / "run_test" / "node_1" / "result.dat").exists()
            assert (tmp_path / "run_test" / "node_1" / "metrics.dat").exists()
            assert (tmp_path / "run_test" / "node_1" / "result.manifest.json").exists()
            assert (tmp_path / "run_test" / "node_1" / "metrics.manifest.json").exists()

            # Verify DB records were added
            assert mock_db.add.call_count == 2
            assert mock_db.flush.call_count == 1

            # Verify the records are ArtifactRecord instances
            from backend.models.artifact import ArtifactRecord
            for call in mock_db.add.call_args_list:
                record = call[0][0]
                assert isinstance(record, ArtifactRecord)
                assert record.run_id == "run_test"
                assert record.node_id == "node_1"
        finally:
            executor_mod._artifact_store = original_store

    def test_handles_non_serializable_values_gracefully(self, tmp_path: Path):
        """Verify non-serializable values fall back to text serialization."""
        import backend.engine.executor as executor_mod

        original_store = executor_mod._artifact_store
        executor_mod._artifact_store = ArtifactStore(base_path=tmp_path)
        try:
            mock_db = MagicMock()

            # A custom object that isn't JSON-serializable
            class CustomObj:
                def __str__(self):
                    return "custom_repr"

            node_outputs = {"result": CustomObj()}

            # Should not raise
            executor_mod._cache_block_outputs(
                "node_1", "run_test", node_outputs, None, mock_db
            )

            # Should have cached it as text
            dat_file = tmp_path / "run_test" / "node_1" / "result.dat"
            assert dat_file.exists()
            assert dat_file.read_text() == "custom_repr"
        finally:
            executor_mod._artifact_store = original_store

    def test_empty_outputs_is_noop(self):
        """Verify _cache_block_outputs does nothing for empty outputs."""
        import backend.engine.executor as executor_mod

        mock_db = MagicMock()
        executor_mod._cache_block_outputs("node_1", "run_test", {}, None, mock_db)
        mock_db.add.assert_not_called()

    def test_db_failure_does_not_crash(self, tmp_path: Path):
        """Verify DB flush failure is handled gracefully."""
        import backend.engine.executor as executor_mod

        original_store = executor_mod._artifact_store
        executor_mod._artifact_store = ArtifactStore(base_path=tmp_path)
        try:
            mock_db = MagicMock()
            mock_db.flush.side_effect = Exception("DB connection lost")

            node_outputs = {"result": "hello"}

            # Should not raise despite DB failure
            executor_mod._cache_block_outputs(
                "node_1", "run_test", node_outputs, None, mock_db
            )

            # Files should still exist on disk (cache wrote them)
            assert (tmp_path / "run_test" / "node_1" / "result.dat").exists()
        finally:
            executor_mod._artifact_store = original_store


class TestArtifactRecordRoundTrip:
    """Tests for ArtifactRecord ↔ ArtifactManifest conversion."""

    def test_from_manifest_to_manifest_roundtrip(self, store: ArtifactStore):
        """Verify ArtifactRecord.from_manifest → .to_manifest produces equivalent data."""
        from backend.models.artifact import ArtifactRecord

        manifest = store.store("node_rt", "output", "run_rt", {"key": "value"}, "config")
        record = ArtifactRecord.from_manifest(manifest)

        assert record.id == manifest.artifact_id
        assert record.run_id == manifest.run_id
        assert record.node_id == manifest.node_id
        assert record.port_id == manifest.port_id
        assert record.data_type == manifest.data_type
        assert record.serializer == manifest.serializer
        assert record.content_hash == manifest.content_hash
        assert record.file_path == manifest.file_path
        assert record.size_bytes == manifest.size_bytes

        # Round-trip back to manifest
        restored = record.to_manifest()
        assert restored.artifact_id == manifest.artifact_id
        assert restored.content_hash == manifest.content_hash
        assert restored.data_type == manifest.data_type
        assert restored.preview == manifest.preview
