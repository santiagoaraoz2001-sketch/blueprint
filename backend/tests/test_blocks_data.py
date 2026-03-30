"""Exhaustive tests for all 27 data blocks.

Covers: text_input, text_to_dataset, text_concatenator, text_chunker,
data_merger, data_preview, dataset_row_selector, dataset_to_text,
filter_sample, column_transform, config_builder, config_file_loader,
metrics_input, metrics_to_dataset, local_file_loader, train_val_test_split,
document_ingestion, data_augmentation, model_selector, huggingface_loader,
huggingface_model_loader, synthetic_data_gen, web_scraper, api_data_fetcher,
sql_query, vector_store_build, dataset_builder
"""

from __future__ import annotations
import pytest

pytestmark = pytest.mark.slow

from .block_test_helpers import (
    node, edge, text_input_node, text_to_dataset_node, metrics_input_node,
    model_selector_node, inference_node, prompt_template_node,
    create_pipeline, execute, validate, dry_run, validate_config,
    create_and_run, replay, wait_for_run,
    assert_run_complete, assert_replay_nodes, assert_validation_no_structural_errors,
)


# ═══════════════════════════════════════════════════════════════════════
#  TEXT_INPUT (source block — no inputs)
# ═══════════════════════════════════════════════════════════════════════

class TestTextInput:
    def test_standalone(self, live_backend):
        nodes = [text_input_node("ti", "Hello, world!")]
        pid, run = create_and_run("data:ti:basic", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_empty_string(self, live_backend):
        nodes = [text_input_node("ti", "")]
        pid, run = create_and_run("data:ti:empty", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_unicode_and_emoji(self, live_backend):
        nodes = [text_input_node("ti", "日本語テスト 🚀 résumé Ñ")]
        pid, run = create_and_run("data:ti:unicode", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_multiline(self, live_backend):
        nodes = [text_input_node("ti", "line1\nline2\nline3\nline4\nline5")]
        pid, run = create_and_run("data:ti:multiline", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_large_text(self, live_backend):
        nodes = [text_input_node("ti", "x" * 10000)]
        pid, run = create_and_run("data:ti:large", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  CONFIG_BUILDER (source block)
# ═══════════════════════════════════════════════════════════════════════

class TestConfigBuilder:
    def test_json_body(self, live_backend):
        nodes = [node("cb", "config_builder", {"json_body": '{"lr": 0.001, "epochs": 3}'})]
        pid, run = create_and_run("data:cb:json", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_yaml_body(self, live_backend):
        nodes = [node("cb", "config_builder", {"json_body": "lr: 0.001\nepochs: 3"})]
        pid, run = create_and_run("data:cb:yaml", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_empty_json(self, live_backend):
        nodes = [node("cb", "config_builder", {"json_body": "{}"})]
        pid, run = create_and_run("data:cb:empty", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_nested_config(self, live_backend):
        nodes = [node("cb", "config_builder", {"json_body": '{"model": {"name": "llama", "params": {"lr": 0.001}}}'})]
        pid, run = create_and_run("data:cb:nested", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_invalid_json_fallback(self, live_backend):
        nodes = [node("cb", "config_builder", {"json_body": "not valid json {{{"})]
        pid, run = create_and_run("data:cb:invalid", nodes, [], stderr_path=live_backend.stderr_path)
        # Should still complete — falls back to raw text
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  METRICS_INPUT (source block)
# ═══════════════════════════════════════════════════════════════════════

class TestMetricsInput:
    def test_json_format(self, live_backend):
        nodes = [metrics_input_node("mi", '{"accuracy": 0.92, "loss": 0.08}')]
        pid, run = create_and_run("data:mi:json", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_empty_metrics(self, live_backend):
        nodes = [metrics_input_node("mi", "{}")]
        pid, run = create_and_run("data:mi:empty", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_nested_metrics(self, live_backend):
        nodes = [metrics_input_node("mi", '{"train": {"loss": 0.1}, "eval": {"loss": 0.2}}')]
        pid, run = create_and_run("data:mi:nested", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_key_value_format(self, live_backend):
        nodes = [node("mi", "metrics_input", {"metrics_json": "accuracy=0.92\nloss=0.08", "format": "key_value"})]
        pid, run = create_and_run("data:mi:kv", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_single_metric(self, live_backend):
        nodes = [metrics_input_node("mi", '{"score": 42}')]
        pid, run = create_and_run("data:mi:single", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  TEXT_TO_DATASET
# ═══════════════════════════════════════════════════════════════════════

class TestTextToDataset:
    def test_standalone(self, live_backend):
        nodes = [text_input_node("ti", "Hello world"), text_to_dataset_node("ttd")]
        edges = [edge("ti", "ttd", "text", "text")]
        pid, run = create_and_run("data:ttd:basic", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)
        assert_replay_nodes(run["id"], 2)

    def test_split_by_newline(self, live_backend):
        nodes = [
            text_input_node("ti", "line1\nline2\nline3"),
            text_to_dataset_node("ttd", split_by="newline"),
        ]
        edges = [edge("ti", "ttd", "text", "text")]
        pid, run = create_and_run("data:ttd:newline", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_split_by_paragraph(self, live_backend):
        nodes = [
            text_input_node("ti", "para1\n\npara2\n\npara3"),
            text_to_dataset_node("ttd", split_by="paragraph"),
        ]
        edges = [edge("ti", "ttd", "text", "text")]
        pid, run = create_and_run("data:ttd:para", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_custom_column_name(self, live_backend):
        nodes = [
            text_input_node("ti", "test data"),
            text_to_dataset_node("ttd", column_name="content"),
        ]
        edges = [edge("ti", "ttd", "text", "text")]
        pid, run = create_and_run("data:ttd:colname", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_empty_text(self, live_backend):
        nodes = [text_input_node("ti", ""), text_to_dataset_node("ttd")]
        edges = [edge("ti", "ttd", "text", "text")]
        pid, run = create_and_run("data:ttd:empty", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  DATASET_TO_TEXT
# ═══════════════════════════════════════════════════════════════════════

class TestDatasetToText:
    def test_standalone(self, live_backend):
        nodes = [
            text_input_node("ti", "hello\nworld"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("dtt", "dataset_to_text", {"text_column": "text"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "dtt", "dataset", "dataset")]
        pid, run = create_and_run("data:dtt:basic", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_single_row(self, live_backend):
        nodes = [
            text_input_node("ti", "one\ntwo\nthree"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("dtt", "dataset_to_text", {"row_index": 0}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "dtt", "dataset", "dataset")]
        pid, run = create_and_run("data:dtt:row0", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_auto_detect_column(self, live_backend):
        nodes = [
            text_input_node("ti", "hello world"),
            text_to_dataset_node("ttd"),
            node("dtt", "dataset_to_text"),  # No text_column set — auto-detect
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "dtt", "dataset", "dataset")]
        pid, run = create_and_run("data:dtt:auto", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  TEXT_CONCATENATOR
# ═══════════════════════════════════════════════════════════════════════

class TestTextConcatenator:
    def test_two_inputs(self, live_backend):
        nodes = [
            text_input_node("a", "Hello"),
            text_input_node("b", "World"),
            node("tc", "text_concatenator"),
        ]
        edges = [edge("a", "tc", "text", "text_a"), edge("b", "tc", "text", "text_b")]
        pid, run = create_and_run("data:tc:two", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_three_inputs(self, live_backend):
        nodes = [
            text_input_node("a", "One"),
            text_input_node("b", "Two"),
            text_input_node("c", "Three"),
            node("tc", "text_concatenator"),
        ]
        edges = [
            edge("a", "tc", "text", "text_a"),
            edge("b", "tc", "text", "text_b"),
            edge("c", "tc", "text", "text_c"),
        ]
        pid, run = create_and_run("data:tc:three", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_custom_separator(self, live_backend):
        nodes = [
            text_input_node("a", "Hello"),
            text_input_node("b", "World"),
            node("tc", "text_concatenator", {"separator": " | "}),
        ]
        edges = [edge("a", "tc", "text", "text_a"), edge("b", "tc", "text", "text_b")]
        pid, run = create_and_run("data:tc:sep", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_max_length(self, live_backend):
        nodes = [
            text_input_node("a", "A" * 100),
            text_input_node("b", "B" * 100),
            node("tc", "text_concatenator", {"max_length": 50}),
        ]
        edges = [edge("a", "tc", "text", "text_a"), edge("b", "tc", "text", "text_b")]
        pid, run = create_and_run("data:tc:maxlen", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  TEXT_CHUNKER
# ═══════════════════════════════════════════════════════════════════════

class TestTextChunker:
    def test_character_strategy(self, live_backend):
        nodes = [
            text_input_node("ti", "A" * 200),
            text_to_dataset_node("ttd"),
            node("ch", "text_chunker", {"strategy": "character", "chunk_size": 200, "chunk_overlap": 10}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "ch", "dataset", "dataset")]
        pid, run = create_and_run("data:ch:char", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_paragraph_strategy(self, live_backend):
        nodes = [
            text_input_node("ti", "Para 1 text.\n\nPara 2 text.\n\nPara 3 text."),
            text_to_dataset_node("ttd"),
            node("ch", "text_chunker", {"strategy": "recursive", "chunk_size": 100, "chunk_overlap": 10}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "ch", "dataset", "dataset")]
        pid, run = create_and_run("data:ch:recursive", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_sentence_strategy(self, live_backend):
        nodes = [
            text_input_node("ti", "First sentence. Second sentence. Third sentence. Fourth sentence."),
            text_to_dataset_node("ttd"),
            node("ch", "text_chunker", {"strategy": "token", "chunk_size": 50, "chunk_overlap": 5}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "ch", "dataset", "dataset")]
        pid, run = create_and_run("data:ch:sent", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_small_chunks(self, live_backend):
        nodes = [
            text_input_node("ti", "The quick brown fox jumps over the lazy dog."),
            text_to_dataset_node("ttd"),
            node("ch", "text_chunker", {"strategy": "character", "chunk_size": 50, "chunk_overlap": 0}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "ch", "dataset", "dataset")]
        pid, run = create_and_run("data:ch:small", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  DATA_MERGER
# ═══════════════════════════════════════════════════════════════════════

class TestDataMerger:
    def _two_datasets(self):
        return [
            text_input_node("a", "apple\nbanana"),
            text_to_dataset_node("da", split_by="newline"),
            text_input_node("b", "cherry\ndate"),
            text_to_dataset_node("db", split_by="newline"),
        ], [
            edge("a", "da", "text", "text"),
            edge("b", "db", "text", "text"),
        ]

    def test_concat(self, live_backend):
        base_nodes, base_edges = self._two_datasets()
        merger = node("m", "data_merger", {"method": "concat"})
        nodes = base_nodes + [merger]
        edges = base_edges + [edge("da", "m", "dataset", "dataset_a"), edge("db", "m", "dataset", "dataset_b")]
        pid, run = create_and_run("data:dm:concat", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_interleave(self, live_backend):
        base_nodes, base_edges = self._two_datasets()
        merger = node("m", "data_merger", {"method": "interleave"})
        nodes = base_nodes + [merger]
        edges = base_edges + [edge("da", "m", "dataset", "dataset_a"), edge("db", "m", "dataset", "dataset_b")]
        pid, run = create_and_run("data:dm:interleave", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_dedup(self, live_backend):
        base_nodes, base_edges = self._two_datasets()
        merger = node("m", "data_merger", {"method": "dedup"})
        nodes = base_nodes + [merger]
        edges = base_edges + [edge("da", "m", "dataset", "dataset_a"), edge("db", "m", "dataset", "dataset_b")]
        pid, run = create_and_run("data:dm:dedup", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_shuffle(self, live_backend):
        base_nodes, base_edges = self._two_datasets()
        merger = node("m", "data_merger", {"method": "concat", "shuffle": True, "seed": 42})
        nodes = base_nodes + [merger]
        edges = base_edges + [edge("da", "m", "dataset", "dataset_a"), edge("db", "m", "dataset", "dataset_b")]
        pid, run = create_and_run("data:dm:shuffle", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  DATA_PREVIEW
# ═══════════════════════════════════════════════════════════════════════

class TestDataPreview:
    def test_basic(self, live_backend):
        nodes = [
            text_input_node("ti", "a\nb\nc\nd\ne"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("dp", "data_preview"),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "dp", "dataset", "dataset")]
        pid, run = create_and_run("data:dp:basic", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_head_mode(self, live_backend):
        nodes = [
            text_input_node("ti", "\n".join(f"row{i}" for i in range(20))),
            text_to_dataset_node("ttd", split_by="newline"),
            node("dp", "data_preview", {"sample_mode": "head", "sample_size": 5}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "dp", "dataset", "dataset")]
        pid, run = create_and_run("data:dp:head", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_random_mode(self, live_backend):
        nodes = [
            text_input_node("ti", "\n".join(f"row{i}" for i in range(20))),
            text_to_dataset_node("ttd", split_by="newline"),
            node("dp", "data_preview", {"sample_mode": "random", "sample_size": 3, "seed": 42}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "dp", "dataset", "dataset")]
        pid, run = create_and_run("data:dp:random", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  DATASET_ROW_SELECTOR
# ═══════════════════════════════════════════════════════════════════════

class TestDatasetRowSelector:
    def test_first_mode(self, live_backend):
        nodes = [
            text_input_node("ti", "a\nb\nc"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("rs", "dataset_row_selector", {"mode": "first", "count": 1}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "rs", "dataset", "dataset")]
        pid, run = create_and_run("data:rs:first", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_last_mode(self, live_backend):
        nodes = [
            text_input_node("ti", "a\nb\nc"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("rs", "dataset_row_selector", {"mode": "last", "count": 2}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "rs", "dataset", "dataset")]
        pid, run = create_and_run("data:rs:last", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_random_mode(self, live_backend):
        nodes = [
            text_input_node("ti", "a\nb\nc\nd\ne"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("rs", "dataset_row_selector", {"mode": "random", "count": 2, "seed": 42}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "rs", "dataset", "dataset")]
        pid, run = create_and_run("data:rs:random", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  FILTER_SAMPLE
# ═══════════════════════════════════════════════════════════════════════

class TestFilterSample:
    def test_not_empty(self, live_backend):
        nodes = [
            text_input_node("ti", "hello\n\nworld\n\n"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("fs", "filter_sample", {"method": "not_empty", "text_column": "text"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "fs", "dataset", "dataset")]
        pid, run = create_and_run("data:fs:notempty", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_length_filter(self, live_backend):
        nodes = [
            text_input_node("ti", "hi\nhello world\nthis is a longer sentence"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("fs", "filter_sample", {"method": "length", "text_column": "text", "min_length": 5}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "fs", "dataset", "dataset")]
        pid, run = create_and_run("data:fs:length", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_random_sample(self, live_backend):
        nodes = [
            text_input_node("ti", "\n".join(f"row{i}" for i in range(20))),
            text_to_dataset_node("ttd", split_by="newline"),
            node("fs", "filter_sample", {"method": "random_sample", "sample_size": 5, "seed": 42}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "fs", "dataset", "dataset")]
        pid, run = create_and_run("data:fs:random", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_regex_filter(self, live_backend):
        nodes = [
            text_input_node("ti", "abc123\nhello\ntest456\nworld"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("fs", "filter_sample", {"method": "regex", "text_column": "text", "regex_pattern": "\\d+"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "fs", "dataset", "dataset")]
        pid, run = create_and_run("data:fs:regex", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_dedup(self, live_backend):
        nodes = [
            text_input_node("ti", "hello\nworld\nhello\nfoo\nworld"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("fs", "filter_sample", {"method": "dedup", "text_column": "text"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "fs", "dataset", "dataset")]
        pid, run = create_and_run("data:fs:dedup", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  COLUMN_TRANSFORM
# ═══════════════════════════════════════════════════════════════════════

class TestColumnTransform:
    def test_rename(self, live_backend):
        nodes = [
            text_input_node("ti", "hello\nworld"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("ct", "column_transform", {"operation": "rename", "source_column": "text", "target_column": "content"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "ct", "dataset", "dataset")]
        pid, run = create_and_run("data:ct:rename", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_keep_columns(self, live_backend):
        nodes = [
            text_input_node("ti", "hello\nworld"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("ct", "column_transform", {"operation": "keep", "keep_columns": "text"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "ct", "dataset", "dataset")]
        pid, run = create_and_run("data:ct:keep", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_lowercase(self, live_backend):
        nodes = [
            text_input_node("ti", "HELLO\nWORLD"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("ct", "column_transform", {"operation": "lowercase", "lowercase_columns": "text"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "ct", "dataset", "dataset")]
        pid, run = create_and_run("data:ct:lower", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  TRAIN_VAL_TEST_SPLIT
# ═══════════════════════════════════════════════════════════════════════

class TestTrainValTestSplit:
    def test_default_split(self, live_backend):
        nodes = [
            text_input_node("ti", "\n".join(f"row{i}" for i in range(20))),
            text_to_dataset_node("ttd", split_by="newline"),
            node("tvts", "train_val_test_split", {"seed": 42}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "tvts", "dataset", "dataset")]
        pid, run = create_and_run("data:tvts:default", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_custom_ratios(self, live_backend):
        nodes = [
            text_input_node("ti", "\n".join(f"row{i}" for i in range(30))),
            text_to_dataset_node("ttd", split_by="newline"),
            node("tvts", "train_val_test_split", {
                "train_ratio": 0.6, "val_ratio": 0.2, "test_ratio": 0.2, "seed": 42,
            }),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "tvts", "dataset", "dataset")]
        pid, run = create_and_run("data:tvts:custom", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_no_test_split(self, live_backend):
        nodes = [
            text_input_node("ti", "\n".join(f"row{i}" for i in range(10))),
            text_to_dataset_node("ttd", split_by="newline"),
            node("tvts", "train_val_test_split", {
                "train_ratio": 0.8, "val_ratio": 0.2, "test_ratio": 0.0, "seed": 42,
            }),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "tvts", "dataset", "dataset")]
        pid, run = create_and_run("data:tvts:notst", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  METRICS_TO_DATASET
# ═══════════════════════════════════════════════════════════════════════

class TestMetricsToDataset:
    def test_standalone(self, live_backend):
        nodes = [
            metrics_input_node("mi", '{"accuracy": 0.92, "loss": 0.08}'),
            node("mtd", "metrics_to_dataset"),
        ]
        edges = [edge("mi", "mtd", "metrics", "metrics")]
        pid, run = create_and_run("data:mtd:basic", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_columns_format(self, live_backend):
        nodes = [
            metrics_input_node("mi", '{"a": 1, "b": 2, "c": 3}'),
            node("mtd", "metrics_to_dataset", {"format": "columns"}),
        ]
        edges = [edge("mi", "mtd", "metrics", "metrics")]
        pid, run = create_and_run("data:mtd:cols", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  DATA_AUGMENTATION (rule-based strategies — no model needed)
# ═══════════════════════════════════════════════════════════════════════

class TestDataAugmentation:
    def test_synonym_swap(self, live_backend):
        nodes = [
            text_input_node("ti", "The quick brown fox jumps over the lazy dog."),
            text_to_dataset_node("ttd"),
            node("aug", "data_augmentation", {"strategy": "synonym_swap", "num_augmented": 2}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "aug", "dataset", "dataset")]
        pid, run = create_and_run("data:aug:syn", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_random_deletion(self, live_backend):
        nodes = [
            text_input_node("ti", "The quick brown fox jumps over the lazy dog."),
            text_to_dataset_node("ttd"),
            node("aug", "data_augmentation", {"strategy": "random_deletion", "num_augmented": 2, "aug_probability": 0.3}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "aug", "dataset", "dataset")]
        pid, run = create_and_run("data:aug:del", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_random_swap(self, live_backend):
        nodes = [
            text_input_node("ti", "The quick brown fox jumps over the lazy dog."),
            text_to_dataset_node("ttd"),
            node("aug", "data_augmentation", {"strategy": "random_swap", "num_augmented": 2}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "aug", "dataset", "dataset")]
        pid, run = create_and_run("data:aug:swap", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_char_noise(self, live_backend):
        nodes = [
            text_input_node("ti", "Hello world this is a test sentence."),
            text_to_dataset_node("ttd"),
            node("aug", "data_augmentation", {"strategy": "char_noise", "num_augmented": 2, "aug_probability": 0.1}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "aug", "dataset", "dataset")]
        pid, run = create_and_run("data:aug:noise", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_random_insertion(self, live_backend):
        nodes = [
            text_input_node("ti", "Hello world this is a test."),
            text_to_dataset_node("ttd"),
            node("aug", "data_augmentation", {"strategy": "random_insertion", "num_augmented": 2}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "aug", "dataset", "dataset")]
        pid, run = create_and_run("data:aug:ins", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  VALIDATION-ONLY BLOCKS (need internet/GPU/special deps)
# ═══════════════════════════════════════════════════════════════════════

class TestDataBlocksValidation:
    """Validate config for blocks that need external services."""

    def test_config_file_loader_validate(self, live_backend):
        status, data = validate_config("config_file_loader", {"file_path": "/tmp/test.json", "format": "auto"})
        assert status == 200

    def test_local_file_loader_validate(self, live_backend):
        status, data = validate_config("local_file_loader", {"file_path": "/tmp/test.csv"})
        assert status == 200

    def test_huggingface_loader_validate(self, live_backend):
        status, data = validate_config("huggingface_loader", {"dataset_name": "imdb", "split": "train", "max_samples": 10})
        assert status == 200

    def test_huggingface_model_loader_validate(self, live_backend):
        status, data = validate_config("huggingface_model_loader", {"model_id": "meta-llama/Llama-3.2-1B"})
        assert status == 200

    def test_synthetic_data_gen_validate(self, live_backend):
        status, data = validate_config("synthetic_data_gen", {"num_samples": 10, "temperature": 0.8})
        assert status == 200

    def test_web_scraper_validate(self, live_backend):
        status, data = validate_config("web_scraper", {"url": "https://example.com", "mode": "single_page"})
        assert status == 200

    def test_api_data_fetcher_validate(self, live_backend):
        status, data = validate_config("api_data_fetcher", {"url": "https://api.example.com/data", "method": "GET"})
        assert status == 200

    def test_sql_query_validate(self, live_backend):
        status, data = validate_config("sql_query", {"db_path": "/tmp/test.db", "query": "SELECT 1"})
        assert status == 200

    def test_vector_store_build_validate(self, live_backend):
        status, data = validate_config("vector_store_build", {"backend": "chroma", "collection_name": "test"})
        assert status == 200

    def test_document_ingestion_validate(self, live_backend):
        status, data = validate_config("document_ingestion", {"directory_path": "/tmp/docs", "chunk_strategy": "character"})
        assert status == 200

    def test_dataset_builder_validate(self, live_backend):
        status, data = validate_config("dataset_builder", {"source": "huggingface", "hf_dataset": "imdb"})
        assert status == 200


# ═══════════════════════════════════════════════════════════════════════
#  E2E DATA WORKFLOWS
# ═══════════════════════════════════════════════════════════════════════

class TestDataWorkflows:
    def test_text_to_chunked_preview(self, live_backend):
        """ti → ttd → chunker → data_preview"""
        nodes = [
            text_input_node("ti", "Para one with text.\n\nPara two here.\n\nPara three final."),
            text_to_dataset_node("ttd"),
            node("ch", "text_chunker", {"strategy": "recursive", "chunk_size": 100, "chunk_overlap": 10}),
            node("dp", "data_preview"),
        ]
        edges = [
            edge("ti", "ttd", "text", "text"),
            edge("ttd", "ch", "dataset", "dataset"),
            edge("ch", "dp", "chunked_dataset", "dataset"),
        ]
        pid, run = create_and_run("wf:data:chunk-preview", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_merge_and_split(self, live_backend):
        """two datasets → merger → train_val_test_split"""
        nodes = [
            text_input_node("a", "\n".join(f"apple{i}" for i in range(10))),
            text_to_dataset_node("da", split_by="newline"),
            text_input_node("b", "\n".join(f"banana{i}" for i in range(10))),
            text_to_dataset_node("db", split_by="newline"),
            node("m", "data_merger", {"method": "concat"}),
            node("tvts", "train_val_test_split", {"seed": 42}),
        ]
        edges = [
            edge("a", "da", "text", "text"),
            edge("b", "db", "text", "text"),
            edge("da", "m", "dataset", "dataset_a"),
            edge("db", "m", "dataset", "dataset_b"),
            edge("m", "tvts", "dataset", "dataset"),
        ]
        pid, run = create_and_run("wf:data:merge-split", nodes, edges,
                                  timeout=60, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_augment_and_preview(self, live_backend):
        """ti → ttd → augmentation → data_preview"""
        nodes = [
            text_input_node("ti", "The cat sat on the mat.\nThe dog ran in the park."),
            text_to_dataset_node("ttd", split_by="newline"),
            node("aug", "data_augmentation", {"strategy": "random_swap", "num_augmented": 2}),
            node("dp", "data_preview"),
        ]
        edges = [
            edge("ti", "ttd", "text", "text"),
            edge("ttd", "aug", "dataset", "dataset"),
            edge("aug", "dp", "augmented_dataset", "dataset"),
        ]
        pid, run = create_and_run("wf:data:aug-preview", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)
