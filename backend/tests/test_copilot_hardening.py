"""Tests for copilot hardening: model catalog, AI output validation, schema enforcement."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.model_catalog import ModelCatalog, ModelInfo
from backend.services.copilot_ai import (
    AICopilot,
    _extract_json_object,
    _validate_variant_suggestions,
    _validate_field_value,
)


# ═══════════════════════════════════════════════════════════════════
#  Risk 1: Model Catalog Tests
# ═══════════════════════════════════════════════════════════════════

class TestModelCatalog:
    @pytest.fixture
    def catalog(self) -> ModelCatalog:
        return ModelCatalog()

    def test_exact_model_name(self, catalog: ModelCatalog):
        """Resolves a well-known model by exact name."""
        info = catalog.lookup("llama-7b")
        assert info is not None
        assert info.params_b == 7.0
        assert info.context == 2048
        assert info.source == "catalog"

    def test_huggingface_style_name(self, catalog: ModelCatalog):
        """Resolves a HuggingFace-style model path like 'meta-llama/Llama-3.1-8B-Instruct'."""
        info = catalog.lookup("meta-llama/Llama-3.1-8B-Instruct")
        assert info is not None
        assert info.params_b == 8.0
        assert info.context == 131072
        assert info.source == "catalog"

    def test_case_insensitive(self, catalog: ModelCatalog):
        """Model lookup is case-insensitive."""
        info = catalog.lookup("MISTRAL-7B")
        assert info is not None
        assert info.params_b == 7.3

    def test_qwen_with_dots(self, catalog: ModelCatalog):
        """Resolves Qwen models with dots in version."""
        info = catalog.lookup("Qwen/Qwen2.5-72B-Instruct")
        assert info is not None
        assert info.params_b == 72.0
        assert info.context == 131072

    def test_heuristic_extraction_billions(self, catalog: ModelCatalog):
        """Falls back to heuristic extraction for unknown '14b' model."""
        info = catalog.lookup("some-custom-model-14b-v2")
        assert info is not None
        assert info.params_b == 14.0
        assert info.source == "heuristic"

    def test_heuristic_extraction_millions(self, catalog: ModelCatalog):
        """Falls back to heuristic extraction for '350m' model."""
        info = catalog.lookup("my-org/custom-350m-chat")
        assert info is not None
        assert abs(info.params_b - 0.35) < 0.01
        assert info.source == "heuristic"

    def test_unknown_model_returns_none(self, catalog: ModelCatalog):
        """Returns None for a completely unknown model with no size indicator."""
        info = catalog.lookup("my-secret-model")
        assert info is None

    def test_empty_string_returns_none(self, catalog: ModelCatalog):
        """Returns None for empty string."""
        assert catalog.lookup("") is None

    def test_lookup_from_config_explicit_params(self, catalog: ModelCatalog):
        """Explicit model_params_b in config takes priority."""
        info = catalog.lookup_from_config({
            "model_name": "unknown-model",
            "model_params_b": 42.0,
        })
        assert info is not None
        assert info.params_b == 42.0
        assert info.source == "config"

    def test_lookup_from_config_model_name(self, catalog: ModelCatalog):
        """Falls through to name lookup when no explicit params."""
        info = catalog.lookup_from_config({
            "model_name": "phi-3-mini",
        })
        assert info is not None
        assert info.params_b == 3.8
        assert info.context == 128000

    def test_lookup_from_config_base_model(self, catalog: ModelCatalog):
        """Looks up base_model key if model_name isn't present."""
        info = catalog.lookup_from_config({
            "base_model": "mistral-7b-instruct-v0.2",
        })
        assert info is not None
        assert info.params_b == 7.3

    def test_context_override_from_config(self, catalog: ModelCatalog):
        """Explicit context_length in config overrides catalog value."""
        info = catalog.lookup_from_config({
            "model_name": "gpt2",
            "context_length": 2048,
        })
        assert info is not None
        assert info.params_b == 0.117
        assert info.context == 2048  # overridden from 1024

    def test_get_context_explicit(self, catalog: ModelCatalog):
        """get_context_from_config returns explicit config value first."""
        ctx = catalog.get_context_from_config({
            "model_max_length": 4096,
            "model_name": "gpt2",  # catalog says 1024
        })
        assert ctx == 4096

    def test_specific_before_generic(self, catalog: ModelCatalog):
        """Specific patterns like llama-3.1-8b match before generic llama-8b."""
        info = catalog.lookup("llama-3.1-8b-instruct")
        assert info is not None
        assert info.context == 131072  # llama-3.1 context, not llama-1 (2048)

    def test_deepseek_v3(self, catalog: ModelCatalog):
        """Resolves DeepSeek-V3 (671B)."""
        info = catalog.lookup("deepseek-ai/DeepSeek-V3")
        assert info is not None
        assert info.params_b == 671.0


# ═══════════════════════════════════════════════════════════════════
#  Risk 2: AI Output Validation Tests
# ═══════════════════════════════════════════════════════════════════

class TestJsonExtraction:
    def test_plain_json(self):
        assert _extract_json_object('{"a": 1}') == {"a": 1}

    def test_markdown_code_block(self):
        text = '```json\n{"a": 1}\n```'
        assert _extract_json_object(text) == {"a": 1}

    def test_prose_with_embedded_json(self):
        text = 'Here is the result:\n{"a": 1}\nHope this helps!'
        assert _extract_json_object(text) == {"a": 1}

    def test_nested_json(self):
        text = '{"n1": {"lr": 0.001, "epochs": 10}}'
        result = _extract_json_object(text)
        assert result == {"n1": {"lr": 0.001, "epochs": 10}}

    def test_invalid_json_returns_none(self):
        assert _extract_json_object("not json at all") is None

    def test_empty_string(self):
        assert _extract_json_object("") is None

    def test_triple_backtick_without_language(self):
        text = '```\n{"key": "value"}\n```'
        assert _extract_json_object(text) == {"key": "value"}

    def test_brace_matching_finds_object_after_prose(self):
        text = 'I suggest these changes: {"n1": {"model": "llama-70b"}} Let me explain...'
        result = _extract_json_object(text)
        assert result == {"n1": {"model": "llama-70b"}}


class TestFieldValidation:
    def test_clamp_numeric_to_max(self):
        meta = {"type": "float", "options": [], "min": 0.0, "max": 1.0}
        assert _validate_field_value(1.5, meta) == 1.0

    def test_clamp_numeric_to_min(self):
        meta = {"type": "integer", "options": [], "min": 1, "max": 100}
        assert _validate_field_value(-5, meta) == 1

    def test_numeric_within_range(self):
        meta = {"type": "float", "options": [], "min": 0.0, "max": 1.0}
        assert _validate_field_value(0.5, meta) == 0.5

    def test_select_valid_option(self):
        meta = {"type": "select", "options": ["adam", "sgd", "adamw"], "min": None, "max": None}
        assert _validate_field_value("adam", meta) == "adam"

    def test_select_invalid_option_rejected(self):
        meta = {"type": "select", "options": ["adam", "sgd", "adamw"], "min": None, "max": None}
        assert _validate_field_value("invalid_optimizer", meta) is None

    def test_select_case_insensitive(self):
        meta = {"type": "select", "options": ["Adam", "SGD"], "min": None, "max": None}
        assert _validate_field_value("adam", meta) == "Adam"

    def test_boolean_true(self):
        meta = {"type": "boolean", "options": [], "min": None, "max": None}
        assert _validate_field_value("true", meta) is True

    def test_boolean_false(self):
        meta = {"type": "boolean", "options": [], "min": None, "max": None}
        assert _validate_field_value("false", meta) is False

    def test_string_passthrough(self):
        meta = {"type": "string", "options": [], "min": None, "max": None}
        assert _validate_field_value(42, meta) == "42"

    def test_integer_coercion_from_float(self):
        meta = {"type": "integer", "options": [], "min": None, "max": None}
        assert _validate_field_value(3.7, meta) == 3

    def test_invalid_numeric_string_rejected(self):
        meta = {"type": "float", "options": [], "min": None, "max": None}
        assert _validate_field_value("not-a-number", meta) is None


class TestVariantSuggestionValidation:
    def test_strips_unknown_node_ids(self):
        valid_ids = {"n1", "n2"}
        raw = {"n1": {"lr": 0.001}, "n99": {"lr": 0.01}}
        schema_map: dict = {}
        result = _validate_variant_suggestions(raw, valid_ids, schema_map)
        assert "n1" in result
        assert "n99" not in result

    def test_strips_unknown_fields_when_schema_available(self):
        valid_ids = {"n1"}
        schema_map = {
            "n1": {
                "learning_rate": {"type": "float", "options": [], "min": 0.0, "max": 1.0},
            }
        }
        raw = {"n1": {"learning_rate": 0.001, "nonexistent_field": "hello"}}
        result = _validate_variant_suggestions(raw, valid_ids, schema_map)
        assert "learning_rate" in result["n1"]
        assert "nonexistent_field" not in result["n1"]

    def test_clamps_out_of_range_values(self):
        valid_ids = {"n1"}
        schema_map = {
            "n1": {
                "epochs": {"type": "integer", "options": [], "min": 1, "max": 100},
            }
        }
        raw = {"n1": {"epochs": 500}}
        result = _validate_variant_suggestions(raw, valid_ids, schema_map)
        assert result["n1"]["epochs"] == 100

    def test_rejects_invalid_enum_value(self):
        valid_ids = {"n1"}
        schema_map = {
            "n1": {
                "optimizer": {"type": "select", "options": ["adam", "sgd"], "min": None, "max": None},
            }
        }
        raw = {"n1": {"optimizer": "invalid"}}
        result = _validate_variant_suggestions(raw, valid_ids, schema_map)
        # n1 should be empty or missing since the only field was rejected
        assert "n1" not in result or not result.get("n1")

    def test_partial_results_kept(self):
        """Valid fields are kept even when other fields in the same node are invalid."""
        valid_ids = {"n1"}
        schema_map = {
            "n1": {
                "lr": {"type": "float", "options": [], "min": 0.0, "max": 1.0},
                "optimizer": {"type": "select", "options": ["adam", "sgd"], "min": None, "max": None},
            }
        }
        raw = {"n1": {"lr": 0.001, "optimizer": "invalid_opt"}}
        result = _validate_variant_suggestions(raw, valid_ids, schema_map)
        assert result["n1"]["lr"] == 0.001
        assert "optimizer" not in result["n1"]

    def test_graceful_with_no_schema(self):
        """When no schema is available, all fields pass through (graceful degradation)."""
        valid_ids = {"n1"}
        schema_map: dict = {}  # no schema for n1
        raw = {"n1": {"anything": "goes", "lr": 0.001}}
        result = _validate_variant_suggestions(raw, valid_ids, schema_map)
        assert result["n1"]["anything"] == "goes"
        assert result["n1"]["lr"] == 0.001


class TestAICopilotRetry:
    @patch("backend.services.copilot_ai._try_ollama_generate")
    @patch("backend.services.copilot_ai._try_mlx_generate", return_value=None)
    def test_retry_on_bad_first_response(self, mock_mlx, mock_ollama):
        """Retries with corrective prompt when first response isn't valid JSON."""
        # First call: bad response. Second call: good response.
        mock_ollama.side_effect = [
            "I think you should change the learning rate to 0.001",
            '{"n1": {"learning_rate": 0.001}}',
        ]

        copilot = AICopilot()
        pipeline = {
            "nodes": [{"id": "n1", "data": {"type": "ft", "label": "FT", "config": {"learning_rate": 0.01}}}],
            "edges": [],
        }
        result = copilot.suggest_variant_config(pipeline, "lower learning rate")
        assert result is not None
        assert result["n1"]["learning_rate"] == 0.001
        assert mock_ollama.call_count == 2

    @patch("backend.services.copilot_ai._try_ollama_generate")
    @patch("backend.services.copilot_ai._try_mlx_generate", return_value=None)
    def test_returns_none_after_both_attempts_fail(self, mock_mlx, mock_ollama):
        """Returns None if both attempts produce invalid output."""
        mock_ollama.side_effect = [
            "Sorry, I can't help with that",
            "Still can't produce JSON",
        ]

        copilot = AICopilot()
        pipeline = {
            "nodes": [{"id": "n1", "data": {"type": "ft", "label": "FT", "config": {}}}],
            "edges": [],
        }
        result = copilot.suggest_variant_config(pipeline, "make it better")
        assert result is None
