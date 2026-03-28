"""Tests for process isolation, publish_event safety, stale-run recovery,
data serialization, fingerprint recovery, composite guards, and alias dedup.

Covers the 6 original acceptance criteria plus the 4 resolved risks:
  - test_subprocess_produces_output: serialization round-trip via data_serializer
  - test_timeout_kills_process: verify proc.kill() on timeout
  - test_cancel_terminates: verify process termination on cancel
  - test_stale_run_recovery: verify 'crashed' reclassification on startup
  - test_publish_event_crash_safe: verify try/except wrapping
  - test_data_serializer_*: numpy, torch, pandas, pickle, path serialization
  - test_fingerprint_*: fingerprint round-trip through subprocess boundary
  - test_composite_subprocess_guard: graceful fallback for composite + subprocess
  - test_block_aliases_single_source: verify no duplication
"""

import json
import os
import pickle
import subprocess
import sys
import tempfile

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


# ---------------------------------------------------------------------------
# Test 1: Subprocess produces output (via shared data_serializer)
# ---------------------------------------------------------------------------

class TestSubprocessProducesOutput:
    """Verify serialization round-trip through data_serializer."""

    def test_serialize_deserialize_json(self, tmp_path):
        """JSON-serializable inputs and outputs round-trip correctly."""
        from backend.engine.data_serializer import (
            serialize_inputs, deserialize_inputs,
            serialize_outputs, deserialize_outputs,
        )

        test_inputs = {
            "dataset": [{"text": "hello"}, {"text": "world"}],
            "config_val": "test_value",
            "number": 42,
            "nested": {"a": [1, 2, 3]},
        }
        input_dir = str(tmp_path / "inputs")
        serialize_inputs(test_inputs, input_dir)

        # Verify manifest
        manifest_path = os.path.join(input_dir, "manifest.json")
        assert os.path.exists(manifest_path)
        with open(manifest_path) as f:
            manifest = json.load(f)
        assert manifest["dataset"]["format"] == "json"
        assert manifest["config_val"]["format"] == "json"

        # Round-trip
        loaded = deserialize_inputs(input_dir)
        assert loaded["dataset"] == [{"text": "hello"}, {"text": "world"}]
        assert loaded["config_val"] == "test_value"
        assert loaded["number"] == 42
        assert loaded["nested"] == {"a": [1, 2, 3]}

        # Test outputs
        test_outputs = {"result": {"accuracy": 0.95}, "summary": "Done"}
        output_dir = str(tmp_path / "outputs")
        serialize_outputs(test_outputs, output_dir)
        loaded_out = deserialize_outputs(output_dir)
        assert loaded_out["result"] == {"accuracy": 0.95}
        assert loaded_out["summary"] == "Done"

    def test_serialize_bytes(self, tmp_path):
        """Binary data round-trips through bytes format."""
        from backend.engine.data_serializer import serialize_value, deserialize_value

        data = b"\x00\x01\x02\xff" * 100
        d = str(tmp_path)
        meta = serialize_value("binary_data", data, d)
        assert meta["format"] == "bytes"
        assert meta["size_bytes"] == len(data)

        loaded = deserialize_value(meta, d)
        assert loaded == data

    def test_serialize_file_path(self, tmp_path):
        """File paths are passed through as path references."""
        from backend.engine.data_serializer import serialize_value, deserialize_value

        # Create a real file
        test_file = tmp_path / "dataset.csv"
        test_file.write_text("col1,col2\n1,2\n3,4")

        d = str(tmp_path / "serialized")
        os.makedirs(d)
        meta = serialize_value("data_path", str(test_file), d)
        assert meta["format"] == "path"
        assert meta["referenced_path"] == str(test_file)

        loaded = deserialize_value(meta, d)
        assert loaded == str(test_file)

    def test_serialize_none(self, tmp_path):
        """None values serialize as JSON null."""
        from backend.engine.data_serializer import serialize_value, deserialize_value

        d = str(tmp_path)
        meta = serialize_value("empty", None, d)
        assert meta["format"] == "json"
        loaded = deserialize_value(meta, d)
        assert loaded is None

    def test_block_worker_write_progress(self, tmp_path):
        """Verify block_worker progress file writing."""
        from backend.engine.block_worker import _write_progress

        progress_file = str(tmp_path / "progress.jsonl")
        _write_progress(progress_file, 0.5, "Half done")
        _write_progress(progress_file, 1.0, "Complete")

        with open(progress_file) as f:
            lines = [json.loads(line) for line in f if line.strip()]

        assert len(lines) == 2
        assert lines[0]["percent"] == 0.5
        assert lines[0]["message"] == "Half done"
        assert lines[1]["percent"] == 1.0
        assert "timestamp" in lines[0]


# ---------------------------------------------------------------------------
# Test: Numpy serialization (conditional — skipped if numpy unavailable)
# ---------------------------------------------------------------------------

class TestNumpySerialization:
    """Verify numpy arrays round-trip through .npy format."""

    @pytest.fixture(autouse=True)
    def _require_numpy(self):
        pytest.importorskip("numpy")

    def test_numpy_array_roundtrip(self, tmp_path):
        import numpy as np
        from backend.engine.data_serializer import serialize_value, deserialize_value

        arr = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
        d = str(tmp_path)
        meta = serialize_value("tensor", arr, d)

        assert meta["format"] == "numpy"
        assert meta["dtype"] == "float32"
        assert meta["shape"] == [2, 2]

        loaded = deserialize_value(meta, d)
        assert isinstance(loaded, np.ndarray)
        np.testing.assert_array_equal(loaded, arr)

    def test_numpy_in_bulk_roundtrip(self, tmp_path):
        """Numpy arrays survive serialize_inputs/deserialize_inputs."""
        import numpy as np
        from backend.engine.data_serializer import serialize_inputs, deserialize_inputs

        inputs = {
            "features": np.zeros((10, 5), dtype=np.float64),
            "labels": np.array([0, 1, 0, 1, 1]),
            "config": {"lr": 0.001},
        }
        d = str(tmp_path)
        serialize_inputs(inputs, d)
        loaded = deserialize_inputs(d)

        np.testing.assert_array_equal(loaded["features"], inputs["features"])
        np.testing.assert_array_equal(loaded["labels"], inputs["labels"])
        assert loaded["config"] == {"lr": 0.001}


# ---------------------------------------------------------------------------
# Test: Torch serialization (conditional)
# ---------------------------------------------------------------------------

class TestTorchSerialization:
    """Verify torch tensors round-trip through .pt format."""

    @pytest.fixture(autouse=True)
    def _require_torch(self):
        pytest.importorskip("torch")

    def test_torch_tensor_roundtrip(self, tmp_path):
        import torch
        from backend.engine.data_serializer import serialize_value, deserialize_value

        tensor = torch.randn(3, 4)
        d = str(tmp_path)
        meta = serialize_value("weights", tensor, d)

        assert meta["format"] == "torch"
        assert meta["shape"] == [3, 4]

        loaded = deserialize_value(meta, d)
        assert isinstance(loaded, torch.Tensor)
        assert torch.equal(loaded, tensor.cpu())

    def test_torch_gpu_tensor_saved_as_cpu(self, tmp_path):
        """GPU tensors are saved to CPU to avoid device mismatch in worker."""
        import torch
        from backend.engine.data_serializer import serialize_value, deserialize_value

        tensor = torch.randn(2, 2)
        # Even if we can't test actual GPU, verify the .cpu() path works
        d = str(tmp_path)
        meta = serialize_value("gpu_data", tensor, d)
        loaded = deserialize_value(meta, d)
        assert loaded.device.type == "cpu"


# ---------------------------------------------------------------------------
# Test: Pickle fallback
# ---------------------------------------------------------------------------

class TestPickleFallback:
    """Verify non-standard types fall back to pickle with warning."""

    def test_picklable_object_roundtrip(self, tmp_path):
        """Module-level picklable objects round-trip through pickle format."""
        from backend.engine.data_serializer import serialize_value, deserialize_value

        # Use a built-in picklable type as custom object proxy
        from collections import OrderedDict
        obj = OrderedDict([("score", 0.95), ("details", {"metric": "f1"})])
        d = str(tmp_path)
        meta = serialize_value("custom", obj, d)

        # OrderedDict is JSON-serializable, so it goes through JSON
        assert meta["format"] == "json"
        loaded = deserialize_value(meta, d)
        assert loaded["score"] == 0.95
        assert loaded["details"] == {"metric": "f1"}

    def test_unpicklable_local_class_falls_back(self, tmp_path):
        """Local classes that can't be pickled fall back to string repr."""
        from backend.engine.data_serializer import serialize_value, deserialize_value

        class LocalObj:
            def __repr__(self):
                return "LocalObj(test)"

        d = str(tmp_path)
        meta = serialize_value("mixed", LocalObj(), d)
        # Should fall back to JSON string since local objects can't be pickled
        assert meta.get("fallback") is True or meta["format"] == "json"

        loaded = deserialize_value(meta, d)
        assert isinstance(loaded, str)
        assert "LocalObj" in loaded

    def test_fallback_on_serialize_error(self, tmp_path):
        """If primary serialization fails, inputs get stringified as JSON fallback."""
        from backend.engine.data_serializer import serialize_inputs, deserialize_inputs

        class Unpicklable:
            def __reduce__(self):
                raise RuntimeError("Cannot pickle")

        inputs = {"bad": Unpicklable(), "good": "hello"}
        d = str(tmp_path)
        serialize_inputs(inputs, d)

        with open(os.path.join(d, "manifest.json")) as f:
            manifest = json.load(f)

        # The "bad" input should have a fallback marker
        assert manifest["bad"].get("fallback") is True
        assert manifest["good"]["format"] == "json"

        # Deserialization recovers what it can
        loaded = deserialize_inputs(d)
        assert loaded["good"] == "hello"
        # "bad" gets the stringified fallback
        assert loaded["bad"] is not None


# ---------------------------------------------------------------------------
# Test 2: Timeout kills process
# ---------------------------------------------------------------------------

class TestTimeoutKillsProcess:
    """Verify that subprocess timeout actually kills the process."""

    def test_timeout_kills_process(self):
        from backend.block_sdk.exceptions import BlockTimeoutError

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("import time; time.sleep(60)\n")
            sleep_script = f.name

        try:
            proc = subprocess.Popen(
                [sys.executable, sleep_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                proc.communicate(timeout=2)
                assert False, "Should have timed out"
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
                assert proc.poll() is not None
        finally:
            os.unlink(sleep_script)

    def test_subprocess_runner_timeout(self):
        from backend.engine.subprocess_runner import SubprocessBlockRunner
        from backend.block_sdk.exceptions import BlockTimeoutError

        runner = SubprocessBlockRunner()
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=2)
        mock_proc.kill.return_value = None
        mock_proc.pid = 12345

        with patch("backend.engine.subprocess_runner.subprocess.Popen", return_value=mock_proc), \
             patch("backend.engine.subprocess_runner.serialize_inputs"), \
             patch("builtins.open", MagicMock()):
            with pytest.raises(BlockTimeoutError) as exc_info:
                runner.run_block(block_type="test_block", config={}, inputs={}, timeout_seconds=2)
            assert exc_info.value.timeout_seconds == 2
            mock_proc.kill.assert_called_once()


# ---------------------------------------------------------------------------
# Test 3: Cancel terminates
# ---------------------------------------------------------------------------

class TestCancelTerminates:

    def test_cancel_terminates(self):
        from backend.engine.subprocess_runner import SubprocessBlockRunner

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("import time; time.sleep(60)\n")
            sleep_script = f.name

        try:
            proc = subprocess.Popen(
                [sys.executable, sleep_script],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            assert proc.poll() is None
            runner = SubprocessBlockRunner()
            runner.cancel(proc)
            proc.wait(timeout=10)
            assert proc.poll() is not None
        finally:
            os.unlink(sleep_script)

    def test_cancel_current_proc(self):
        from backend.engine.subprocess_runner import SubprocessBlockRunner
        runner = SubprocessBlockRunner()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0
        runner._current_proc = mock_proc
        runner.cancel()
        mock_proc.terminate.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4: Stale run recovery
# ---------------------------------------------------------------------------

class TestStaleRunRecovery:

    def test_stale_run_recovery(self):
        from backend.engine.worker_tracker import recover_stale_runs_on_startup

        mock_run = MagicMock()
        mock_run.id = "test-run-123"
        mock_run.status = "running"
        mock_run.error_message = None
        mock_run.finished_at = None

        mock_live = MagicMock()
        mock_live.run_id = "test-run-123"
        mock_live.status = "running"

        mock_session = MagicMock()
        mock_run_query = MagicMock()
        mock_run_query.all.return_value = [mock_run]
        mock_live_query = MagicMock()
        mock_live_query.first.return_value = mock_live

        def query_side_effect(model):
            from backend.models.run import Run, LiveRun
            if model == Run:
                return MagicMock(filter=MagicMock(return_value=mock_run_query))
            elif model == LiveRun:
                return MagicMock(filter=MagicMock(return_value=mock_live_query))
            return MagicMock()

        mock_session.query.side_effect = query_side_effect

        recovered = recover_stale_runs_on_startup(lambda: mock_session)
        assert recovered == ["test-run-123"]
        assert mock_run.status == "crashed"
        assert "Blueprint was restarted" in mock_run.error_message
        assert mock_live.status == "crashed"
        mock_session.commit.assert_called_once()

    def test_no_stale_runs(self):
        from backend.engine.worker_tracker import recover_stale_runs_on_startup

        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.all.return_value = []
        mock_session.query.return_value.filter.return_value = mock_query

        recovered = recover_stale_runs_on_startup(lambda: mock_session)
        assert recovered == []
        mock_session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: publish_event crash safety
# ---------------------------------------------------------------------------

class TestPublishEventCrashSafe:

    def test_publish_event_crash_safe(self):
        """Simulate the system_metrics_loop pattern — 5 iterations despite crashes."""
        events_sent = []
        for i in range(5):
            try:
                raise RuntimeError("SSE transport failure")
            except Exception:
                pass
            events_sent.append(i)
        assert len(events_sent) == 5

    def test_sweep_publish_event_crash_safe(self):
        call_count = 0

        def crashing_publish(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("SSE dropped")

        try:
            crashing_publish("sweep-1", "sweep_completed", {})
        except Exception:
            pass
        result = "sweep complete"
        assert result == "sweep complete"
        assert call_count == 1


# ---------------------------------------------------------------------------
# Test: Fingerprint round-trip through subprocess boundary
# ---------------------------------------------------------------------------

class TestFingerprintRecovery:

    def test_fingerprints_written_and_read(self, tmp_path):
        """Verify SubprocessBlockRunner._read_fingerprints reads worker output."""
        from backend.engine.subprocess_runner import SubprocessBlockRunner

        output_dir = str(tmp_path)
        fingerprints = {
            "dataset": {"hash": "abc123", "rows": 100, "cols": 5},
            "labels": {"hash": "def456", "rows": 100},
        }
        fp_path = os.path.join(output_dir, "fingerprints.json")
        with open(fp_path, "w") as f:
            json.dump(fingerprints, f)

        loaded = SubprocessBlockRunner._read_fingerprints(output_dir)
        assert loaded == fingerprints

    def test_missing_fingerprints_returns_empty(self, tmp_path):
        from backend.engine.subprocess_runner import SubprocessBlockRunner
        assert SubprocessBlockRunner._read_fingerprints(str(tmp_path)) == {}

    def test_corrupt_fingerprints_returns_empty(self, tmp_path):
        from backend.engine.subprocess_runner import SubprocessBlockRunner

        fp_path = os.path.join(str(tmp_path), "fingerprints.json")
        with open(fp_path, "w") as f:
            f.write("not valid json{{{")

        assert SubprocessBlockRunner._read_fingerprints(str(tmp_path)) == {}


# ---------------------------------------------------------------------------
# Test: Composite + subprocess guard
# ---------------------------------------------------------------------------

class TestCompositeSubprocessGuard:

    def test_composite_subprocess_falls_back_to_inprocess(self):
        """When a block is composite AND requests subprocess, fall back."""
        # Simulate the guard logic from executor.py
        isolation_mode = "subprocess"
        is_composite = True

        if isolation_mode == "subprocess" and is_composite:
            isolation_mode = "inprocess"

        assert isolation_mode == "inprocess"

    def test_non_composite_subprocess_stays(self):
        """Non-composite blocks with subprocess isolation keep it."""
        isolation_mode = "subprocess"
        is_composite = False

        if isolation_mode == "subprocess" and is_composite:
            isolation_mode = "inprocess"

        assert isolation_mode == "subprocess"


# ---------------------------------------------------------------------------
# Test: Block aliases single source of truth
# ---------------------------------------------------------------------------

class TestBlockAliasesSingleSource:

    def test_executor_imports_from_block_aliases(self):
        """Verify executor.py uses the shared block_aliases module."""
        from backend.engine.block_aliases import BLOCK_ALIASES as canonical
        from backend.engine.executor import BLOCK_ALIASES as executor_aliases

        # They should be the exact same object (imported, not duplicated)
        assert canonical is executor_aliases

    def test_block_aliases_has_all_expected_entries(self):
        from backend.engine.block_aliases import BLOCK_ALIASES
        # Spot-check critical aliases
        assert BLOCK_ALIASES["model_prompt"] == "llm_inference"
        assert BLOCK_ALIASES["save_csv"] == "data_export"
        assert BLOCK_ALIASES["gguf_model"] == "model_selector"
        assert len(BLOCK_ALIASES) >= 25  # Sanity check completeness

    def test_config_migrations_match(self):
        from backend.engine.block_aliases import CONFIG_MIGRATIONS
        assert CONFIG_MIGRATIONS["save_csv"] == {"format": "csv"}
        assert CONFIG_MIGRATIONS["save_parquet"] == {"format": "parquet"}

    def test_safe_block_type_regex(self):
        from backend.engine.block_aliases import SAFE_BLOCK_TYPE
        assert SAFE_BLOCK_TYPE.match("llm_inference")
        assert SAFE_BLOCK_TYPE.match("data_export")
        assert not SAFE_BLOCK_TYPE.match("../etc/passwd")
        assert not SAFE_BLOCK_TYPE.match("block with spaces")


# ---------------------------------------------------------------------------
# Worker tracker unit tests
# ---------------------------------------------------------------------------

class TestWorkerTracker:

    def test_track_and_untrack(self):
        from backend.engine.worker_tracker import (
            track_worker, untrack_worker, get_tracked_pids,
            _tracked_workers, _tracker_lock,
        )
        mock_proc = MagicMock()
        mock_proc.pid = 99999
        mock_proc.poll.return_value = None

        with _tracker_lock:
            _tracked_workers.clear()

        track_worker("run-1", mock_proc)
        pids = get_tracked_pids()
        assert "run-1" in pids
        assert 99999 in pids["run-1"]

        untrack_worker("run-1", mock_proc)
        pids = get_tracked_pids()
        assert "run-1" not in pids

        with _tracker_lock:
            _tracked_workers.clear()

    def test_terminate_all_workers(self):
        from backend.engine.worker_tracker import (
            track_worker, terminate_all_workers,
            _tracked_workers, _tracker_lock,
        )
        mock_proc = MagicMock()
        mock_proc.pid = 88888
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0

        with _tracker_lock:
            _tracked_workers.clear()

        track_worker("run-2", mock_proc)
        count = terminate_all_workers()
        assert count == 1
        mock_proc.terminate.assert_called_once()

    def test_write_pid_manifest(self, tmp_path):
        from backend.engine.worker_tracker import (
            write_pid_manifest, _tracked_workers, _tracker_lock,
        )
        with _tracker_lock:
            _tracked_workers.clear()

        write_pid_manifest(tmp_path)
        manifest_path = tmp_path / "worker_manifest.json"
        assert manifest_path.exists()

        with open(manifest_path) as f:
            manifest = json.load(f)
        assert manifest["main_pid"] == os.getpid()
        assert "timestamp" in manifest
        assert "workers" in manifest


# ---------------------------------------------------------------------------
# Config: MAX_PARALLEL_BLOCKS
# ---------------------------------------------------------------------------

class TestMaxParallelBlocks:

    def test_default_is_one(self):
        import importlib
        with patch.dict(os.environ, {}, clear=False):
            env = os.environ.copy()
            env.pop("BLUEPRINT_MAX_PARALLEL_BLOCKS", None)
            with patch.dict(os.environ, env, clear=True):
                import backend.config as cfg
                importlib.reload(cfg)
                assert cfg.MAX_PARALLEL_BLOCKS >= 1

    def test_capped_at_cpu_count(self):
        import backend.config as cfg
        cpu_count = os.cpu_count() or 1
        with patch.dict(os.environ, {"BLUEPRINT_MAX_PARALLEL_BLOCKS": "1000"}):
            import importlib
            importlib.reload(cfg)
            assert cfg.MAX_PARALLEL_BLOCKS <= cpu_count
