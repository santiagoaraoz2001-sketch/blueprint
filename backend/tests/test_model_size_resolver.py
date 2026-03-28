"""Tests for the comprehensive model-size resolver (Risk 2 fix)."""

import json
import os
import tempfile

import pytest

from backend.engine.dry_run import (
    _guess_model_size_b,
    _from_explicit_config,
    _from_model_family_registry,
    _from_regex_pattern,
    _from_local_config_json,
    _compute_params_from_architecture,
    _extract_model_name,
)


# ---------------------------------------------------------------------------
# Strategy 1: Explicit config fields
# ---------------------------------------------------------------------------

class TestExplicitConfig:
    def test_model_size_b_field(self):
        assert _from_explicit_config({"model_size_b": 7.0}) == 7.0

    def test_model_size_b_string(self):
        assert _from_explicit_config({"model_size_b": "13.0"}) == 13.0

    def test_total_params_field(self):
        assert _from_explicit_config({"total_params": 7_000_000_000}) == 7.0

    def test_num_parameters_field(self):
        assert _from_explicit_config({"num_parameters": 3_800_000_000}) == 3.8

    def test_no_explicit_fields(self):
        assert _from_explicit_config({"batch_size": 4}) is None


# ---------------------------------------------------------------------------
# Strategy 2: Local config.json
# ---------------------------------------------------------------------------

class TestLocalConfigJson:
    def test_reads_llama_config(self):
        """Reads a HuggingFace config.json and computes parameter count."""
        # Llama 7B architecture config
        config = {
            "model_type": "llama",
            "hidden_size": 4096,
            "intermediate_size": 11008,
            "num_hidden_layers": 32,
            "num_attention_heads": 32,
            "num_key_value_heads": 32,
            "vocab_size": 32000,
            "tie_word_embeddings": False,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.json")
            with open(config_path, "w") as f:
                json.dump(config, f)

            result = _from_local_config_json("irrelevant", {"model_path": tmpdir})

        # Llama 7B has ~6.7B parameters
        assert result is not None
        assert 6.0 < result < 8.0

    def test_reads_num_parameters_directly(self):
        """If config.json has num_parameters, use it directly."""
        config = {"num_parameters": 3_800_000_000}

        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "config.json"), "w") as f:
                json.dump(config, f)

            result = _from_local_config_json("irrelevant", {"model_path": tmpdir})

        assert result == 3.8

    def test_nonexistent_path(self):
        """Non-existent path returns None."""
        result = _from_local_config_json("model", {"model_path": "/nonexistent/path"})
        assert result is None

    def test_no_local_path(self):
        """HuggingFace model ID without local path returns None (unless cached)."""
        result = _from_local_config_json(
            "meta-llama/Llama-3.1-7B",
            {"model_name": "meta-llama/Llama-3.1-7B"},
        )
        # May be None or a value if model is cached locally — either is fine
        # The key is that it doesn't crash
        assert result is None or isinstance(result, float)


# ---------------------------------------------------------------------------
# Strategy 3: Model family registry
# ---------------------------------------------------------------------------

class TestModelFamilyRegistry:
    def test_gpt2_variants(self):
        assert _from_model_family_registry("gpt2") == 0.124
        assert _from_model_family_registry("gpt2-medium") == 0.355
        assert _from_model_family_registry("gpt2-large") == 0.774
        assert _from_model_family_registry("gpt2-xl") == 1.5

    def test_phi_family(self):
        assert _from_model_family_registry("microsoft/phi-3-mini-4k-instruct") == 3.8
        assert _from_model_family_registry("microsoft/phi-3-medium-128k") == 14.0
        assert _from_model_family_registry("microsoft/phi-2") == 2.7

    def test_gemma_family(self):
        assert _from_model_family_registry("google/gemma-2-9b-it") == 9.0
        assert _from_model_family_registry("google/gemma-2-27b") == 27.0
        assert _from_model_family_registry("google/gemma-2-2b") == 2.6

    def test_qwen_family(self):
        assert _from_model_family_registry("Qwen/Qwen2.5-72B-Instruct") == 72.0
        assert _from_model_family_registry("Qwen/Qwen2.5-7B") == 7.0
        assert _from_model_family_registry("Qwen/Qwen2.5-0.5B") == 0.5
        assert _from_model_family_registry("Qwen/Qwen2.5-Coder-32B-Instruct") == 32.0

    def test_mistral_mixtral(self):
        assert _from_model_family_registry("mistralai/Mixtral-8x7B-v0.1") == 46.7
        assert _from_model_family_registry("mistralai/Mixtral-8x22B") == 141.0
        assert _from_model_family_registry("mistralai/Mistral-Nemo-Instruct") == 12.0

    def test_deepseek(self):
        assert _from_model_family_registry("deepseek-ai/DeepSeek-Coder-33B") == 33.0
        assert _from_model_family_registry("deepseek-ai/DeepSeek-V3") == 685.0

    def test_sentence_transformers(self):
        assert _from_model_family_registry("sentence-transformers/all-MiniLM-L6-v2") == 0.023
        assert _from_model_family_registry("cross-encoder/ms-marco-MiniLM-L-6-v2") == 0.023

    def test_bert(self):
        assert _from_model_family_registry("bert-base-uncased") == 0.110
        assert _from_model_family_registry("bert-large-uncased") == 0.340

    def test_unknown_model(self):
        assert _from_model_family_registry("completely-unknown-model") is None


# ---------------------------------------------------------------------------
# Strategy 4: Regex pattern extraction
# ---------------------------------------------------------------------------

class TestRegexPattern:
    def test_standard_b_suffix(self):
        """Standard 'XB' patterns."""
        assert _from_regex_pattern("meta-llama/Llama-3.1-7B") == 7.0
        assert _from_regex_pattern("meta-llama/Llama-3.1-70B-Instruct") == 70.0
        assert _from_regex_pattern("meta-llama/Llama-3.2-3B") == 3.0

    def test_decimal_b_suffix(self):
        """Decimal sizes like '3.2B', '1.5b'."""
        assert _from_regex_pattern("model-3.2B") == 3.2
        assert _from_regex_pattern("model-1.5b-instruct") == 1.5
        assert _from_regex_pattern("model-0.5B") == 0.5

    def test_m_suffix(self):
        """Million-parameter models: '500M', '125m'."""
        result = _from_regex_pattern("gpt2-125m-custom")
        assert result is not None
        assert abs(result - 0.125) < 0.001

        result = _from_regex_pattern("bloom-560M")
        assert result is not None
        assert abs(result - 0.56) < 0.001

    def test_moe_pattern(self):
        """Mixture of Experts: '8x7B'."""
        result = _from_regex_pattern("Mixtral-8x7B-v0.1")
        assert result is not None
        assert abs(result - 56.0) < 0.1  # 8 * 7

        result = _from_regex_pattern("model-8x22B")
        assert result is not None
        assert abs(result - 176.0) < 0.1  # 8 * 22

    def test_lowercase(self):
        assert _from_regex_pattern("my-model-7b-chat") == 7.0

    def test_no_match(self):
        assert _from_regex_pattern("some-model-without-size") is None

    def test_version_not_confused_with_size(self):
        """Version numbers like 'v2' should NOT be parsed as sizes."""
        result = _from_regex_pattern("model-v2")
        # 'v2' doesn't match because 'v' is alphanumeric before the number
        assert result is None

    def test_picks_largest_match(self):
        """When multiple size patterns exist, pick the largest."""
        result = _from_regex_pattern("model-7B-lora-rank-16M")
        # 7B = 7.0, 16M = 0.016 → picks 7.0
        assert result == 7.0


# ---------------------------------------------------------------------------
# Full resolver: _guess_model_size_b
# ---------------------------------------------------------------------------

class TestFullResolver:
    def test_explicit_takes_priority(self):
        """Explicit model_size_b overrides everything."""
        size = _guess_model_size_b({
            "model_size_b": 13.0,
            "model_name": "gpt2",  # Would resolve to 0.124 via registry
        })
        assert size == 13.0

    def test_registry_for_gpt2(self):
        """GPT-2 doesn't follow the XB pattern — resolved via family registry."""
        size = _guess_model_size_b({"model_name": "gpt2"})
        assert size == 0.124

    def test_regex_for_llama(self):
        """Standard Llama model resolved via regex."""
        size = _guess_model_size_b({"model_name": "meta-llama/Llama-3.1-70B-Instruct"})
        assert size == 70.0

    def test_phi_from_registry(self):
        """Phi models without B suffix resolved via registry."""
        size = _guess_model_size_b({"model_name": "microsoft/phi-3-mini-4k-instruct"})
        assert size == 3.8

    def test_config_json_with_tempdir(self):
        """Local model path with config.json is used."""
        config = {
            "model_type": "llama",
            "hidden_size": 2048,
            "intermediate_size": 5632,
            "num_hidden_layers": 16,
            "num_attention_heads": 16,
            "num_key_value_heads": 16,
            "vocab_size": 32000,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "config.json"), "w") as f:
                json.dump(config, f)

            size = _guess_model_size_b({"model_path": tmpdir})

        assert size is not None
        assert 0.1 < size < 5.0  # small model

    def test_unknown_model_returns_none(self):
        """Completely unknown model with no signals returns None."""
        size = _guess_model_size_b({"model_name": "my-private-model"})
        assert size is None

    def test_total_params_from_previous_run(self):
        """total_params from block metrics enables exact resolution."""
        size = _guess_model_size_b({"total_params": 8_030_261_248})
        assert abs(size - 8.03) < 0.01

    def test_extract_model_name_priority(self):
        """model_name is preferred over model_path for name extraction."""
        name = _extract_model_name({
            "model_name": "meta-llama/Llama-3.1-7B",
            "model_path": "/some/path",
        })
        assert name == "meta-llama/Llama-3.1-7B"


# ---------------------------------------------------------------------------
# Architecture parameter computation
# ---------------------------------------------------------------------------

class TestArchitectureComputation:
    def test_llama_7b(self):
        """Llama 7B config should produce ~6.7B params."""
        config = {
            "model_type": "llama",
            "hidden_size": 4096,
            "intermediate_size": 11008,
            "num_hidden_layers": 32,
            "num_attention_heads": 32,
            "num_key_value_heads": 32,
            "vocab_size": 32000,
            "tie_word_embeddings": False,
        }
        result = _compute_params_from_architecture(config)
        assert result is not None
        assert 6.0 < result < 8.0

    def test_llama_70b_gqa(self):
        """Llama 70B with GQA (fewer KV heads) should produce ~70B params."""
        config = {
            "model_type": "llama",
            "hidden_size": 8192,
            "intermediate_size": 28672,
            "num_hidden_layers": 80,
            "num_attention_heads": 64,
            "num_key_value_heads": 8,  # GQA
            "vocab_size": 32000,
            "tie_word_embeddings": False,
        }
        result = _compute_params_from_architecture(config)
        assert result is not None
        assert 60.0 < result < 80.0

    def test_gpt2_style(self):
        """GPT-2 style (non-gated MLP) should produce ~0.124B."""
        config = {
            "model_type": "gpt2",
            "hidden_size": 768,
            "n_inner": 3072,
            "n_layer": 12,
            "num_attention_heads": 12,
            "vocab_size": 50257,
            "tie_word_embeddings": True,
        }
        result = _compute_params_from_architecture(config)
        assert result is not None
        assert 0.1 < result < 0.2

    def test_missing_fields_returns_none(self):
        """Incomplete config returns None."""
        assert _compute_params_from_architecture({}) is None
        assert _compute_params_from_architecture({"hidden_size": 4096}) is None

    def test_qwen2_gated(self):
        """Qwen2 uses gated MLP — should be in gated_types."""
        config = {
            "model_type": "qwen2",
            "hidden_size": 3584,
            "intermediate_size": 18944,
            "num_hidden_layers": 28,
            "num_attention_heads": 28,
            "num_key_value_heads": 4,
            "vocab_size": 152064,
            "tie_word_embeddings": False,
        }
        result = _compute_params_from_architecture(config)
        assert result is not None
        assert 5.0 < result < 10.0  # ~7B
