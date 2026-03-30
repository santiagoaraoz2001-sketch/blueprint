"""Cross-category E2E workflow tests — complex multi-block pipelines."""

from __future__ import annotations
import pytest

pytestmark = pytest.mark.slow

from .block_test_helpers import (
    node, edge, text_input_node, text_to_dataset_node, metrics_input_node,
    model_selector_node, inference_node, prompt_template_node, cot_node,
    create_pipeline, validate, validate_config,
    create_and_run, replay, assert_run_complete, assert_replay_nodes,
)


class TestCrossCategoryWorkflows:

    def test_full_inference_pipeline(self, ollama_model, live_backend):
        """6-block: ms + ti → pt → inf → response_parser → token_counter → data_export"""
        nodes = [
            model_selector_node("ms", ollama_model),
            text_input_node("ti", "artificial intelligence"),
            prompt_template_node("pt", "Define {input} in one sentence."),
            inference_node("inf", ollama_model, max_tokens=80),
            node("rp", "response_parser", {"format": "key_value"}),
            node("tc", "token_counter", {"tokenizer": "estimate"}),
        ]
        edges = [
            edge("ti", "pt", "text", "text"),
            edge("pt", "inf", "rendered_text", "prompt"),
            edge("ms", "inf", "model", "model"),
            edge("inf", "rp", "response", "text"),
            edge("inf", "tc", "response", "text"),
        ]
        pid, run = create_and_run("wf:cross:full-inf", nodes, edges,
                                  timeout=120, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_data_prep_to_eval(self, live_backend):
        """6-block: ti → ttd → text_chunker → filter_sample → data_preview → custom_eval"""
        nodes = [
            text_input_node("ti", "First sentence.\n\nSecond paragraph with more text.\n\nThird short."),
            text_to_dataset_node("ttd"),
            node("ch", "text_chunker", {"strategy": "recursive", "chunk_size": 200, "chunk_overlap": 10}),
            node("fs", "filter_sample", {"method": "not_empty", "text_column": "text"}),
            node("dp", "data_preview"),
            node("ce", "custom_eval", {"scoring_function": "def score(output, reference=None, idx=0):\n    return {'score': len(str(output))}"}),
        ]
        edges = [
            edge("ti", "ttd", "text", "text"),
            edge("ttd", "ch", "dataset", "dataset"),
            edge("ch", "fs", "chunked_dataset", "dataset"),
            edge("fs", "dp", "filtered_dataset", "dataset"),
            edge("fs", "ce", "filtered_dataset", "predictions"),
        ]
        pid, run = create_and_run("wf:cross:data-eval", nodes, edges,
                                  timeout=60, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_agent_to_report(self, ollama_model, live_backend):
        """5-block: ms + ti → cot → agent_text_bridge → report_generator"""
        nodes = [
            model_selector_node("ms", ollama_model),
            text_input_node("ti", "What are 3 types of machine learning?"),
            cot_node("cot", num_steps=2, max_tokens=200),
            node("atb", "agent_text_bridge"),
            node("rg", "report_generator", {"title": "ML Types Report"}),
        ]
        edges = [
            edge("ms", "cot", "llm", "llm"),
            edge("ti", "cot", "text", "input"),
            edge("cot", "atb", "response", "agent"),
            edge("cot", "rg", "metrics", "metrics"),
        ]
        pid, run = create_and_run("wf:cross:agent-report", nodes, edges,
                                  timeout=180, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_metrics_quality_gate_format(self, live_backend):
        """3-block: mi → quality_gate → results_formatter"""
        nodes = [
            metrics_input_node("mi", '{"accuracy": 0.95, "f1": 0.92}'),
            node("qg", "quality_gate", {"metric_name": "accuracy", "operator": ">=", "threshold": 0.8}),
            node("rf", "results_formatter", {"format": "markdown"}),
        ]
        edges = [
            edge("mi", "qg", "metrics", "data"),
            edge("mi", "rf", "metrics", "metrics"),
        ]
        pid, run = create_and_run("wf:cross:metrics-gate", nodes, edges,
                                  stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_data_merge_augment_split(self, live_backend):
        """7-block: two text inputs → merge → augment → split"""
        nodes = [
            text_input_node("a", "The cat sat on the mat.\nThe dog ran fast."),
            text_to_dataset_node("da", split_by="newline"),
            text_input_node("b", "Birds can fly.\nFish can swim."),
            text_to_dataset_node("db", split_by="newline"),
            node("m", "data_merger", {"method": "concat"}),
            node("aug", "data_augmentation", {"strategy": "random_swap", "num_augmented": 1}),
            node("tvts", "train_val_test_split", {"seed": 42}),
        ]
        edges = [
            edge("a", "da", "text", "text"), edge("b", "db", "text", "text"),
            edge("da", "m", "dataset", "dataset_a"), edge("db", "m", "dataset", "dataset_b"),
            edge("m", "aug", "dataset", "dataset"),
            edge("aug", "tvts", "augmented_dataset", "dataset"),
        ]
        pid, run = create_and_run("wf:cross:merge-aug-split", nodes, edges,
                                  timeout=60, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_10_block_pipeline(self, ollama_model, live_backend):
        """10-block mega-pipeline exercising data + inference + eval + output"""
        nodes = [
            model_selector_node("ms", ollama_model),
            text_input_node("ti", "quantum computing"),
            prompt_template_node("pt", "Explain {input} simply."),
            inference_node("inf", ollama_model, max_tokens=100),
            node("rp", "response_parser", {"format": "key_value"}),
            node("tc", "token_counter", {"tokenizer": "estimate"}),
            text_input_node("ti2", "result\ndata"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("dp", "data_preview"),
            node("rf", "results_formatter", {"format": "json"}),
        ]
        edges = [
            edge("ti", "pt", "text", "text"),
            edge("pt", "inf", "rendered_text", "prompt"),
            edge("ms", "inf", "model", "model"),
            edge("inf", "rp", "response", "text"),
            edge("inf", "tc", "response", "text"),
            edge("ti2", "ttd", "text", "text"),
            edge("ttd", "dp", "dataset", "dataset"),
            edge("tc", "rf", "metrics", "metrics"),
        ]
        pid, run = create_and_run("wf:cross:10block", nodes, edges,
                                  timeout=180, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)
        r = replay(run["id"])
        assert len(r["nodes"]) == 10
        assert all(n["status"] == "completed" for n in r["nodes"])

    def test_training_pipeline_full_validate(self, live_backend):
        """Full training pipeline validation: ms + db + qlora + save_model + model_card"""
        nodes = [
            node("ms", "model_selector", {"source": "huggingface", "model_id": "meta-llama/Llama-3.2-1B"}),
            node("db", "dataset_builder", {"source": "huggingface", "hf_dataset": "tatsu-lab/alpaca", "hf_max_samples": 10}),
            node("ql", "qlora_finetuning", {"model_name": "meta-llama/Llama-3.2-1B", "epochs": 1, "batch_size": 1}),
            node("sm", "save_model", {"format": "safetensors"}),
            node("mc", "model_card_writer", {"model_name": "my-model"}),
        ]
        edges = [
            edge("ms", "ql", "model", "model"),
            edge("db", "ql", "dataset", "dataset"),
            edge("ql", "sm", "trained_model", "model"),
            edge("ql", "mc", "metrics", "metrics"),
        ]
        pid = create_pipeline("wf:cross:train-full", nodes, edges)
        val = validate(pid)
        assert val["block_count"] == 5

    def test_error_recovery_workflow(self, live_backend):
        """error_handler catches upstream issue, quality_gate verifies"""
        nodes = [
            text_input_node("ti", "safe data"),
            node("eh", "error_handler"),
            metrics_input_node("mi", '{"quality": 0.95}'),
            node("qg", "quality_gate", {"metric_name": "quality", "operator": ">=", "threshold": 0.5}),
            node("rf", "results_formatter", {"format": "json"}),
        ]
        edges = [
            edge("ti", "eh", "text", "input"),
            edge("mi", "qg", "metrics", "data"),
            edge("mi", "rf", "metrics", "metrics"),
        ]
        pid, run = create_and_run("wf:cross:error-recover", nodes, edges,
                                  stderr_path=live_backend.stderr_path)
        assert_run_complete(run)
