"""Unit tests for the block validation framework.

Tests the exception hierarchy, config validation (type checking, defaults,
bounds, select options), and the block runner infrastructure.

Run with:
    python -m pytest backend/tests/test_block_validation.py -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.block_sdk.exceptions import (
    BlockConfigError,
    BlockDependencyError,
    BlockError,
    BlockExecutionError,
    BlockInputError,
    BlockOutputError,
    BlockTimeoutError,
)
from backend.block_sdk.config_validator import validate_and_apply_defaults

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ══════════════════════════════════════════════════════════════════════════════
# Exception hierarchy tests
# ══════════════════════════════════════════════════════════════════════════════


class TestExceptionHierarchy:
    """Verify all exception types inherit from BlockError correctly."""

    def test_block_error_base(self):
        e = BlockError("base error")
        assert str(e) == "base error"
        assert e.details == ""
        assert e.recoverable is False

    def test_block_error_with_details(self):
        e = BlockError("error", details="extra info", recoverable=True)
        assert e.details == "extra info"
        assert e.recoverable is True

    def test_block_config_error_inherits(self):
        e = BlockConfigError("lr", "bad config")
        assert isinstance(e, BlockError)
        assert isinstance(e, BlockConfigError)
        assert isinstance(e, Exception)
        assert e.field == "lr"
        assert e.recoverable is True  # default for config errors

    def test_block_input_error_inherits(self):
        e = BlockInputError("missing input", details="dataset field")
        assert isinstance(e, BlockError)
        assert e.details == "dataset field"

    def test_block_output_error_defaults_recoverable(self):
        e = BlockOutputError("no output")
        assert isinstance(e, BlockError)
        assert e.recoverable is True  # default for outputs

    def test_block_output_error_override_recoverable(self):
        e = BlockOutputError("critical", recoverable=False)
        assert e.recoverable is False

    def test_block_execution_error_inherits(self):
        e = BlockExecutionError("runtime crash")
        assert isinstance(e, BlockError)
        assert e.recoverable is False

    def test_block_dependency_error_inherits(self):
        e = BlockDependencyError("torch")
        assert isinstance(e, BlockError)
        assert e.recoverable is False
        assert "torch" in str(e)

    def test_block_timeout_error_inherits(self):
        e = BlockTimeoutError(60)
        assert isinstance(e, BlockError)
        assert e.recoverable is False
        assert e.timeout_seconds == 60

    def test_all_catchable_as_block_error(self):
        """All subclasses should be catchable with ``except BlockError``."""
        exceptions = [
            BlockConfigError("f", "a"),
            BlockInputError("b"),
            BlockOutputError("c"),
            BlockExecutionError("d"),
            BlockDependencyError("e"),
            BlockTimeoutError(30),
        ]
        for exc in exceptions:
            try:
                raise exc
            except BlockError as caught:
                assert caught is exc
            else:
                pytest.fail(f"{type(exc).__name__} was not caught by BlockError")

    def test_not_catchable_as_wrong_subclass(self):
        """A BlockConfigError should not be catchable as BlockInputError."""
        with pytest.raises(BlockConfigError):
            try:
                raise BlockConfigError("field", "config issue")
            except BlockInputError:
                pytest.fail("BlockConfigError caught by BlockInputError")

    def test_error_message_preserved(self):
        msg = "model_name is required but was not provided"
        e = BlockConfigError("model_name", msg)
        assert str(e) == msg
        assert msg in repr(e)
        assert e.field == "model_name"


# ══════════════════════════════════════════════════════════════════════════════
# Config validation: type checking
# ══════════════════════════════════════════════════════════════════════════════


class TestTypeValidation:
    """Test that schema validation catches type mismatches."""

    # ── Integer ───────────────────────────────────────────────────────────

    def test_integer_valid(self):
        schema = {"epochs": {"type": "integer", "default": 3}}
        result = validate_and_apply_defaults({"epochs": 5}, schema)
        assert result["epochs"] == 5

    def test_integer_rejects_non_numeric_string(self):
        schema = {"epochs": {"type": "integer"}}
        with pytest.raises(BlockConfigError, match="must be an integer"):
            validate_and_apply_defaults({"epochs": "not_a_number"}, schema)

    def test_integer_accepts_numeric_string(self):
        """CLI passes integers as strings — they should be accepted."""
        schema = {"epochs": {"type": "integer"}}
        validate_and_apply_defaults({"epochs": "5"}, schema)

    def test_integer_rejects_bool_true(self):
        """Python bool is subclass of int, but should be rejected."""
        schema = {"epochs": {"type": "integer"}}
        with pytest.raises(BlockConfigError, match="must be an integer"):
            validate_and_apply_defaults({"epochs": True}, schema)

    def test_integer_rejects_bool_false(self):
        schema = {"epochs": {"type": "integer"}}
        with pytest.raises(BlockConfigError, match="must be an integer"):
            validate_and_apply_defaults({"epochs": False}, schema)

    def test_integer_accepts_whole_float(self):
        """YAML may parse ``5`` as ``5.0`` — whole floats are OK."""
        schema = {"epochs": {"type": "integer"}}
        validate_and_apply_defaults({"epochs": 5.0}, schema)

    def test_integer_rejects_fractional_float(self):
        schema = {"epochs": {"type": "integer"}}
        with pytest.raises(BlockConfigError, match="must be an integer"):
            validate_and_apply_defaults({"epochs": 5.5}, schema)

    def test_integer_rejects_list(self):
        schema = {"epochs": {"type": "integer"}}
        with pytest.raises(BlockConfigError, match="must be an integer"):
            validate_and_apply_defaults({"epochs": [5]}, schema)

    # ── Float ─────────────────────────────────────────────────────────────

    def test_float_valid(self):
        schema = {"lr": {"type": "float"}}
        result = validate_and_apply_defaults({"lr": 0.001}, schema)
        assert result["lr"] == 0.001

    def test_float_rejects_non_numeric_string(self):
        schema = {"lr": {"type": "float"}}
        with pytest.raises(BlockConfigError, match="must be a number"):
            validate_and_apply_defaults({"lr": "fast"}, schema)

    def test_float_accepts_numeric_string(self):
        schema = {"lr": {"type": "float"}}
        validate_and_apply_defaults({"lr": "0.001"}, schema)

    def test_float_accepts_int(self):
        schema = {"lr": {"type": "float"}}
        result = validate_and_apply_defaults({"lr": 1}, schema)
        assert result["lr"] == 1

    def test_float_rejects_bool(self):
        schema = {"lr": {"type": "float"}}
        with pytest.raises(BlockConfigError, match="must be a number"):
            validate_and_apply_defaults({"lr": True}, schema)

    def test_float_rejects_dict(self):
        schema = {"lr": {"type": "float"}}
        with pytest.raises(BlockConfigError, match="must be a number"):
            validate_and_apply_defaults({"lr": {"value": 0.1}}, schema)

    # ── Boolean ───────────────────────────────────────────────────────────

    def test_boolean_true(self):
        schema = {"flag": {"type": "boolean"}}
        result = validate_and_apply_defaults({"flag": True}, schema)
        assert result["flag"] is True

    def test_boolean_false(self):
        schema = {"flag": {"type": "boolean"}}
        result = validate_and_apply_defaults({"flag": False}, schema)
        assert result["flag"] is False

    def test_boolean_rejects_number(self):
        schema = {"flag": {"type": "boolean"}}
        with pytest.raises(BlockConfigError, match="must be a boolean"):
            validate_and_apply_defaults({"flag": 42}, schema)

    def test_boolean_accepts_string_true(self):
        schema = {"flag": {"type": "boolean"}}
        validate_and_apply_defaults({"flag": "true"}, schema)

    def test_boolean_accepts_string_false(self):
        schema = {"flag": {"type": "boolean"}}
        validate_and_apply_defaults({"flag": "false"}, schema)

    def test_boolean_rejects_string_yes(self):
        schema = {"flag": {"type": "boolean"}}
        with pytest.raises(BlockConfigError, match="must be a boolean"):
            validate_and_apply_defaults({"flag": "yes"}, schema)

    def test_boolean_rejects_zero(self):
        """0 is falsy but not a boolean."""
        schema = {"flag": {"type": "boolean"}}
        with pytest.raises(BlockConfigError, match="must be a boolean"):
            validate_and_apply_defaults({"flag": 0}, schema)

    # ── Select ────────────────────────────────────────────────────────────

    def test_select_rejects_non_string(self):
        schema = {"fmt": {"type": "select", "options": ["a", "b"]}}
        with pytest.raises(BlockConfigError, match="must be a string"):
            validate_and_apply_defaults({"fmt": 123}, schema)

    # ── String types ──────────────────────────────────────────────────────

    def test_string_valid(self):
        schema = {"name": {"type": "string"}}
        result = validate_and_apply_defaults({"name": "gpt2"}, schema)
        assert result["name"] == "gpt2"

    def test_string_rejects_number(self):
        schema = {"name": {"type": "string"}}
        with pytest.raises(BlockConfigError, match="must be a string"):
            validate_and_apply_defaults({"name": 123}, schema)

    def test_text_area_rejects_number(self):
        schema = {"prompt": {"type": "text_area"}}
        with pytest.raises(BlockConfigError, match="must be a string"):
            validate_and_apply_defaults({"prompt": 42}, schema)

    def test_file_path_rejects_number(self):
        schema = {"path": {"type": "file_path"}}
        with pytest.raises(BlockConfigError, match="must be a string"):
            validate_and_apply_defaults({"path": 42}, schema)

    # ── Unknown types pass through ────────────────────────────────────────

    def test_unknown_type_passes(self):
        """Unknown config types should not raise — future-proof."""
        schema = {"custom": {"type": "my_widget"}}
        result = validate_and_apply_defaults({"custom": "anything"}, schema)
        assert result["custom"] == "anything"


# ══════════════════════════════════════════════════════════════════════════════
# Config validation: default application
# ══════════════════════════════════════════════════════════════════════════════


class TestDefaultApplication:
    """Test that defaults from block.yaml are applied correctly."""

    def test_missing_field_gets_default(self):
        schema = {"epochs": {"type": "integer", "default": 5}}
        result = validate_and_apply_defaults({}, schema)
        assert result["epochs"] == 5

    def test_none_value_gets_default(self):
        schema = {"lr": {"type": "float", "default": 0.001}}
        result = validate_and_apply_defaults({"lr": None}, schema)
        assert result["lr"] == 0.001

    def test_empty_string_gets_default(self):
        schema = {"name": {"type": "string", "default": "gpt2"}}
        result = validate_and_apply_defaults({"name": ""}, schema)
        assert result["name"] == "gpt2"

    def test_explicit_value_overrides_default(self):
        schema = {"epochs": {"type": "integer", "default": 5}}
        result = validate_and_apply_defaults({"epochs": 10}, schema)
        assert result["epochs"] == 10

    def test_multiple_defaults_applied(self):
        schema = {
            "epochs": {"type": "integer", "default": 3},
            "lr": {"type": "float", "default": 0.001},
            "name": {"type": "string", "default": "test"},
        }
        result = validate_and_apply_defaults({}, schema)
        assert result["epochs"] == 3
        assert result["lr"] == 0.001
        assert result["name"] == "test"

    def test_no_default_stays_missing(self):
        schema = {"model_name": {"type": "string"}}
        result = validate_and_apply_defaults({}, schema)
        assert "model_name" not in result

    def test_false_boolean_not_replaced_by_default(self):
        """False is a valid value, not missing."""
        schema = {"flag": {"type": "boolean", "default": True}}
        result = validate_and_apply_defaults({"flag": False}, schema)
        assert result["flag"] is False

    def test_zero_not_replaced_by_default(self):
        """0 is a valid value, not missing."""
        schema = {"count": {"type": "integer", "default": 10}}
        result = validate_and_apply_defaults({"count": 0}, schema)
        assert result["count"] == 0

    def test_extra_keys_preserved(self):
        """Config keys not in schema should pass through untouched."""
        schema = {"epochs": {"type": "integer", "default": 3}}
        result = validate_and_apply_defaults({"epochs": 5, "custom_key": "value"}, schema)
        assert result["custom_key"] == "value"

    def test_non_dict_schema_entry_skipped(self):
        """Schema entries that aren't dicts (e.g. comments) are skipped."""
        schema = {"epochs": {"type": "integer", "default": 3}, "_comment": "this is a note"}
        result = validate_and_apply_defaults({}, schema)
        assert result["epochs"] == 3


# ══════════════════════════════════════════════════════════════════════════════
# Config validation: bounds checking
# ══════════════════════════════════════════════════════════════════════════════


class TestBoundsChecking:
    """Test min/max enforcement for numeric config fields."""

    def test_within_bounds_passes(self):
        schema = {"lr": {"type": "float", "min": 0.0, "max": 1.0}}
        result = validate_and_apply_defaults({"lr": 0.5}, schema)
        assert result["lr"] == 0.5

    def test_at_min_boundary_passes(self):
        schema = {"epochs": {"type": "integer", "min": 1, "max": 100}}
        result = validate_and_apply_defaults({"epochs": 1}, schema)
        assert result["epochs"] == 1

    def test_at_max_boundary_passes(self):
        schema = {"epochs": {"type": "integer", "min": 1, "max": 100}}
        result = validate_and_apply_defaults({"epochs": 100}, schema)
        assert result["epochs"] == 100

    def test_below_min_raises(self):
        schema = {"epochs": {"type": "integer", "min": 1, "max": 100}}
        with pytest.raises(BlockConfigError, match="below minimum"):
            validate_and_apply_defaults({"epochs": 0}, schema)

    def test_above_max_raises(self):
        schema = {"epochs": {"type": "integer", "min": 1, "max": 100}}
        with pytest.raises(BlockConfigError, match="above maximum"):
            validate_and_apply_defaults({"epochs": 999}, schema)

    def test_float_below_min_raises(self):
        schema = {"lr": {"type": "float", "min": 0.0001, "max": 0.01}}
        with pytest.raises(BlockConfigError, match="below minimum"):
            validate_and_apply_defaults({"lr": 0.00001}, schema)

    def test_float_above_max_raises(self):
        schema = {"lr": {"type": "float", "min": 0.0, "max": 1.0}}
        with pytest.raises(BlockConfigError, match="above maximum"):
            validate_and_apply_defaults({"lr": 1.5}, schema)

    def test_no_min_allows_low_values(self):
        schema = {"lr": {"type": "float", "max": 1.0}}
        result = validate_and_apply_defaults({"lr": -100.0}, schema)
        assert result["lr"] == -100.0

    def test_no_max_allows_high_values(self):
        schema = {"epochs": {"type": "integer", "min": 1}}
        result = validate_and_apply_defaults({"epochs": 999999}, schema)
        assert result["epochs"] == 999999

    def test_default_within_bounds_passes(self):
        """Default values should also be within bounds."""
        schema = {"lr": {"type": "float", "default": 0.5, "min": 0.0, "max": 1.0}}
        result = validate_and_apply_defaults({}, schema)
        assert result["lr"] == 0.5

    def test_negative_integer_within_bounds(self):
        schema = {"offset": {"type": "integer", "min": -10, "max": 10}}
        result = validate_and_apply_defaults({"offset": -5}, schema)
        assert result["offset"] == -5


# ══════════════════════════════════════════════════════════════════════════════
# Config validation: select options
# ══════════════════════════════════════════════════════════════════════════════


class TestSelectValidation:
    """Test select field option enforcement."""

    def test_valid_option_passes(self):
        schema = {"format": {"type": "select", "options": ["plain", "json", "csv"]}}
        result = validate_and_apply_defaults({"format": "json"}, schema)
        assert result["format"] == "json"

    def test_invalid_option_raises(self):
        schema = {"format": {"type": "select", "options": ["plain", "json", "csv"]}}
        with pytest.raises(BlockConfigError, match="not in allowed options"):
            validate_and_apply_defaults({"format": "xml"}, schema)

    def test_empty_options_list_passes(self):
        """No options defined = accept anything."""
        schema = {"format": {"type": "select", "options": []}}
        result = validate_and_apply_defaults({"format": "anything"}, schema)
        assert result["format"] == "anything"

    def test_default_must_be_valid_option(self):
        """When a default is applied, it should still pass validation."""
        schema = {"format": {"type": "select", "options": ["a", "b"], "default": "a"}}
        result = validate_and_apply_defaults({}, schema)
        assert result["format"] == "a"

    def test_case_sensitive_options(self):
        """Select matching should be case-sensitive."""
        schema = {"format": {"type": "select", "options": ["json", "JSON"]}}
        with pytest.raises(BlockConfigError, match="not in allowed options"):
            validate_and_apply_defaults({"format": "Json"}, schema)


# ══════════════════════════════════════════════════════════════════════════════
# Config validation: real block.yaml schemas
# ══════════════════════════════════════════════════════════════════════════════


class TestRealBlockSchemas:
    """Test validation against actual block.yaml config schemas."""

    @pytest.fixture
    def ballast_schema(self):
        yaml_path = PROJECT_ROOT / "blocks" / "training" / "ballast_training" / "block.yaml"
        if not yaml_path.exists():
            pytest.skip("ballast_training block not found")
        import yaml as pyyaml

        with open(yaml_path) as f:
            spec = pyyaml.safe_load(f)
        return spec.get("config", {})

    @pytest.fixture
    def text_input_schema(self):
        yaml_path = PROJECT_ROOT / "blocks" / "data" / "text_input" / "block.yaml"
        if not yaml_path.exists():
            pytest.skip("text_input block not found")
        import yaml as pyyaml

        with open(yaml_path) as f:
            spec = pyyaml.safe_load(f)
        return spec.get("config", {})

    def test_ballast_defaults_applied(self, ballast_schema):
        result = validate_and_apply_defaults({}, ballast_schema)
        assert result["layer_depth"] == 0.5
        assert result["epochs"] == 5
        assert result["batch_size"] == 4

    def test_ballast_lr_out_of_bounds(self, ballast_schema):
        with pytest.raises(BlockConfigError, match="above maximum"):
            validate_and_apply_defaults({"lr": 1.0}, ballast_schema)

    def test_ballast_valid_config(self, ballast_schema):
        config = {"model_name": "gpt2", "epochs": 3, "lr": 0.0001}
        result = validate_and_apply_defaults(config, ballast_schema)
        assert result["model_name"] == "gpt2"
        assert result["epochs"] == 3

    def test_ballast_layer_depth_bounds(self, ballast_schema):
        with pytest.raises(BlockConfigError, match="below minimum"):
            validate_and_apply_defaults({"layer_depth": 0.01}, ballast_schema)
        with pytest.raises(BlockConfigError, match="above maximum"):
            validate_and_apply_defaults({"layer_depth": 2.0}, ballast_schema)

    def test_text_input_select_validation(self, text_input_schema):
        result = validate_and_apply_defaults({"format": "json"}, text_input_schema)
        assert result["format"] == "json"

    def test_text_input_invalid_format(self, text_input_schema):
        with pytest.raises(BlockConfigError, match="not in allowed options"):
            validate_and_apply_defaults({"format": "xml"}, text_input_schema)


# ══════════════════════════════════════════════════════════════════════════════
# Fixture file tests
# ══════════════════════════════════════════════════════════════════════════════


class TestFixtureFiles:
    """Verify fixture files are well-formed and contain expected data."""

    def test_small_fixture_has_10_rows(self):
        path = FIXTURES_DIR / "small.jsonl"
        assert path.exists(), "small.jsonl not found"
        rows = [json.loads(line) for line in path.read_text().strip().split("\n")]
        assert len(rows) == 10
        for row in rows:
            assert "text" in row, f"Row missing 'text': {row}"
            assert "label" in row, f"Row missing 'label': {row}"
            assert isinstance(row["text"], str)
            assert len(row["text"]) > 0

    def test_small_fixture_has_varied_labels(self):
        path = FIXTURES_DIR / "small.jsonl"
        rows = [json.loads(line) for line in path.read_text().strip().split("\n")]
        labels = {row["label"] for row in rows}
        assert len(labels) >= 2, "Small fixture should have varied labels"

    def test_medium_fixture_has_1000_rows(self):
        path = FIXTURES_DIR / "medium.jsonl"
        assert path.exists(), "medium.jsonl not found"
        lines = [l for l in path.read_text().strip().split("\n") if l]
        assert len(lines) == 1000
        # Spot-check first and last
        first = json.loads(lines[0])
        last = json.loads(lines[-1])
        assert "text" in first and "label" in first
        assert "text" in last and "label" in last

    def test_empty_fixture_is_empty(self):
        path = FIXTURES_DIR / "empty.jsonl"
        assert path.exists(), "empty.jsonl not found"
        content = path.read_text().strip()
        assert content == ""

    def test_malformed_fixture_has_bad_rows(self):
        path = FIXTURES_DIR / "malformed.jsonl"
        assert path.exists(), "malformed.jsonl not found"
        lines = path.read_text().strip().split("\n")
        assert len(lines) >= 10, "malformed.jsonl should have many edge cases"

        parse_errors = 0
        for line in lines:
            try:
                json.loads(line)
            except (json.JSONDecodeError, ValueError):
                parse_errors += 1
        assert parse_errors >= 2, "malformed.jsonl should have multiple unparseable rows"

    def test_malformed_fixture_has_missing_fields(self):
        path = FIXTURES_DIR / "malformed.jsonl"
        lines = path.read_text().strip().split("\n")
        missing_text = 0
        missing_label = 0
        for line in lines:
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    if "text" not in row:
                        missing_text += 1
                    if "label" not in row:
                        missing_label += 1
            except (json.JSONDecodeError, ValueError):
                continue
        assert missing_text > 0, "Should have rows with missing 'text'"
        assert missing_label > 0, "Should have rows with missing 'label'"


# ══════════════════════════════════════════════════════════════════════════════
# Block runner: input generation tests
# ══════════════════════════════════════════════════════════════════════════════


class TestInputGeneration:
    """Test that _generate_input_for_type produces valid mock data."""

    def setup_method(self):
        self.run_dir = tempfile.mkdtemp(prefix="test_input_gen_")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.run_dir, ignore_errors=True)

    def test_dataset_without_fixture(self):
        from backend.tests.block_runner import _generate_input_for_type

        result = _generate_input_for_type("dataset", "data", None, self.run_dir, {})
        assert os.path.isfile(result)
        with open(result) as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) > 0
        assert "text" in data[0]

    def test_dataset_with_fixture(self):
        from backend.tests.block_runner import _generate_input_for_type

        fixture = str(FIXTURES_DIR / "small.jsonl")
        result = _generate_input_for_type("dataset", "data", fixture, self.run_dir, {})
        assert os.path.isfile(result)
        with open(result) as f:
            data = json.load(f)
        assert len(data) == 10

    def test_text_input(self):
        from backend.tests.block_runner import _generate_input_for_type

        result = _generate_input_for_type("text", "prompt", None, self.run_dir, {})
        assert os.path.isfile(result)
        content = open(result).read()
        assert len(content) > 0

    def test_model_input_uses_config(self):
        from backend.tests.block_runner import _generate_input_for_type

        config = {"model_name": "meta-llama/Llama-3-8B"}
        result = _generate_input_for_type("model", "base_model", None, self.run_dir, config)
        assert isinstance(result, dict)
        assert result["model_name"] == "meta-llama/Llama-3-8B"

    def test_model_input_without_config(self):
        from backend.tests.block_runner import _generate_input_for_type

        result = _generate_input_for_type("model", "base_model", None, self.run_dir, {})
        assert isinstance(result, dict)
        assert "model_name" in result

    def test_config_input(self):
        from backend.tests.block_runner import _generate_input_for_type

        result = _generate_input_for_type("config", "settings", None, self.run_dir, {})
        assert isinstance(result, dict)

    def test_metrics_input(self):
        from backend.tests.block_runner import _generate_input_for_type

        result = _generate_input_for_type("metrics", "eval", None, self.run_dir, {})
        assert isinstance(result, dict)

    def test_embedding_input(self):
        from backend.tests.block_runner import _generate_input_for_type

        result = _generate_input_for_type("embedding", "vectors", None, self.run_dir, {})
        assert isinstance(result, list)
        assert len(result) > 0
        assert isinstance(result[0], list)

    def test_artifact_input(self):
        from backend.tests.block_runner import _generate_input_for_type

        result = _generate_input_for_type("artifact", "pkg", None, self.run_dir, {})
        assert os.path.isdir(result)

    def test_any_input(self):
        from backend.tests.block_runner import _generate_input_for_type

        result = _generate_input_for_type("any", "generic", None, self.run_dir, {})
        assert result is not None

    def test_unique_filenames_per_input(self):
        """Multiple dataset inputs should not overwrite each other."""
        from backend.tests.block_runner import _generate_input_for_type

        path_a = _generate_input_for_type("dataset", "train", None, self.run_dir, {})
        path_b = _generate_input_for_type("dataset", "eval", None, self.run_dir, {})
        assert path_a != path_b
        assert os.path.isfile(path_a)
        assert os.path.isfile(path_b)


# ══════════════════════════════════════════════════════════════════════════════
# Block runner: fixture loading tests
# ══════════════════════════════════════════════════════════════════════════════


class TestFixtureLoading:
    """Test fixture loading and custom fixture path support."""

    def test_load_small_fixture(self):
        from backend.tests.block_runner import _load_fixture

        path = _load_fixture("small")
        assert os.path.isfile(path)
        with open(path) as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) == 10

    def test_load_medium_fixture(self):
        from backend.tests.block_runner import _load_fixture

        path = _load_fixture("medium")
        assert os.path.isfile(path)

    def test_load_nonexistent_fixture_raises(self):
        from backend.tests.block_runner import _load_fixture

        with pytest.raises(FileNotFoundError, match="Fixture"):
            _load_fixture("nonexistent")

    def test_load_custom_fixture_path(self):
        from backend.tests.block_runner import _load_fixture_path

        path = _load_fixture_path(str(FIXTURES_DIR / "small.jsonl"))
        assert os.path.isfile(path)

    def test_load_custom_fixture_path_not_found(self):
        from backend.tests.block_runner import _load_fixture_path

        with pytest.raises(FileNotFoundError):
            _load_fixture_path("/nonexistent/path/data.jsonl")

    def test_realistic_fixture_auto_generated(self):
        """The realistic fixture should be auto-generated on first use."""
        from backend.tests.block_runner import _load_fixture

        path = _load_fixture("realistic")
        assert os.path.isfile(path)
        with open(path) as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) == 10000


# ══════════════════════════════════════════════════════════════════════════════
# Block runner: CLI coercion tests
# ══════════════════════════════════════════════════════════════════════════════


class TestCoercion:
    """Test CLI value coercion from strings to typed values."""

    def test_coerce_integer(self):
        from backend.tests.block_runner import _coerce_value

        assert _coerce_value("42", "integer") == 42

    def test_coerce_invalid_integer_passes_through(self):
        from backend.tests.block_runner import _coerce_value

        assert _coerce_value("abc", "integer") == "abc"

    def test_coerce_float(self):
        from backend.tests.block_runner import _coerce_value

        assert _coerce_value("0.001", "float") == 0.001

    def test_coerce_boolean_true(self):
        from backend.tests.block_runner import _coerce_value

        assert _coerce_value("true", "boolean") is True
        assert _coerce_value("True", "boolean") is True
        assert _coerce_value("1", "boolean") is True
        assert _coerce_value("yes", "boolean") is True

    def test_coerce_boolean_false(self):
        from backend.tests.block_runner import _coerce_value

        assert _coerce_value("false", "boolean") is False
        assert _coerce_value("no", "boolean") is False
        assert _coerce_value("0", "boolean") is False

    def test_coerce_string_passthrough(self):
        from backend.tests.block_runner import _coerce_value

        assert _coerce_value("hello", "string") == "hello"
        assert _coerce_value("hello", "text_area") == "hello"


# ══════════════════════════════════════════════════════════════════════════════
# Block runner: integration tests
# ══════════════════════════════════════════════════════════════════════════════


class TestBlockRunnerIntegration:
    """Integration tests running actual blocks through the test harness."""

    def test_text_input_happy_path(self):
        from backend.tests.block_runner import run_block_test

        exit_code = run_block_test(
            block_dir="blocks/data/text_input",
            config_overrides={"text_value": "Hello World"},
        )
        assert exit_code == 0

    def test_text_input_with_fixture(self):
        from backend.tests.block_runner import run_block_test

        exit_code = run_block_test(
            block_dir="blocks/data/text_input",
            fixture_name="small",
            config_overrides={"text_value": "test"},
        )
        assert exit_code == 0

    def test_text_input_verbose(self):
        from backend.tests.block_runner import run_block_test

        exit_code = run_block_test(
            block_dir="blocks/data/text_input",
            config_overrides={"text_value": "verbose test"},
            verbose=True,
        )
        assert exit_code == 0

    def test_ballast_validation_failure(self):
        """Out-of-bounds lr should fail validation."""
        from backend.tests.block_runner import run_block_test

        exit_code = run_block_test(
            block_dir="blocks/training/ballast_training",
            fixture_name="small",
            config_overrides={"model_name": "gpt2", "lr": "1.0"},
        )
        assert exit_code == 1

    def test_ballast_with_fixture_succeeds(self):
        """Ballast training in fallback mode should succeed."""
        from backend.tests.block_runner import run_block_test

        exit_code = run_block_test(
            block_dir="blocks/training/ballast_training",
            fixture_name="small",
            config_overrides={"model_name": "gpt2"},
        )
        assert exit_code == 0

    def test_nonexistent_block_returns_1(self):
        from backend.tests.block_runner import run_block_test

        exit_code = run_block_test(block_dir="blocks/does/not_exist")
        assert exit_code == 1

    def test_custom_fixture_path(self):
        from backend.tests.block_runner import run_block_test

        exit_code = run_block_test(
            block_dir="blocks/data/text_input",
            fixture_path_override=str(FIXTURES_DIR / "small.jsonl"),
            config_overrides={"text_value": "custom fixture test"},
        )
        assert exit_code == 0

    def test_custom_fixture_path_not_found(self):
        from backend.tests.block_runner import run_block_test

        exit_code = run_block_test(
            block_dir="blocks/data/text_input",
            fixture_path_override="/nonexistent/data.jsonl",
        )
        assert exit_code == 1

    def test_temp_directory_cleaned_up(self):
        """Run directory should be cleaned up after test completes."""
        import glob

        from backend.tests.block_runner import run_block_test

        # Count temp dirs before
        before = set(glob.glob(os.path.join(tempfile.gettempdir(), "block_test_*")))

        run_block_test(
            block_dir="blocks/data/text_input",
            config_overrides={"text_value": "cleanup test"},
        )

        after = set(glob.glob(os.path.join(tempfile.gettempdir(), "block_test_*")))
        # No new temp dirs should remain
        new_dirs = after - before
        assert len(new_dirs) == 0, f"Temp directories leaked: {new_dirs}"


# ══════════════════════════════════════════════════════════════════════════════
# Block runner: output formatting tests
# ══════════════════════════════════════════════════════════════════════════════


class TestOutputFormatting:
    """Test the box drawing output utilities."""

    def test_box_line_truncates_long_text(self):
        from backend.tests.block_runner import _box_line, BOX_WIDTH

        long_text = "A" * 200
        line = _box_line(long_text)
        # Format: "║ " (2) + content (BOX_WIDTH-2) + " ║" (2) = BOX_WIDTH + 2
        assert len(line) == BOX_WIDTH + 2
        # Content should be truncated, not overflow
        assert "A" * (BOX_WIDTH - 2) in line

    def test_box_line_pads_short_text(self):
        from backend.tests.block_runner import _box_line, BOX_WIDTH

        line = _box_line("Hi")
        assert line.startswith("\u2551 Hi")
        assert line.endswith(" \u2551")

    def test_format_bytes(self):
        from backend.tests.block_runner import _format_bytes

        assert _format_bytes(0) == "0 B"
        assert _format_bytes(512) == "512 B"
        assert _format_bytes(1024) == "1.0 KB"
        assert _format_bytes(1536) == "1.5 KB"
        assert _format_bytes(1048576) == "1.0 MB"
        assert _format_bytes(1572864) == "1.5 MB"
