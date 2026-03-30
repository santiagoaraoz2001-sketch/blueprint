"""Exhaustive tests for all 17 evaluation blocks.

Tier 1 (full execution): custom_eval, ab_comparator, ab_significance, latency_profiler
Tier 2/3 (validation only): lm_eval_harness, mmlu_eval, toxicity_eval, coherence_eval,
    factuality_checker, semantic_similarity, summarization_eval, bias_fairness_eval,
    model_diff, model_telemetry, rag_eval, custom_benchmark, human_eval
"""

from __future__ import annotations
import pytest

pytestmark = pytest.mark.slow

from .block_test_helpers import (
    node, edge, text_input_node, text_to_dataset_node, metrics_input_node,
    create_pipeline, validate, validate_config,
    create_and_run, assert_run_complete,
)


# ═══════════════════════════════════════════════════════════════════════
#  CUSTOM_EVAL
# ═══════════════════════════════════════════════════════════════════════

class TestCustomEval:
    def test_default_scoring(self, live_backend):
        nodes = [
            text_input_node("ti", "prediction1\nprediction2\nprediction3"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("ce", "custom_eval"),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "ce", "dataset", "predictions")]
        pid, run = create_and_run("eval:ce:default", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_custom_scoring_function(self, live_backend):
        nodes = [
            text_input_node("ti", "hello\nworld\ntest"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("ce", "custom_eval", {"scoring_function": "def score(output, reference=None, idx=0):\n    return {'score': len(str(output)) / 10.0}"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "ce", "dataset", "predictions")]
        pid, run = create_and_run("eval:ce:custom", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_with_reference(self, live_backend):
        nodes = [
            text_input_node("pred", "hello\nworld"),
            text_to_dataset_node("pd", split_by="newline"),
            text_input_node("ref", "hello\nearth"),
            text_to_dataset_node("rd", split_by="newline"),
            node("ce", "custom_eval"),
        ]
        edges = [
            edge("pred", "pd", "text", "text"), edge("ref", "rd", "text", "text"),
            edge("pd", "ce", "dataset", "predictions"), edge("rd", "ce", "dataset", "reference"),
        ]
        pid, run = create_and_run("eval:ce:ref", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_fail_fast(self, live_backend):
        nodes = [
            text_input_node("ti", "test"),
            text_to_dataset_node("ttd"),
            node("ce", "custom_eval", {"error_handling": "fail_fast"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "ce", "dataset", "predictions")]
        pid, run = create_and_run("eval:ce:failfast", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_aggregation_median(self, live_backend):
        nodes = [
            text_input_node("ti", "short\nmedium length text\nthis is a much longer sentence with many words"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("ce", "custom_eval", {
                "scoring_function": "def score(output, reference=None, idx=0):\n    return {'score': len(str(output))}",
                "aggregate": "median",
            }),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "ce", "dataset", "predictions")]
        pid, run = create_and_run("eval:ce:median", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  AB_SIGNIFICANCE
# ═══════════════════════════════════════════════════════════════════════

class TestABSignificance:
    def test_ttest(self, live_backend):
        nodes = [
            metrics_input_node("a", '{"accuracy": [0.8, 0.85, 0.82, 0.9, 0.87]}'),
            metrics_input_node("b", '{"accuracy": [0.7, 0.75, 0.72, 0.78, 0.76]}'),
            node("sig", "ab_significance", {"test_type": "welch_t"}),
        ]
        edges = [edge("a", "sig", "metrics", "metrics_a"), edge("b", "sig", "metrics", "metrics_b")]
        pid, run = create_and_run("eval:sig:ttest", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_bootstrap(self, live_backend):
        nodes = [
            metrics_input_node("a", '{"accuracy": [0.8, 0.85, 0.82, 0.9, 0.87]}'),
            metrics_input_node("b", '{"accuracy": [0.7, 0.75, 0.72, 0.78, 0.76]}'),
            node("sig", "ab_significance", {"test_type": "bootstrap", "n_bootstrap": 100}),
        ]
        edges = [edge("a", "sig", "metrics", "metrics_a"), edge("b", "sig", "metrics", "metrics_b")]
        pid, run = create_and_run("eval:sig:bootstrap", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_mann_whitney(self, live_backend):
        nodes = [
            metrics_input_node("a", '{"accuracy": [0.8, 0.85, 0.82, 0.9, 0.87]}'),
            metrics_input_node("b", '{"accuracy": [0.7, 0.75, 0.72, 0.78, 0.76]}'),
            node("sig", "ab_significance", {"test_type": "mann_whitney"}),
        ]
        edges = [edge("a", "sig", "metrics", "metrics_a"), edge("b", "sig", "metrics", "metrics_b")]
        pid, run = create_and_run("eval:sig:mw", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  AB_COMPARATOR
# ═══════════════════════════════════════════════════════════════════════

class TestABComparator:
    def test_heuristic(self, live_backend):
        nodes = [
            text_input_node("ti", "Question: What is AI?"),
            text_to_dataset_node("ttd"),
            node("abc", "ab_comparator", {"method": "heuristic"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "abc", "dataset", "dataset")]
        pid, run = create_and_run("eval:abc:heur", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_precomputed(self, live_backend):
        nodes = [
            text_input_node("ti", "test query"),
            text_to_dataset_node("ttd"),
            node("abc", "ab_comparator", {"method": "precomputed"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "abc", "dataset", "dataset")]
        pid, run = create_and_run("eval:abc:pre", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  LATENCY_PROFILER
# ═══════════════════════════════════════════════════════════════════════

class TestLatencyProfiler:
    def test_validate_config(self, live_backend):
        s, d = validate_config("latency_profiler", {"num_runs": 5, "warmup_runs": 1})
        assert s == 200

    def test_validate_pipeline(self, live_backend):
        nodes = [
            text_input_node("ti", "test"),
            node("lp", "latency_profiler", {"num_runs": 3}),
        ]
        edges = [edge("ti", "lp", "text", "input")]
        pid = create_pipeline("eval:lp:val", nodes, edges)
        val = validate(pid)
        assert val["block_count"] == 2


# ═══════════════════════════════════════════════════════════════════════
#  VALIDATION-ONLY EVALUATION BLOCKS
# ═══════════════════════════════════════════════════════════════════════

class TestEvalValidation:
    def test_lm_eval_harness_config(self, live_backend):
        s, d = validate_config("lm_eval_harness", {"model_name": "meta-llama/Llama-3.2-1B", "tasks": "hellaswag"})
        assert s == 200

    def test_mmlu_eval_config(self, live_backend):
        s, d = validate_config("mmlu_eval", {"model_name": "test-model", "subjects": "all"})
        assert s == 200

    def test_toxicity_eval_config(self, live_backend):
        s, d = validate_config("toxicity_eval", {"threshold": 0.5})
        assert s == 200

    def test_coherence_eval_config(self, live_backend):
        s, d = validate_config("coherence_eval", {"metric": "perplexity"})
        assert s == 200

    def test_factuality_checker_config(self, live_backend):
        s, d = validate_config("factuality_checker", {"method": "nli"})
        assert s == 200

    def test_semantic_similarity_config(self, live_backend):
        s, d = validate_config("semantic_similarity", {"model_name": "all-MiniLM-L6-v2"})
        assert s == 200

    def test_summarization_eval_config(self, live_backend):
        s, d = validate_config("summarization_eval", {"metrics": "rouge"})
        assert s == 200

    def test_bias_fairness_config(self, live_backend):
        s, d = validate_config("bias_fairness_eval", {"protected_attribute": "gender"})
        assert s == 200

    def test_model_diff_config(self, live_backend):
        s, d = validate_config("model_diff", {"comparison_type": "output"})
        assert s == 200

    def test_model_telemetry_config(self, live_backend):
        s, d = validate_config("model_telemetry", {"collect_memory": True})
        assert s == 200

    def test_rag_eval_config(self, live_backend):
        s, d = validate_config("rag_eval", {"metrics": "relevance,faithfulness"})
        assert s == 200

    def test_custom_benchmark_config(self, live_backend):
        s, d = validate_config("custom_benchmark", {"benchmark_name": "test"})
        assert s == 200

    def test_human_eval_config(self, live_backend):
        s, d = validate_config("human_eval", {"num_samples": 10})
        assert s == 200


# ═══════════════════════════════════════════════════════════════════════
#  EVALUATION E2E WORKFLOWS
# ═══════════════════════════════════════════════════════════════════════

class TestEvalWorkflows:
    def test_dataset_to_custom_eval(self, live_backend):
        """ti → ttd → custom_eval"""
        nodes = [
            text_input_node("ti", "pred1\npred2\npred3"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("ce", "custom_eval", {"scoring_function": "def score(output, reference=None, idx=0):\n    return {'score': 1.0 if len(str(output)) > 3 else 0.0}"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "ce", "dataset", "predictions")]
        pid, run = create_and_run("wf:eval:ttd-ce", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_dual_metrics_significance(self, live_backend):
        """mi_a + mi_b → ab_significance"""
        nodes = [
            metrics_input_node("a", '{"accuracy": [0.9, 0.88, 0.92, 0.85, 0.91]}'),
            metrics_input_node("b", '{"accuracy": [0.6, 0.65, 0.62, 0.58, 0.63]}'),
            node("sig", "ab_significance", {"test_type": "welch_t"}),
        ]
        edges = [edge("a", "sig", "metrics", "metrics_a"), edge("b", "sig", "metrics", "metrics_b")]
        pid, run = create_and_run("wf:eval:dual-sig", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)
