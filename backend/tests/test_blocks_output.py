"""Exhaustive tests for all 5 output blocks."""

from __future__ import annotations
import pytest

pytestmark = pytest.mark.slow

from .block_test_helpers import (
    node, edge, text_input_node, text_to_dataset_node, metrics_input_node,
    create_pipeline, validate, validate_config,
    create_and_run, assert_run_complete,
)


class TestResultsFormatter:
    def test_csv(self, live_backend):
        nodes = [metrics_input_node("mi"), node("rf", "results_formatter", {"format": "csv"})]
        edges = [edge("mi", "rf", "metrics", "metrics")]
        pid, run = create_and_run("out:rf:csv", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_json(self, live_backend):
        nodes = [metrics_input_node("mi"), node("rf", "results_formatter", {"format": "json"})]
        edges = [edge("mi", "rf", "metrics", "metrics")]
        pid, run = create_and_run("out:rf:json", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_markdown(self, live_backend):
        nodes = [metrics_input_node("mi"), node("rf", "results_formatter", {"format": "markdown"})]
        edges = [edge("mi", "rf", "metrics", "metrics")]
        pid, run = create_and_run("out:rf:md", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_nested_metrics(self, live_backend):
        nodes = [
            metrics_input_node("mi", '{"train": {"loss": 0.1, "acc": 0.9}, "eval": {"loss": 0.2}}'),
            node("rf", "results_formatter", {"format": "json"}),
        ]
        edges = [edge("mi", "rf", "metrics", "metrics")]
        pid, run = create_and_run("out:rf:nested", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_include_config(self, live_backend):
        nodes = [
            metrics_input_node("mi"),
            node("rf", "results_formatter", {"format": "csv", "include_config": True}),
        ]
        edges = [edge("mi", "rf", "metrics", "metrics")]
        pid, run = create_and_run("out:rf:config", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


class TestReportGenerator:
    def test_standalone(self, live_backend):
        nodes = [
            metrics_input_node("mi"),
            node("rg", "report_generator", {"title": "Test Report"}),
        ]
        edges = [edge("mi", "rg", "metrics", "metrics")]
        pid, run = create_and_run("out:rg:basic", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_with_dataset(self, live_backend):
        nodes = [
            metrics_input_node("mi"),
            text_input_node("ti", "a\nb\nc"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("rg", "report_generator", {"title": "Full Report"}),
        ]
        edges = [
            edge("mi", "rg", "metrics", "metrics"),
            edge("ti", "ttd", "text", "text"),
            edge("ttd", "rg", "dataset", "dataset"),
        ]
        pid, run = create_and_run("out:rg:dataset", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_custom_sections(self, live_backend):
        nodes = [
            metrics_input_node("mi"),
            node("rg", "report_generator", {"title": "Report", "sections": "summary,metrics"}),
        ]
        edges = [edge("mi", "rg", "metrics", "metrics")]
        pid, run = create_and_run("out:rg:sections", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


class TestModelCardWriter:
    def test_standalone(self, live_backend):
        nodes = [node("mcw", "model_card_writer", {"model_name": "test-model", "base_model": "llama-3.2"})]
        pid, run = create_and_run("out:mcw:basic", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_with_metrics(self, live_backend):
        nodes = [
            metrics_input_node("mi", '{"eval_loss": 0.05, "perplexity": 12.3}'),
            node("mcw", "model_card_writer", {"model_name": "my-model"}),
        ]
        edges = [edge("mi", "mcw", "metrics", "metrics")]
        pid, run = create_and_run("out:mcw:metrics", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_minimal(self, live_backend):
        nodes = [node("mcw", "model_card_writer")]
        pid, run = create_and_run("out:mcw:minimal", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_html_format(self, live_backend):
        nodes = [node("mcw", "model_card_writer", {"model_name": "test", "format": "html"})]
        pid, run = create_and_run("out:mcw:html", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


class TestArtifactPackager:
    def test_config(self, live_backend):
        s, d = validate_config("artifact_packager", {"archive_format": "zip", "include_metadata": True})
        assert s == 200

    def test_validate_pipeline(self, live_backend):
        nodes = [text_input_node("ti", "data"), node("ap", "artifact_packager")]
        edges = [edge("ti", "ap", "text", "input")]
        pid = create_pipeline("out:ap:val", nodes, edges)
        val = validate(pid)
        assert val["block_count"] == 2


class TestLeaderboardPublisher:
    def test_config(self, live_backend):
        s, d = validate_config("leaderboard_publisher", {"leaderboard_name": "test"})
        assert s == 200


class TestOutputWorkflows:
    def test_metrics_to_report_and_formatter(self, live_backend):
        """mi → report_generator + results_formatter"""
        nodes = [
            metrics_input_node("mi"),
            node("rg", "report_generator", {"title": "Workflow Report"}),
            node("rf", "results_formatter", {"format": "json"}),
        ]
        edges = [
            edge("mi", "rg", "metrics", "metrics"),
            edge("mi", "rf", "metrics", "metrics"),
        ]
        pid, run = create_and_run("wf:out:report-format", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)
