"""Tests for the validation gateway and error classification.

Covers:
  1. Execution blocked without valid plan (HTTP 400)
  2. Execution allowed with valid plan
  3. Pre-validation endpoint returns fast (<500ms)
  4. Stale handle detection (outdated block version)
  5. Error classification: ConnectionRefusedError
  6. Error classification: FileNotFoundError

Run with:
    python -m pytest backend/tests/test_validation_gateway.py -v
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.engine.validator import validate_pipeline, ValidationReport
from backend.engine.error_classifier import classify_error, ClassifiedError


# ══════════════════════════════════════════════════════════════════════════════
# Test fixtures — minimal pipeline definitions
# ══════════════════════════════════════════════════════════════════════════════

def _make_node(node_id: str, block_type: str = "llm_inference", label: str = "Test Block", config: dict | None = None, inputs: list | None = None, outputs: list | None = None):
    """Create a minimal node dict matching the pipeline definition schema."""
    return {
        "id": node_id,
        "type": "blockNode",
        "data": {
            "type": block_type,
            "label": label,
            "config": config or {},
            "inputs": inputs or [{"id": "input", "label": "Input", "dataType": "any", "required": False}],
            "outputs": outputs or [{"id": "output", "label": "Output", "dataType": "any"}],
            "category": "inference",
        },
        "position": {"x": 0, "y": 0},
    }


def _make_edge(source: str, target: str, source_handle: str = "output", target_handle: str = "input"):
    return {
        "id": f"{source}-{target}",
        "source": source,
        "target": target,
        "sourceHandle": source_handle,
        "targetHandle": target_handle,
    }


def _valid_pipeline():
    """A minimal valid two-node pipeline."""
    return {
        "nodes": [
            _make_node("node-1", block_type="local_file_loader", label="Loader", config={"file_path": "/data/test.csv"}),
            _make_node("node-2", block_type="llm_inference", label="LLM", config={"model_name": "gpt-4"}),
        ],
        "edges": [
            _make_edge("node-1", "node-2"),
        ],
    }


def _invalid_pipeline():
    """A pipeline with a cycle and missing required config."""
    return {
        "nodes": [
            _make_node("a", block_type="llm_inference", label="Block A"),
            _make_node("b", block_type="llm_inference", label="Block B"),
        ],
        "edges": [
            _make_edge("a", "b"),
            _make_edge("b", "a"),  # Creates a cycle
        ],
    }


# ══════════════════════════════════════════════════════════════════════════════
# Test 1: Execution blocked without valid plan
# ══════════════════════════════════════════════════════════════════════════════

class TestExecuteBlockedWithoutValidPlan:
    def test_invalid_pipeline_returns_validation_errors(self):
        """An invalid pipeline must not pass validation (simulates execution gate)."""
        definition = _invalid_pipeline()
        report = validate_pipeline(definition)

        assert report.valid is False
        assert len(report.errors) > 0
        # Should detect the cycle
        assert any("cycle" in e.lower() for e in report.errors)

    def test_empty_pipeline_fails_validation(self):
        """A pipeline with no nodes fails validation."""
        report = validate_pipeline({"nodes": [], "edges": []})
        assert report.valid is False
        assert any("no blocks" in e.lower() for e in report.errors)


# ══════════════════════════════════════════════════════════════════════════════
# Test 2: Execution allowed with valid plan
# ══════════════════════════════════════════════════════════════════════════════

class TestExecuteAllowedWithValidPlan:
    def test_valid_pipeline_passes(self):
        """A well-formed pipeline passes validation."""
        definition = _valid_pipeline()
        report = validate_pipeline(definition)

        assert report.valid is True
        assert len(report.errors) == 0
        assert report.block_count == 2
        assert report.edge_count == 1


# ══════════════════════════════════════════════════════════════════════════════
# Test 3: Pre-validation endpoint responds fast
# ══════════════════════════════════════════════════════════════════════════════

class TestPreValidationEndpointFast:
    def test_validation_completes_within_500ms(self):
        """validate_pipeline() should complete in under 500ms for a typical pipeline."""
        # Build a moderately sized pipeline (10 nodes, 9 edges — chain)
        nodes = [
            _make_node(f"node-{i}", block_type="llm_inference", label=f"Block {i}", config={"model_name": "test"})
            for i in range(10)
        ]
        edges = [
            _make_edge(f"node-{i}", f"node-{i+1}")
            for i in range(9)
        ]
        definition = {"nodes": nodes, "edges": edges}

        start = time.monotonic()
        report = validate_pipeline(definition)
        elapsed_ms = (time.monotonic() - start) * 1000

        assert elapsed_ms < 500, f"Validation took {elapsed_ms:.0f}ms, expected <500ms"
        assert report.block_count == 10

    def test_validation_fast_for_large_pipeline(self):
        """Even 50-node pipelines should validate quickly."""
        nodes = [
            _make_node(f"node-{i}", block_type="llm_inference", label=f"Block {i}", config={"model_name": "test"})
            for i in range(50)
        ]
        # Build a chain
        edges = [
            _make_edge(f"node-{i}", f"node-{i+1}")
            for i in range(49)
        ]
        definition = {"nodes": nodes, "edges": edges}

        start = time.monotonic()
        report = validate_pipeline(definition)
        elapsed_ms = (time.monotonic() - start) * 1000

        assert elapsed_ms < 500, f"Validation took {elapsed_ms:.0f}ms, expected <500ms"
        assert report.block_count == 50


# ══════════════════════════════════════════════════════════════════════════════
# Test 4: Stale handle detection
# ══════════════════════════════════════════════════════════════════════════════

class TestStaleHandleDetection:
    def test_stale_handle_with_removed_ports(self):
        """When a saved node references ports that no longer exist in the registry,
        the validator should produce a blocking error."""
        # Node was saved with block_version "1.0" and has port "old_port"
        node = _make_node(
            "stale-node",
            block_type="llm_inference",
            label="Stale Block",
            config={"model_name": "test"},
            inputs=[{"id": "old_port", "label": "Old Input", "dataType": "any", "required": False}],
            outputs=[{"id": "output", "label": "Output", "dataType": "any"}],
        )
        node["data"]["block_version"] = "1.0"

        # Mock the block registry to return a block.yaml with version "2.0" and no "old_port"
        mock_yaml = {
            "version": "2.0",
            "inputs": [{"id": "new_port", "label": "New Input", "dataType": "any"}],
            "outputs": [{"id": "output", "label": "Output", "dataType": "any"}],
        }

        definition = {"nodes": [node], "edges": []}

        with patch("backend.engine.validator.is_known_block", return_value=True), \
             patch("backend.engine.validator.get_block_yaml", return_value=mock_yaml):
            report = validate_pipeline(definition)

        # Should have a blocking error about removed ports
        assert report.valid is False
        stale_errors = [e for e in report.errors if "outdated ports" in e.lower() or "stale" in e.lower()]
        assert len(stale_errors) > 0, f"Expected stale handle error, got: {report.errors}"

    def test_compatible_version_upgrade_is_warning(self):
        """Version upgrade that only adds ports (non-breaking) should produce a warning, not an error."""
        node = _make_node(
            "compat-node",
            block_type="llm_inference",
            label="Compatible Block",
            config={"model_name": "test"},
            inputs=[{"id": "input", "label": "Input", "dataType": "any", "required": False}],
            outputs=[{"id": "output", "label": "Output", "dataType": "any"}],
        )
        node["data"]["block_version"] = "1.0"

        # Registry has the same ports + a new one
        mock_yaml = {
            "version": "1.1",
            "inputs": [
                {"id": "input", "label": "Input", "dataType": "any"},
                {"id": "extra_input", "label": "Extra", "dataType": "any"},
            ],
            "outputs": [{"id": "output", "label": "Output", "dataType": "any"}],
        }

        definition = {"nodes": [node], "edges": []}

        with patch("backend.engine.validator.is_known_block", return_value=True), \
             patch("backend.engine.validator.get_block_yaml", return_value=mock_yaml):
            report = validate_pipeline(definition)

        # Should pass (non-breaking change) with a warning
        assert report.valid is True
        assert any("compatible" in w.lower() or "version" in w.lower() for w in report.warnings)


# ══════════════════════════════════════════════════════════════════════════════
# Test 5: Error classification — ConnectionRefusedError
# ══════════════════════════════════════════════════════════════════════════════

class TestErrorClassificationConnectionRefused:
    def test_classify_connection_refused(self):
        exc = ConnectionRefusedError("Connection refused to localhost:8080")
        result = classify_error(exc)

        assert isinstance(result, ClassifiedError)
        assert result.title == "Service Unavailable"
        assert result.severity == "error"
        assert "connect" in result.message.lower()
        assert result.original_type == "ConnectionRefusedError"

    def test_classify_connection_refused_with_block_type(self):
        exc = ConnectionRefusedError("Connection refused")
        result = classify_error(exc, block_type="api_caller")

        assert result.block_type == "api_caller"
        assert result.title == "Service Unavailable"


# ══════════════════════════════════════════════════════════════════════════════
# Test 6: Error classification — FileNotFoundError
# ══════════════════════════════════════════════════════════════════════════════

class TestErrorClassificationFileNotFound:
    def test_classify_file_not_found(self):
        exc = FileNotFoundError(2, "No such file or directory", "/data/model.bin")
        result = classify_error(exc)

        assert isinstance(result, ClassifiedError)
        assert result.title == "File Not Found"
        assert result.severity == "error"
        assert "/data/model.bin" in result.message
        assert "path" in result.action.lower()

    def test_classify_file_not_found_from_message(self):
        exc = FileNotFoundError("No such file or directory: '/path/to/data.csv'")
        result = classify_error(exc)

        assert result.title == "File Not Found"
        assert result.severity == "error"

    def test_classify_returns_dict(self):
        exc = FileNotFoundError("missing file")
        result = classify_error(exc)
        d = result.to_dict()

        assert isinstance(d, dict)
        assert "title" in d
        assert "message" in d
        assert "action" in d
        assert "severity" in d
        assert "original_type" in d


# ══════════════════════════════════════════════════════════════════════════════
# Additional error classification tests (coverage for 15+ types)
# ══════════════════════════════════════════════════════════════════════════════

class TestErrorClassificationCoverage:
    """Ensure all 15+ error types in ERROR_MAP produce correct ClassifiedError instances."""

    @pytest.mark.parametrize("exc,expected_title", [
        (MemoryError("out of memory"), "Out of Memory"),
        (json.JSONDecodeError("Expecting value", "doc", 0), "Invalid Data Format"),
        (ImportError("No module named 'torch'", name="torch"), "Missing Dependency"),
        (ModuleNotFoundError("No module named 'mlx'", name="mlx"), "Missing Dependency"),
        (PermissionError("Permission denied: '/data'"), "Permission Denied"),
        (TimeoutError("timed out"), "Operation Timed Out"),
        (ValueError("invalid literal"), "Invalid Value"),
        (KeyError("missing_key"), "Missing Key"),
        (RuntimeError("generic runtime error"), "Runtime Error"),
        (OSError("disk full"), "System Error"),
        (TypeError("expected str, got int"), "Type Mismatch"),
        (StopIteration(), "Empty Dataset"),
        (UnicodeDecodeError("utf-8", b"", 0, 1, "invalid"), "Encoding Error"),
        (ZeroDivisionError("division by zero"), "Division by Zero"),
        (NotImplementedError("not supported"), "Not Implemented"),
        (OverflowError("numeric overflow"), "Numeric Overflow"),
    ])
    def test_error_type_classified(self, exc, expected_title):
        result = classify_error(exc)
        assert result.title == expected_title
        assert result.severity == "error"
        assert isinstance(result.message, str)
        assert isinstance(result.action, str)

    def test_unknown_exception_fallback(self):
        """Unknown exception types get a generic 'Unexpected Error' classification."""

        class CustomBlockError(Exception):
            pass

        result = classify_error(CustomBlockError("something broke"))
        assert result.title == "Unexpected Error"
        assert "something broke" in result.message

    def test_cuda_oom_pattern(self):
        """RuntimeError with CUDA OOM message gets specialized classification."""
        exc = RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")
        result = classify_error(exc)
        assert result.title == "GPU Out of Memory"
        assert "batch size" in result.action.lower() or "model" in result.action.lower()

    def test_tensor_shape_mismatch(self):
        """RuntimeError about shape/dimension mismatch gets specialized classification."""
        exc = RuntimeError("size mismatch for layer.weight: expected [512, 768], got [256, 768]")
        result = classify_error(exc)
        assert result.title == "Tensor Shape Mismatch"
