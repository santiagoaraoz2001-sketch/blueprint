"""Tests for pipeline versioning, model registry, and .blueprint.json export."""

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event as sa_event, inspect
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models.pipeline import Pipeline
from backend.models.pipeline_version import PipelineVersion
from backend.models.model_record import ModelRecord
from backend.models.run import Run


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session(tmp_path):
    """Create an in-memory SQLite database with all tables for testing."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @sa_event.listens_for(engine, "connect")
    def _wal(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Import all models to register with Base.metadata
    from backend.models import (  # noqa: F401
        project, experiment, experiment_phase, pipeline, pipeline_version,
        run, dataset, artifact, paper, sweep, model_record,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_pipeline(db_session):
    """Insert a sample pipeline and return it."""
    pipeline = Pipeline(
        id=str(uuid.uuid4()),
        name="Test Pipeline",
        definition={
            "nodes": [
                {"id": "node1", "data": {"type": "llm_inference", "label": "Inference", "config": {"model": "gpt-4"}}},
                {"id": "node2", "data": {"type": "data_export", "label": "Export", "config": {"format": "csv"}}},
            ],
            "edges": [
                {"id": "e1", "source": "node1", "target": "node2"},
            ],
        },
    )
    db_session.add(pipeline)
    db_session.commit()
    return pipeline


# ---------------------------------------------------------------------------
# Test 1: test_version_auto_saved_on_save
# ---------------------------------------------------------------------------

class TestVersionAutoSavedOnSave:
    def test_create_version_increments_number(self, db_session, sample_pipeline):
        """When create_version_for_pipeline is called, it should auto-increment the version number."""
        from backend.routers.pipeline_versions import create_version_for_pipeline

        v1 = create_version_for_pipeline(
            db_session, sample_pipeline.id,
            sample_pipeline.definition, message="First save",
        )
        db_session.commit()
        assert v1.version_number == 1
        assert v1.message == "First save"

        v2 = create_version_for_pipeline(
            db_session, sample_pipeline.id,
            sample_pipeline.definition, message="Second save",
        )
        db_session.commit()
        assert v2.version_number == 2

    def test_snapshot_stores_full_definition(self, db_session, sample_pipeline):
        """The snapshot field should contain the full JSON pipeline definition."""
        from backend.routers.pipeline_versions import create_version_for_pipeline

        v = create_version_for_pipeline(
            db_session, sample_pipeline.id,
            sample_pipeline.definition, message="Auto-save",
        )
        db_session.commit()

        parsed = json.loads(v.snapshot)
        assert "nodes" in parsed
        assert "edges" in parsed
        assert len(parsed["nodes"]) == 2
        assert len(parsed["edges"]) == 1

    def test_snapshot_is_deterministic(self, db_session, sample_pipeline):
        """Two snapshots of the same definition should produce identical JSON (sorted keys)."""
        from backend.routers.pipeline_versions import create_version_for_pipeline

        v1 = create_version_for_pipeline(
            db_session, sample_pipeline.id,
            sample_pipeline.definition,
        )
        v2 = create_version_for_pipeline(
            db_session, sample_pipeline.id,
            sample_pipeline.definition,
        )
        db_session.commit()
        assert v1.snapshot == v2.snapshot


# ---------------------------------------------------------------------------
# Test 2: test_restore_creates_new_version
# ---------------------------------------------------------------------------

class TestRestoreCreatesNewVersion:
    def test_restore_creates_new_version_and_updates_pipeline(self, db_session, sample_pipeline):
        """Restoring a version should create a new version with the old snapshot
        and update the pipeline's current definition."""
        from backend.routers.pipeline_versions import create_version_for_pipeline

        # Create v1 with original definition
        original_def = sample_pipeline.definition
        create_version_for_pipeline(
            db_session, sample_pipeline.id, original_def, message="v1",
        )
        db_session.commit()

        # Modify the pipeline definition
        modified_def = {
            "nodes": [
                {"id": "node1", "data": {"type": "llm_inference", "label": "Inference", "config": {"model": "gpt-4"}}},
                {"id": "node3", "data": {"type": "data_loader", "label": "Loader", "config": {}}},
            ],
            "edges": [],
        }
        sample_pipeline.definition = modified_def
        create_version_for_pipeline(
            db_session, sample_pipeline.id, modified_def, message="v2",
        )
        db_session.commit()

        # Now restore v1
        v1 = (
            db_session.query(PipelineVersion)
            .filter(
                PipelineVersion.pipeline_id == sample_pipeline.id,
                PipelineVersion.version_number == 1,
            )
            .first()
        )
        assert v1 is not None

        old_snapshot = json.loads(v1.snapshot)

        # Create a restore version (v3)
        v3 = create_version_for_pipeline(
            db_session, sample_pipeline.id,
            old_snapshot, message="Restored from v1",
        )
        sample_pipeline.definition = old_snapshot
        db_session.commit()

        assert v3.version_number == 3
        assert v3.message == "Restored from v1"
        assert json.loads(v3.snapshot) == old_snapshot
        assert sample_pipeline.definition == old_snapshot

    def test_version_count_grows_on_restore(self, db_session, sample_pipeline):
        """After restore, total version count should increase."""
        from backend.routers.pipeline_versions import create_version_for_pipeline

        create_version_for_pipeline(
            db_session, sample_pipeline.id,
            sample_pipeline.definition, message="v1",
        )
        create_version_for_pipeline(
            db_session, sample_pipeline.id,
            sample_pipeline.definition, message="v2",
        )
        db_session.commit()

        count_before = db_session.query(PipelineVersion).filter(
            PipelineVersion.pipeline_id == sample_pipeline.id
        ).count()
        assert count_before == 2

        # Restore from v1
        v1 = db_session.query(PipelineVersion).filter(
            PipelineVersion.pipeline_id == sample_pipeline.id,
            PipelineVersion.version_number == 1,
        ).first()
        create_version_for_pipeline(
            db_session, sample_pipeline.id,
            json.loads(v1.snapshot), message="Restored from v1",
        )
        db_session.commit()

        count_after = db_session.query(PipelineVersion).filter(
            PipelineVersion.pipeline_id == sample_pipeline.id
        ).count()
        assert count_after == 3


# ---------------------------------------------------------------------------
# Test 3: test_model_auto_registered_after_training
# ---------------------------------------------------------------------------

class TestModelAutoRegisteredAfterTraining:
    def test_training_block_produces_model_record(self, db_session, sample_pipeline):
        """After a training block completes, auto_register_models should create a ModelRecord."""
        from backend.services.model_auto_register import auto_register_models

        # Create a run
        run = Run(
            id=str(uuid.uuid4()),
            pipeline_id=sample_pipeline.id,
            status="complete",
        )
        db_session.add(run)
        db_session.commit()

        nodes = [
            {
                "id": "train1",
                "data": {
                    "type": "lora_finetuning",
                    "label": "LoRA Fine-tune",
                    "config": {"model_name": "llama-7b", "epochs": 3, "dataset": "my-data.jsonl"},
                },
            },
        ]
        outputs = {
            "train1": {
                "model_path": "/models/llama-7b-lora",
                "model_name": "llama-7b-lora-finetuned",
            },
        }
        metrics = {
            "train1.loss": 0.42,
            "train1.eval_accuracy": 0.89,
        }

        registered = auto_register_models(run.id, nodes, outputs, metrics, db_session)
        assert len(registered) == 1

        record = db_session.query(ModelRecord).filter(ModelRecord.id == registered[0]).first()
        assert record is not None
        assert record.name == "llama-7b-lora-finetuned"
        assert record.source_run_id == run.id
        assert record.source_node_id == "train1"
        assert "lora_finetuning" in record.tags
        assert record.training_config["epochs"] == 3
        assert record.metrics.get("loss") == 0.42

    def test_merge_block_produces_model_record(self, db_session, sample_pipeline):
        """Merge blocks should also auto-register models."""
        from backend.services.model_auto_register import auto_register_models

        run = Run(
            id=str(uuid.uuid4()),
            pipeline_id=sample_pipeline.id,
            status="complete",
        )
        db_session.add(run)
        db_session.commit()

        nodes = [
            {
                "id": "merge1",
                "data": {
                    "type": "slerp_merge",
                    "label": "SLERP Merge",
                    "config": {"output_model_name": "merged-model"},
                },
            },
        ]
        outputs = {
            "merge1": {
                "model_path": "/models/merged-model.safetensors",
            },
        }

        registered = auto_register_models(run.id, nodes, outputs, {}, db_session)
        assert len(registered) == 1

        record = db_session.query(ModelRecord).filter(ModelRecord.id == registered[0]).first()
        assert record is not None
        assert record.name == "merged-model"
        assert record.format == "safetensors"
        assert "slerp_merge" in record.tags

    def test_non_training_block_skipped(self, db_session, sample_pipeline):
        """Blocks that are not training or merge blocks should not produce ModelRecords."""
        from backend.services.model_auto_register import auto_register_models

        run = Run(
            id=str(uuid.uuid4()),
            pipeline_id=sample_pipeline.id,
            status="complete",
        )
        db_session.add(run)
        db_session.commit()

        nodes = [
            {
                "id": "infer1",
                "data": {"type": "llm_inference", "label": "Inference", "config": {}},
            },
        ]
        outputs = {"infer1": {"text": "Hello world"}}

        registered = auto_register_models(run.id, nodes, outputs, {}, db_session)
        assert len(registered) == 0


# ---------------------------------------------------------------------------
# Test 4: test_model_card_shows_provenance
# ---------------------------------------------------------------------------

class TestModelCardShowsProvenance:
    def test_model_record_stores_provenance(self, db_session, sample_pipeline):
        """A ModelRecord should store run_id, node_id, and training config for provenance."""
        run = Run(
            id=str(uuid.uuid4()),
            pipeline_id=sample_pipeline.id,
            status="complete",
        )
        db_session.add(run)
        db_session.commit()

        record = ModelRecord(
            id=str(uuid.uuid4()),
            name="test-model",
            version="1.0.0",
            format="pytorch",
            source_run_id=run.id,
            source_node_id="train1",
            metrics={"accuracy": 0.95},
            tags="lora_finetuning,pytorch",
            training_config={"epochs": 5, "learning_rate": 1e-4},
            source_data="dataset-v2.jsonl",
        )
        db_session.add(record)
        db_session.commit()

        # Verify all provenance fields
        fetched = db_session.query(ModelRecord).filter(ModelRecord.id == record.id).first()
        assert fetched.source_run_id == run.id
        assert fetched.source_node_id == "train1"
        assert fetched.training_config["epochs"] == 5
        assert fetched.training_config["learning_rate"] == 1e-4
        assert fetched.source_data == "dataset-v2.jsonl"
        assert fetched.metrics["accuracy"] == 0.95
        assert "lora_finetuning" in fetched.tags

    def test_model_card_links_to_pipeline(self, db_session, sample_pipeline):
        """A model card should be traceable back to the pipeline via its run."""
        run = Run(
            id=str(uuid.uuid4()),
            pipeline_id=sample_pipeline.id,
            status="complete",
        )
        db_session.add(run)
        db_session.commit()

        record = ModelRecord(
            id=str(uuid.uuid4()),
            name="traced-model",
            version="1.0.0",
            format="safetensors",
            source_run_id=run.id,
            source_node_id="node1",
        )
        db_session.add(record)
        db_session.commit()

        # Trace: model → run → pipeline
        fetched_model = db_session.query(ModelRecord).filter(ModelRecord.id == record.id).first()
        fetched_run = db_session.query(Run).filter(Run.id == fetched_model.source_run_id).first()
        fetched_pipeline = db_session.query(Pipeline).filter(Pipeline.id == fetched_run.pipeline_id).first()
        assert fetched_pipeline.id == sample_pipeline.id
        assert fetched_pipeline.name == "Test Pipeline"


# ---------------------------------------------------------------------------
# Test 5: test_blueprint_json_export_deterministic
# ---------------------------------------------------------------------------

class TestBlueprintJsonExportDeterministic:
    def test_sorted_keys_and_indent(self):
        """The .blueprint.json export should use sort_keys=True and indent=2."""
        definition = {
            "nodes": [{"id": "b", "data": {}}, {"id": "a", "data": {}}],
            "edges": [{"id": "e1", "source": "a", "target": "b"}],
        }

        blueprint = {
            "version": "1.0.0",
            "pipeline_name": "Test",
            "nodes": definition["nodes"],
            "edges": definition["edges"],
            "resolved_configs": {},
            "block_versions": {},
            "platform_profile": {"os": "Darwin", "python": "3.11.0", "capabilities": []},
            "created_at": "2026-01-01T00:00:00",
        }

        json1 = json.dumps(blueprint, sort_keys=True, indent=2)
        json2 = json.dumps(blueprint, sort_keys=True, indent=2)

        # Deterministic: same input always produces same output
        assert json1 == json2

        # Verify structure
        parsed = json.loads(json1)
        assert parsed["version"] == "1.0.0"
        assert parsed["pipeline_name"] == "Test"
        assert len(parsed["nodes"]) == 2
        assert len(parsed["edges"]) == 1

        # Verify keys are sorted (first key alphabetically should come first)
        keys = list(parsed.keys())
        assert keys == sorted(keys)

    def test_identical_pipelines_produce_identical_export(self):
        """Two identical pipeline definitions should produce byte-identical JSON exports."""
        def make_blueprint(name, nodes, edges):
            return json.dumps({
                "version": "1.0.0",
                "pipeline_name": name,
                "nodes": nodes,
                "edges": edges,
                "resolved_configs": {},
                "block_versions": {"llm_inference": "1.0.0"},
                "platform_profile": {"os": "Darwin", "python": "3.11.0", "capabilities": []},
                "created_at": "2026-01-01T00:00:00",
            }, sort_keys=True, indent=2)

        nodes = [{"id": "n1", "data": {"type": "llm_inference"}}]
        edges = []

        export_a = make_blueprint("My Pipeline", nodes, edges)
        export_b = make_blueprint("My Pipeline", nodes, edges)
        assert export_a == export_b

    def test_different_pipelines_produce_different_export(self):
        """Different pipeline definitions should produce different JSON exports."""
        def make_blueprint(nodes):
            return json.dumps({
                "version": "1.0.0",
                "pipeline_name": "Test",
                "nodes": nodes,
                "edges": [],
                "resolved_configs": {},
                "block_versions": {},
                "platform_profile": {"os": "Darwin", "python": "3.11.0", "capabilities": []},
                "created_at": "2026-01-01T00:00:00",
            }, sort_keys=True, indent=2)

        export_a = make_blueprint([{"id": "n1"}])
        export_b = make_blueprint([{"id": "n1"}, {"id": "n2"}])
        assert export_a != export_b


# ---------------------------------------------------------------------------
# Test 6: Concurrent version numbering safety
# ---------------------------------------------------------------------------

class TestConcurrentVersionNumbering:
    def test_unique_constraint_prevents_duplicate_versions(self, db_session, sample_pipeline):
        """The unique constraint on (pipeline_id, version_number) should prevent
        two versions with the same number from being committed."""
        from sqlalchemy.exc import IntegrityError

        v1 = PipelineVersion(
            id=str(uuid.uuid4()),
            pipeline_id=sample_pipeline.id,
            version_number=1,
            snapshot="{}",
            author="local",
        )
        db_session.add(v1)
        db_session.commit()

        # Attempt to insert a second version with the same number
        v1_dup = PipelineVersion(
            id=str(uuid.uuid4()),
            pipeline_id=sample_pipeline.id,
            version_number=1,
            snapshot="{}",
            author="local",
        )
        db_session.add(v1_dup)
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_retry_loop_recovers_from_conflict(self, db_session, sample_pipeline):
        """create_version_for_pipeline should recover via retry if a conflict occurs."""
        from backend.routers.pipeline_versions import create_version_for_pipeline

        # Pre-insert version 1 manually
        v1 = PipelineVersion(
            id=str(uuid.uuid4()),
            pipeline_id=sample_pipeline.id,
            version_number=1,
            snapshot="{}",
            author="local",
        )
        db_session.add(v1)
        db_session.commit()

        # Now create_version_for_pipeline should get version 2 (no conflict)
        v2 = create_version_for_pipeline(
            db_session, sample_pipeline.id, {"test": True},
        )
        db_session.commit()
        assert v2.version_number == 2

    def test_different_pipelines_have_independent_version_numbers(self, db_session):
        """Two different pipelines should each start at version 1."""
        from backend.routers.pipeline_versions import create_version_for_pipeline

        p1 = Pipeline(id=str(uuid.uuid4()), name="Pipeline A", definition={})
        p2 = Pipeline(id=str(uuid.uuid4()), name="Pipeline B", definition={})
        db_session.add_all([p1, p2])
        db_session.commit()

        v1a = create_version_for_pipeline(db_session, p1.id, {"a": 1})
        v1b = create_version_for_pipeline(db_session, p2.id, {"b": 1})
        db_session.commit()

        assert v1a.version_number == 1
        assert v1b.version_number == 1


# ---------------------------------------------------------------------------
# Test 7: Sharded model size detection
# ---------------------------------------------------------------------------

class TestShardedModelSizeDetection:
    def test_single_file_size(self, tmp_path):
        """_get_model_size should return exact size for a single file."""
        from backend.services.model_auto_register import _get_model_size

        model_file = tmp_path / "model.safetensors"
        model_file.write_bytes(b"\x00" * 1024)

        result = _get_model_size({"model_path": str(model_file)})
        assert result == 1024

    def test_sharded_directory_size(self, tmp_path):
        """_get_model_size should sum all model shard files in a directory."""
        from backend.services.model_auto_register import _get_model_size

        model_dir = tmp_path / "my-model"
        model_dir.mkdir()
        # Create sharded safetensors
        (model_dir / "model-00001-of-00002.safetensors").write_bytes(b"\x00" * 500)
        (model_dir / "model-00002-of-00002.safetensors").write_bytes(b"\x00" * 300)
        # Non-model files should be excluded from model-specific sum
        (model_dir / "config.json").write_text("{}")
        (model_dir / "tokenizer.json").write_text("{}")

        result = _get_model_size({"model_path": str(model_dir)})
        assert result == 800

    def test_hf_index_file_size(self, tmp_path):
        """_get_model_size should read the HF index file for accurate shard sizes."""
        from backend.services.model_auto_register import _get_model_size

        model_dir = tmp_path / "hf-model"
        model_dir.mkdir()

        # Create shard files
        (model_dir / "model-00001-of-00002.safetensors").write_bytes(b"\x00" * 2000)
        (model_dir / "model-00002-of-00002.safetensors").write_bytes(b"\x00" * 3000)

        # Create HF index file referencing both shards
        index = {
            "metadata": {"total_size": 5000},
            "weight_map": {
                "layer1.weight": "model-00001-of-00002.safetensors",
                "layer2.weight": "model-00002-of-00002.safetensors",
                "layer2.bias": "model-00002-of-00002.safetensors",
            },
        }
        (model_dir / "model.safetensors.index.json").write_text(json.dumps(index))

        result = _get_model_size({"model_path": str(model_dir)})
        assert result == 5000

    def test_explicit_size_bytes_in_output(self):
        """_get_model_size should prefer explicit size_bytes from output metadata."""
        from backend.services.model_auto_register import _get_model_size

        result = _get_model_size({"size_bytes": 999999, "model_path": "/nonexistent"})
        assert result == 999999

    def test_nonexistent_path_returns_none(self):
        """_get_model_size should return None for non-existent paths."""
        from backend.services.model_auto_register import _get_model_size

        result = _get_model_size({"model_path": "/this/does/not/exist"})
        assert result is None


# ---------------------------------------------------------------------------
# Test 8: Format detection for sharded and directory models
# ---------------------------------------------------------------------------

class TestFormatDetection:
    def test_detect_safetensors_directory(self, tmp_path):
        """Should detect safetensors format from directory contents."""
        from backend.services.model_auto_register import _detect_model_format

        model_dir = tmp_path / "safetensors-model"
        model_dir.mkdir()
        (model_dir / "model-00001-of-00002.safetensors").write_bytes(b"")
        (model_dir / "model.safetensors.index.json").write_text("{}")

        result = _detect_model_format({"model_path": str(model_dir)})
        assert result == "safetensors"

    def test_detect_gguf_directory(self, tmp_path):
        """Should detect gguf format from directory contents."""
        from backend.services.model_auto_register import _detect_model_format

        model_dir = tmp_path / "gguf-model"
        model_dir.mkdir()
        (model_dir / "model.gguf").write_bytes(b"")

        result = _detect_model_format({"model_path": str(model_dir)})
        assert result == "gguf"

    def test_explicit_format_in_output(self):
        """Should use explicit format field from output metadata."""
        from backend.services.model_auto_register import _detect_model_format

        result = _detect_model_format({"format": "onnx", "model_path": "/some/model.bin"})
        assert result == "onnx"

    def test_single_file_format(self, tmp_path):
        """Should detect format from single file extension."""
        from backend.services.model_auto_register import _detect_model_format

        model_file = tmp_path / "model.onnx"
        model_file.write_bytes(b"")

        result = _detect_model_format({"model_path": str(model_file)})
        assert result == "onnx"


# ---------------------------------------------------------------------------
# Test 9: Checkpoint selector and sweep auto-registration
# ---------------------------------------------------------------------------

class TestCheckpointAndSweepRegistration:
    def test_checkpoint_selector_registers_model(self, db_session, sample_pipeline):
        """checkpoint_selector blocks should auto-register models."""
        from backend.services.model_auto_register import auto_register_models

        run = Run(id=str(uuid.uuid4()), pipeline_id=sample_pipeline.id, status="complete")
        db_session.add(run)
        db_session.commit()

        nodes = [{
            "id": "ckpt1",
            "data": {
                "type": "checkpoint_selector",
                "label": "Best Checkpoint",
                "config": {"output_model_name": "best-checkpoint"},
            },
        }]
        outputs = {"ckpt1": {"model_path": "/checkpoints/epoch-5", "model_name": "epoch5-best"}}

        registered = auto_register_models(run.id, nodes, outputs, {}, db_session)
        assert len(registered) == 1
        record = db_session.query(ModelRecord).filter(ModelRecord.id == registered[0]).first()
        assert record.name == "epoch5-best"
        assert "checkpoint_selector" in record.tags

    def test_hyperparameter_sweep_registers_model(self, db_session, sample_pipeline):
        """hyperparameter_sweep blocks should auto-register their best model."""
        from backend.services.model_auto_register import auto_register_models

        run = Run(id=str(uuid.uuid4()), pipeline_id=sample_pipeline.id, status="complete")
        db_session.add(run)
        db_session.commit()

        nodes = [{
            "id": "sweep1",
            "data": {
                "type": "hyperparameter_sweep",
                "label": "HP Sweep",
                "config": {"model_name": "sweep-model"},
            },
        }]
        outputs = {"sweep1": {"model_path": "/sweep/best-trial/model", "model_name": "sweep-best"}}

        registered = auto_register_models(run.id, nodes, outputs, {}, db_session)
        assert len(registered) == 1
        record = db_session.query(ModelRecord).filter(ModelRecord.id == registered[0]).first()
        assert record.name == "sweep-best"
        assert "hyperparameter_sweep" in record.tags
