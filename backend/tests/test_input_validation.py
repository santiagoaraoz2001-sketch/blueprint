"""
Tests for input validation, connected-input config satisfaction, runtime type
checking, multi-input aggregation, and runtime-prep parity between full and
partial executors.

Run with:
    python -m pytest backend/tests/test_input_validation.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.engine.schema_validator import validate_config, validate_inputs
from backend.engine.runtime_prep import (
    PreparedNode,
    check_input_types,
    apply_multi_input_policy,
    prepare_node_runtime,
)
from backend.block_sdk.exceptions import BlockConfigError, BlockInputError


# ── Fixtures ─────────────────────────────────────────────────────────

def _lora_schema() -> dict:
    """Minimal schema matching the lora_finetuning block's structure."""
    return {
        "name": "LoRA Fine-Tuning",
        "type": "lora_finetuning",
        "inputs": [
            {"id": "dataset", "label": "Training Data", "data_type": "dataset", "required": True},
            {"id": "model", "label": "Base Model", "data_type": "model", "required": False},
        ],
        "outputs": [
            {"id": "model", "label": "Fine-tuned Model", "data_type": "model"},
        ],
        "config": {
            "model_name": {
                "type": "string",
                "label": "Model Name",
                "mandatory": True,
            },
            "r": {
                "type": "integer",
                "label": "LoRA Rank",
                "default": 16,
                "min": 1,
            },
            "lr": {
                "type": "float",
                "label": "Learning Rate",
                "default": 0.0001,
            },
        },
    }


def _typed_input_schema() -> dict:
    """Schema with expected_type_family and cardinality for type-checking tests."""
    return {
        "inputs": [
            {
                "id": "model",
                "label": "Model",
                "data_type": "model",
                "required": False,
                "expected_type_family": "dict",
                "cardinality": "scalar",
            },
            {
                "id": "dataset",
                "label": "Dataset",
                "data_type": "dataset",
                "required": False,
                "expected_type_family": "list",
                "cardinality": "list",
            },
            {
                "id": "text",
                "label": "Text",
                "data_type": "text",
                "required": False,
                "expected_type_family": "str",
                "cardinality": "scalar",
            },
        ],
        "config": {},
    }


def _multi_input_schema() -> dict:
    """Schema with multi_input policies."""
    return {
        "inputs": [
            {
                "id": "data",
                "label": "Data",
                "data_type": "any",
                "multi_input": "aggregate",
            },
            {
                "id": "config",
                "label": "Config",
                "data_type": "config",
                "multi_input": "last_write",
            },
            {
                "id": "model",
                "label": "Model",
                "data_type": "model",
                "multi_input": "error",
            },
        ],
        "config": {},
    }


# ── Test: Connected input satisfies mandatory config ─────────────────

class TestConnectedInputSatisfiesConfig:
    """Task 74/78: Connected inputs satisfy mandatory config fields."""

    def test_connected_model_port_satisfies_model_name(self):
        """When model port is connected, empty model_name should pass validation."""
        schema = _lora_schema()
        config = {"model_name": ""}  # empty — normally would fail

        # Provide connected model input
        inputs = {"model": {"model_id": "meta-llama/Llama-3-8B"}}

        cleaned = validate_config(schema, config, inputs=inputs)
        # Should NOT raise BlockConfigError — the model port satisfies model_name
        assert "model_name" in cleaned or cleaned.get("model_name") == ""

    def test_no_connection_and_empty_model_name_fails(self):
        """Without model port connected, empty model_name must fail."""
        schema = _lora_schema()
        config = {"model_name": ""}

        with pytest.raises(BlockConfigError):
            validate_config(schema, config, inputs=None)

    def test_no_connection_and_no_inputs_arg_fails(self):
        """Without inputs= parameter at all, empty mandatory field fails."""
        schema = _lora_schema()
        config = {"model_name": ""}

        with pytest.raises(BlockConfigError):
            validate_config(schema, config)

    def test_explicit_model_name_still_works(self):
        """When model_name is explicitly set, it works regardless of connections."""
        schema = _lora_schema()
        config = {"model_name": "meta-llama/Llama-3-8B"}

        cleaned = validate_config(schema, config, inputs=None)
        assert cleaned["model_name"] == "meta-llama/Llama-3-8B"

    def test_dataset_name_mapping(self):
        """dataset_name config is satisfied by dataset input port."""
        schema = {
            "config": {
                "dataset_name": {
                    "type": "string",
                    "label": "Dataset",
                    "mandatory": True,
                },
            },
        }
        config = {"dataset_name": ""}
        inputs = {"dataset": [{"text": "hello"}]}
        cleaned = validate_config(schema, config, inputs=inputs)
        # Should not raise
        assert "dataset_name" in cleaned

    def test_teacher_model_mapping(self):
        """teacher_model config is satisfied by teacher input port."""
        schema = {
            "config": {
                "teacher_model": {
                    "type": "string",
                    "label": "Teacher Model",
                    "mandatory": True,
                },
            },
        }
        config = {"teacher_model": ""}
        inputs = {"teacher": {"model_id": "gpt-4"}}
        cleaned = validate_config(schema, config, inputs=inputs)
        assert "teacher_model" in cleaned

    def test_checkpoint_dir_mapping(self):
        """checkpoint_dir config is satisfied by model input port."""
        schema = {
            "config": {
                "checkpoint_dir": {
                    "type": "string",
                    "label": "Checkpoint Dir",
                    "mandatory": True,
                },
            },
        }
        config = {"checkpoint_dir": ""}
        inputs = {"model": "/path/to/checkpoint"}
        cleaned = validate_config(schema, config, inputs=inputs)
        assert "checkpoint_dir" in cleaned

    def test_url_mapping(self):
        """url config is satisfied by config input port."""
        schema = {
            "config": {
                "url": {
                    "type": "string",
                    "label": "URL",
                    "mandatory": True,
                },
            },
        }
        config = {"url": ""}
        inputs = {"config": {"url": "http://example.com"}}
        cleaned = validate_config(schema, config, inputs=inputs)
        assert "url" in cleaned


# ── Test: Runtime type checking ──────────────────────────────────────

class TestRuntimeTypeChecking:
    """Task 75: Runtime type family and cardinality checking."""

    def test_dataset_on_model_port_warns(self):
        """Sending a list (dataset) to a dict-expected (model) port → warning."""
        schema = _typed_input_schema()
        inputs = {"model": [{"item": 1}]}  # list, expected dict
        warnings = check_input_types(schema, inputs)
        assert len(warnings) >= 1
        assert "model" in warnings[0]
        assert "dict" in warnings[0]

    def test_correct_types_no_warnings(self):
        """Correct types produce no warnings."""
        schema = _typed_input_schema()
        inputs = {
            "model": {"name": "llama"},
            "dataset": [{"text": "hello"}],
            "text": "hello world",
        }
        warnings = check_input_types(schema, inputs)
        assert warnings == []

    def test_unexpected_list_on_scalar_input(self):
        """List value on scalar-cardinality port → warning."""
        schema = _typed_input_schema()
        inputs = {"text": ["hello", "world"]}  # list, expected scalar
        warnings = check_input_types(schema, inputs)
        assert any("scalar" in w for w in warnings)

    def test_scalar_on_list_input_warns(self):
        """Scalar value on list-cardinality port → warning."""
        schema = _typed_input_schema()
        inputs = {"dataset": "not a list"}  # str, expected list
        warnings = check_input_types(schema, inputs)
        assert any("list" in w for w in warnings)

    def test_any_type_family_never_warns(self):
        """Ports with expected_type_family='any' accept everything."""
        schema = {
            "inputs": [
                {"id": "data", "data_type": "any", "expected_type_family": "any", "cardinality": "any"},
            ],
        }
        inputs = {"data": {"whatever": True}}
        warnings = check_input_types(schema, inputs)
        assert warnings == []

    def test_none_value_skipped(self):
        """None input values are skipped (handled by validate_inputs)."""
        schema = _typed_input_schema()
        inputs = {"model": None}
        warnings = check_input_types(schema, inputs)
        assert warnings == []

    def test_missing_port_skipped(self):
        """Ports not present in inputs are skipped."""
        schema = _typed_input_schema()
        inputs = {}
        warnings = check_input_types(schema, inputs)
        assert warnings == []


# ── Test: Multi-input aggregation ────────────────────────────────────

class TestMultiInputPolicy:
    """Task 75: Multi-input aggregation policies."""

    def test_aggregate_keeps_list(self):
        """'aggregate' policy: values stay as collected list."""
        schema = _multi_input_schema()
        inputs = {"data": ["val1", "val2"]}
        multi_counts = {"data": 2}
        result = apply_multi_input_policy(schema, inputs, multi_counts)
        assert result["data"] == ["val1", "val2"]

    def test_last_write_keeps_last(self):
        """'last_write' policy: only last value retained."""
        schema = _multi_input_schema()
        inputs = {"config": [{"a": 1}, {"b": 2}]}
        multi_counts = {"config": 2}
        result = apply_multi_input_policy(schema, inputs, multi_counts)
        assert result["config"] == {"b": 2}

    def test_error_policy_raises(self):
        """'error' policy: raises BlockInputError on multiple connections."""
        schema = _multi_input_schema()
        inputs = {"model": ["m1", "m2"]}
        multi_counts = {"model": 2}
        with pytest.raises(BlockInputError, match="multiple connections"):
            apply_multi_input_policy(schema, inputs, multi_counts)

    def test_single_connection_no_policy_change(self):
        """Single connection: no policy applied regardless of mode."""
        schema = _multi_input_schema()
        inputs = {"model": "single_model"}
        multi_counts = {"model": 1}
        result = apply_multi_input_policy(schema, inputs, multi_counts)
        assert result["model"] == "single_model"


# ── Test: Runtime prep parity ────────────────────────────────────────

class TestRuntimePrepParity:
    """Task 77/78: Full executor and partial executor produce identical
    PreparedNode for the same node configuration."""

    @pytest.fixture
    def mock_block_dir(self, tmp_path):
        """Create a minimal block directory with block.yaml."""
        block_dir = tmp_path / "test_block"
        block_dir.mkdir()
        (block_dir / "run.py").write_text("def run(ctx): pass\n")
        (block_dir / "block.yaml").write_text(
            "name: Test\n"
            "type: test_block\n"
            "version: '1.0.0'\n"
            "timeout: 300\n"
            "max_retries: 2\n"
            "composite: false\n"
            "inputs:\n"
            "  - id: model\n"
            "    label: Model\n"
            "    data_type: model\n"
            "    required: false\n"
            "outputs:\n"
            "  - id: result\n"
            "    label: Result\n"
            "    data_type: text\n"
            "config:\n"
            "  model_name:\n"
            "    type: string\n"
            "    label: Model Name\n"
            "    mandatory: true\n"
        )
        return block_dir

    def test_full_and_partial_produce_identical_prepared_node(self, mock_block_dir, tmp_path):
        """Both executors must produce the same PreparedNode for identical inputs."""
        def find_block_fn(block_type):
            if block_type == "test_block":
                return mock_block_dir
            return None

        def resolve_secrets_fn(config):
            return dict(config)

        node_inputs = {"model": {"model_id": "meta-llama/Llama-3-8B"}}
        config = {"model_name": ""}  # empty but satisfied by model input

        # Simulate "full executor" calling prepare_node_runtime
        full_prepared = prepare_node_runtime(
            node_id="node_1",
            block_type="test_block",
            config=config.copy(),
            node_inputs=node_inputs,
            run_id="run_full",
            find_block_fn=find_block_fn,
            resolve_secrets_fn=resolve_secrets_fn,
        )

        # Simulate "partial executor" calling prepare_node_runtime
        partial_prepared = prepare_node_runtime(
            node_id="node_1",
            block_type="test_block",
            config=config.copy(),
            node_inputs=node_inputs,
            run_id="run_partial",
            find_block_fn=find_block_fn,
            resolve_secrets_fn=resolve_secrets_fn,
        )

        # Core metadata must be identical
        assert full_prepared.block_type == partial_prepared.block_type
        assert full_prepared.block_dir == partial_prepared.block_dir
        assert full_prepared.timeout_seconds == partial_prepared.timeout_seconds
        assert full_prepared.max_retries == partial_prepared.max_retries
        assert full_prepared.is_composite == partial_prepared.is_composite
        assert full_prepared.cleaned_config == partial_prepared.cleaned_config
        assert full_prepared.block_version == partial_prepared.block_version
        assert full_prepared.context_cls == partial_prepared.context_cls

    def test_block_not_found_raises_runtime_error(self):
        """Missing block type raises RuntimeError."""
        def find_block_fn(block_type):
            return None

        def resolve_secrets_fn(config):
            return dict(config)

        with pytest.raises(RuntimeError, match="not found"):
            prepare_node_runtime(
                node_id="node_1",
                block_type="nonexistent_block",
                config={},
                node_inputs={},
                run_id="test_run",
                find_block_fn=find_block_fn,
                resolve_secrets_fn=resolve_secrets_fn,
            )

    def test_connected_input_passes_validation_in_prep(self, mock_block_dir):
        """prepare_node_runtime should not raise when connected input satisfies config."""
        def find_block_fn(block_type):
            return mock_block_dir

        def resolve_secrets_fn(config):
            return dict(config)

        # model_name is mandatory but empty; model input is connected
        prepared = prepare_node_runtime(
            node_id="node_1",
            block_type="test_block",
            config={"model_name": ""},
            node_inputs={"model": {"id": "test-model"}},
            run_id="test_run",
            find_block_fn=find_block_fn,
            resolve_secrets_fn=resolve_secrets_fn,
        )
        assert prepared is not None
        assert prepared.block_version == "1.0.0"
        assert prepared.timeout_seconds == 300
        assert prepared.max_retries == 2
