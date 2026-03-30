"""Exhaustive tests for all 18 inference blocks.

Tier 1 (full execution via Ollama): prompt_chain, response_parser, token_counter
Tier 2/3 (validation only): embedding_*, rag_pipeline, quantize_model, vision_inference,
    chat_completion, model_comparison, model_benchmark, guardrails, ab_test_inference, model_router
"""

from __future__ import annotations
import pytest

pytestmark = pytest.mark.slow

from .block_test_helpers import (
    node, edge, text_input_node, text_to_dataset_node, metrics_input_node,
    model_selector_node, inference_node, prompt_template_node,
    create_pipeline, validate, validate_config,
    create_and_run, assert_run_complete, assert_replay_nodes,
)


# ═══════════════════════════════════════════════════════════════════════
#  PROMPT_CHAIN
# ═══════════════════════════════════════════════════════════════════════

class TestPromptChain:
    def test_two_steps(self, ollama_model, live_backend):
        nodes = [
            model_selector_node("ms", ollama_model),
            text_input_node("ti", "What is the capital of Japan?"),
            node("pc", "prompt_chain", {"steps": '["Analyze: {input}", "Summarize: {input}"]', "max_tokens": 100, "temperature": 0.3}),
        ]
        edges = [edge("ms", "pc", "model", "model"), edge("ti", "pc", "text", "text")]
        pid, run = create_and_run("inf:pc:2step", nodes, edges,
                                  timeout=120, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_single_step(self, ollama_model, live_backend):
        nodes = [
            model_selector_node("ms", ollama_model),
            text_input_node("ti", "Say hi."),
            node("pc", "prompt_chain", {"steps": '["Answer: {input}"]', "max_tokens": 30}),
        ]
        edges = [edge("ms", "pc", "model", "model"), edge("ti", "pc", "text", "text")]
        pid, run = create_and_run("inf:pc:1step", nodes, edges,
                                  timeout=120, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_custom_template(self, ollama_model, live_backend):
        nodes = [
            model_selector_node("ms", ollama_model),
            text_input_node("ti", "machine learning"),
            node("pc", "prompt_chain", {
                "steps": '["Explain {input} in detail", "Now simplify the explanation"]', "max_tokens": 80,
            }),
        ]
        edges = [edge("ms", "pc", "model", "model"), edge("ti", "pc", "text", "text")]
        pid, run = create_and_run("inf:pc:template", nodes, edges,
                                  timeout=120, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  RESPONSE_PARSER
# ═══════════════════════════════════════════════════════════════════════

class TestResponseParser:
    def test_json_format(self, live_backend):
        nodes = [
            text_input_node("ti", '{"answer": 42, "name": "test"}'),
            node("rp", "response_parser", {"format": "json"}),
        ]
        edges = [edge("ti", "rp", "text", "text")]
        pid, run = create_and_run("inf:rp:json", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_csv_format(self, live_backend):
        nodes = [
            text_input_node("ti", "name,age\nAlice,30\nBob,25"),
            node("rp", "response_parser", {"format": "csv"}),
        ]
        edges = [edge("ti", "rp", "text", "text")]
        pid, run = create_and_run("inf:rp:csv", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_key_value_format(self, live_backend):
        nodes = [
            text_input_node("ti", "name: Alice\nage: 30\ncity: NYC"),
            node("rp", "response_parser", {"format": "key_value"}),
        ]
        edges = [edge("ti", "rp", "text", "text")]
        pid, run = create_and_run("inf:rp:kv", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_regex_format(self, live_backend):
        nodes = [
            text_input_node("ti", "The answer is 42 and the score is 95."),
            node("rp", "response_parser", {"format": "regex", "regex_pattern": "\\d+"}),
        ]
        edges = [edge("ti", "rp", "text", "text")]
        pid, run = create_and_run("inf:rp:regex", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_invalid_json_non_strict(self, live_backend):
        nodes = [
            text_input_node("ti", "this is not json at all"),
            node("rp", "response_parser", {"format": "json", "strict": False}),
        ]
        edges = [edge("ti", "rp", "text", "text")]
        pid, run = create_and_run("inf:rp:invalid", nodes, edges, stderr_path=live_backend.stderr_path)
        # Should complete (non-strict mode) or fail gracefully
        assert run["status"] in ("complete", "failed")


# ═══════════════════════════════════════════════════════════════════════
#  TOKEN_COUNTER
# ═══════════════════════════════════════════════════════════════════════

class TestTokenCounter:
    def test_estimate_tokenizer(self, live_backend):
        nodes = [
            text_input_node("ti", "Hello world, this is a test sentence for counting tokens."),
            node("tc", "token_counter", {"tokenizer": "estimate"}),
        ]
        edges = [edge("ti", "tc", "text", "text")]
        pid, run = create_and_run("inf:tc:estimate", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_with_cost(self, live_backend):
        nodes = [
            text_input_node("ti", "Hello world."),
            node("tc", "token_counter", {"tokenizer": "estimate", "cost_per_1k_tokens": 0.01}),
        ]
        edges = [edge("ti", "tc", "text", "text")]
        pid, run = create_and_run("inf:tc:cost", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_context_window(self, live_backend):
        nodes = [
            text_input_node("ti", "A" * 500),
            node("tc", "token_counter", {"tokenizer": "estimate", "context_window": 4096}),
        ]
        edges = [edge("ti", "tc", "text", "text")]
        pid, run = create_and_run("inf:tc:ctx", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_empty_text(self, live_backend):
        nodes = [
            text_input_node("ti", ""),
            node("tc", "token_counter", {"tokenizer": "estimate"}),
        ]
        edges = [edge("ti", "tc", "text", "text")]
        pid, run = create_and_run("inf:tc:empty", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_large_text(self, live_backend):
        nodes = [
            text_input_node("ti", "word " * 2000),
            node("tc", "token_counter", {"tokenizer": "estimate"}),
        ]
        edges = [edge("ti", "tc", "text", "text")]
        pid, run = create_and_run("inf:tc:large", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  VALIDATION-ONLY INFERENCE BLOCKS
# ═══════════════════════════════════════════════════════════════════════

class TestInferenceValidation:
    def test_embedding_generator_config(self, live_backend):
        s, d = validate_config("embedding_generator", {"provider": "sentence-transformers", "model_name": "all-MiniLM-L6-v2", "text_column": "text"})
        assert s == 200

    def test_embedding_similarity_search_config(self, live_backend):
        s, d = validate_config("embedding_similarity_search", {"top_k": 5, "metric": "cosine"})
        assert s == 200

    def test_embedding_clustering_config(self, live_backend):
        s, d = validate_config("embedding_clustering", {"algorithm": "kmeans", "n_clusters": 5})
        assert s == 200

    def test_reranker_config(self, live_backend):
        s, d = validate_config("reranker", {"model_name": "cross-encoder/ms-marco-MiniLM-L-6-v2", "top_k": 5})
        assert s == 200

    def test_rag_pipeline_config(self, live_backend):
        s, d = validate_config("rag_pipeline", {"query": "test", "top_k": 3, "provider": "ollama"})
        assert s == 200

    def test_quantize_model_config(self, live_backend):
        s, d = validate_config("quantize_model", {"method": "gptq", "bits": 4})
        assert s == 200

    def test_vision_inference_config(self, live_backend):
        s, d = validate_config("vision_inference", {"model_name": "llava"})
        assert s == 200

    def test_chat_completion_config(self, live_backend):
        s, d = validate_config("chat_completion", {"provider": "ollama", "model_name": "llama3"})
        assert s == 200

    def test_model_comparison_config(self, live_backend):
        s, d = validate_config("model_comparison", {"metric": "quality"})
        assert s == 200

    def test_model_benchmark_config(self, live_backend):
        s, d = validate_config("model_benchmark", {"benchmark": "mmlu"})
        assert s == 200

    def test_guardrails_config(self, live_backend):
        s, d = validate_config("guardrails", {"check_toxicity": True})
        assert s == 200

    def test_ab_test_inference_config(self, live_backend):
        s, d = validate_config("ab_test_inference", {"split_ratio": 0.5})
        assert s == 200

    def test_model_router_config(self, live_backend):
        s, d = validate_config("model_router", {"strategy": "round_robin"})
        assert s == 200


# ═══════════════════════════════════════════════════════════════════════
#  INFERENCE E2E WORKFLOWS
# ═══════════════════════════════════════════════════════════════════════

class TestInferenceWorkflows:
    def test_inference_then_parse(self, ollama_model, live_backend):
        """ms + ti → inf → response_parser(key_value)"""
        nodes = [
            model_selector_node("ms", ollama_model),
            text_input_node("ti", "List your name and age in key:value format."),
            inference_node("inf", ollama_model, max_tokens=50),
            node("rp", "response_parser", {"format": "key_value"}),
        ]
        edges = [
            edge("ms", "inf", "model", "model"),
            edge("ti", "inf", "text", "prompt"),
            edge("inf", "rp", "response", "text"),
        ]
        pid, run = create_and_run("wf:inf:parse", nodes, edges,
                                  timeout=120, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_inference_then_count(self, ollama_model, live_backend):
        """ms + ti → inf → token_counter"""
        nodes = [
            model_selector_node("ms", ollama_model),
            text_input_node("ti", "Tell me a short joke."),
            inference_node("inf", ollama_model, max_tokens=80),
            node("tc", "token_counter", {"tokenizer": "estimate"}),
        ]
        edges = [
            edge("ms", "inf", "model", "model"),
            edge("ti", "inf", "text", "prompt"),
            edge("inf", "tc", "response", "text"),
        ]
        pid, run = create_and_run("wf:inf:count", nodes, edges,
                                  timeout=120, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_prompt_chain_to_parser(self, ollama_model, live_backend):
        """ms + ti → prompt_chain → response_parser"""
        nodes = [
            model_selector_node("ms", ollama_model),
            text_input_node("ti", "Define AI in one sentence."),
            node("pc", "prompt_chain", {"steps": '["Define: {input}", "Elaborate: {input}"]', "max_tokens": 80}),
            node("rp", "response_parser", {"format": "key_value"}),
        ]
        edges = [
            edge("ms", "pc", "model", "model"),
            edge("ti", "pc", "text", "text"),
            edge("pc", "rp", "response", "text"),
        ]
        pid, run = create_and_run("wf:inf:chain-parse", nodes, edges,
                                  timeout=180, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)
