"""Exhaustive tests for all 8 endpoint blocks."""

from __future__ import annotations
import pytest

pytestmark = pytest.mark.slow

from .block_test_helpers import (
    node, edge, text_input_node, text_to_dataset_node,
    create_pipeline, validate, validate_config,
    create_and_run, assert_run_complete,
)


class TestDataExport:
    def test_json_format(self, live_backend):
        nodes = [
            text_input_node("ti", "hello\nworld"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("de", "data_export", {"format": "json"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "de", "dataset", "data")]
        pid, run = create_and_run("ep:de:json", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_csv_format(self, live_backend):
        nodes = [
            text_input_node("ti", "hello\nworld"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("de", "data_export", {"format": "csv"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "de", "dataset", "data")]
        pid, run = create_and_run("ep:de:csv", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_txt_format(self, live_backend):
        nodes = [
            text_input_node("ti", "plain text data"),
            node("de", "data_export", {"format": "txt"}),
        ]
        edges = [edge("ti", "de", "text", "data")]
        pid, run = create_and_run("ep:de:txt", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_auto_format(self, live_backend):
        nodes = [
            text_input_node("ti", "a\nb\nc"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("de", "data_export", {"format": "auto"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "de", "dataset", "data")]
        pid, run = create_and_run("ep:de:auto", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_timestamp_filename(self, live_backend):
        nodes = [
            text_input_node("ti", "data"),
            text_to_dataset_node("ttd"),
            node("de", "data_export", {"format": "json", "timestamp_filename": True}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "de", "dataset", "data")]
        pid, run = create_and_run("ep:de:ts", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


class TestDatabaseWriter:
    def test_validate_config(self, live_backend):
        s, d = validate_config("database_writer", {"connection_string": "sqlite:///test.db", "table_name": "results"})
        assert s == 200

    def test_validate_pipeline(self, live_backend):
        nodes = [
            text_input_node("ti", "test"),
            text_to_dataset_node("ttd"),
            node("dbw", "database_writer", {"connection_string": "sqlite:///test.db", "table_name": "test"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "dbw", "dataset", "data")]
        pid = create_pipeline("ep:dbw:val", nodes, edges)
        val = validate(pid)
        assert val["block_count"] == 3


class TestSaveModel:
    def test_validate_config(self, live_backend):
        s, d = validate_config("save_model", {"format": "safetensors", "output_path": "/tmp/model"})
        assert s == 200

    def test_validate_pipeline(self, live_backend):
        nodes = [
            node("ms", "model_selector", {"source": "huggingface", "model_id": "test"}),
            node("sm", "save_model", {"format": "safetensors"}),
        ]
        edges = [edge("ms", "sm", "model", "model")]
        pid = create_pipeline("ep:sm:val", nodes, edges)
        val = validate(pid)
        assert val["block_count"] == 2


class TestEndpointValidation:
    def test_hf_hub_push_config(self, live_backend):
        s, d = validate_config("hf_hub_push", {"repo_id": "user/model", "repo_type": "model"})
        assert s == 200

    def test_api_publisher_config(self, live_backend):
        s, d = validate_config("api_publisher", {"host": "0.0.0.0", "port": 5000})
        assert s == 200

    def test_webhook_trigger_config(self, live_backend):
        s, d = validate_config("webhook_trigger", {"url": "https://hooks.example.com", "method": "POST"})
        assert s == 200

    def test_save_pdf_config(self, live_backend):
        s, d = validate_config("save_pdf", {"title": "Report", "format": "a4"})
        assert s == 200

    def test_save_embeddings_config(self, live_backend):
        s, d = validate_config("save_embeddings", {"format": "numpy", "output_path": "/tmp/embeddings"})
        assert s == 200


class TestEndpointWorkflows:
    def test_inference_to_export(self, ollama_model, live_backend):
        """ms + ti → inf → data_export"""
        nodes = [
            node("ms", "model_selector", {"source": "ollama", "model_id": ollama_model}),
            text_input_node("ti", "Say hello."),
            node("inf", "llm_inference", {"model_name": ollama_model, "max_tokens": 30}),
            node("de", "data_export", {"format": "txt"}),
        ]
        edges = [
            edge("ms", "inf", "model", "model"),
            edge("ti", "inf", "text", "prompt"),
            edge("inf", "de", "response", "data"),
        ]
        pid, run = create_and_run("wf:ep:inf-export", nodes, edges,
                                  timeout=120, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)
