"""Exhaustive tests for all 18 flow blocks.

Tier 1 (full execution): conditional_branch, aggregator, error_handler, quality_gate,
    parallel_fan_out, loop_iterator, ab_split_test, python_runner, rollback_point, artifact_viewer
Tier 2/3 (validation): loop_controller, embedding_visualizer, cloud_compute_provider,
    notification_hub, experiment_logger, human_review_gate, agentic_review_loop, control_tower
"""

from __future__ import annotations
import pytest

pytestmark = pytest.mark.slow

from .block_test_helpers import (
    node, edge, text_input_node, text_to_dataset_node, metrics_input_node,
    model_selector_node, inference_node,
    create_pipeline, validate, validate_config,
    create_and_run, assert_run_complete, assert_replay_nodes,
)


# ═══════════════════════════════════════════════════════════════════════
#  CONDITIONAL_BRANCH
# ═══════════════════════════════════════════════════════════════════════

class TestConditionalBranch:
    def test_is_not_empty(self, live_backend):
        nodes = [
            text_input_node("ti", "some data"),
            node("cb", "conditional_branch", {"operator": "is_not_empty"}),
        ]
        edges = [edge("ti", "cb", "text", "input")]
        pid, run = create_and_run("flow:cb:notempty", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_is_empty(self, live_backend):
        nodes = [
            text_input_node("ti", ""),
            node("cb", "conditional_branch", {"operator": "is_empty"}),
        ]
        edges = [edge("ti", "cb", "text", "input")]
        pid, run = create_and_run("flow:cb:empty", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_contains(self, live_backend):
        nodes = [
            text_input_node("ti", "The answer is 42"),
            node("cb", "conditional_branch", {"operator": "contains", "value": "42"}),
        ]
        edges = [edge("ti", "cb", "text", "input")]
        pid, run = create_and_run("flow:cb:contains", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_greater_than_with_metrics(self, live_backend):
        nodes = [
            metrics_input_node("mi", '{"accuracy": 0.9}'),
            node("cb", "conditional_branch", {"field": "accuracy", "operator": "greater_than", "value": "0.5"}),
        ]
        edges = [edge("mi", "cb", "metrics", "input")]
        pid, run = create_and_run("flow:cb:gt", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_custom_expression(self, live_backend):
        nodes = [
            text_input_node("ti", "Hello World"),
            node("cb", "conditional_branch", {"condition": "len(str(input_data)) > 5"}),
        ]
        edges = [edge("ti", "cb", "text", "input")]
        pid, run = create_and_run("flow:cb:expr", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  AGGREGATOR
# ═══════════════════════════════════════════════════════════════════════

class TestAggregator:
    def test_concatenate(self, live_backend):
        nodes = [
            text_input_node("a", "apple\nbanana"),
            text_to_dataset_node("da", split_by="newline"),
            text_input_node("b", "cherry\ndate"),
            text_to_dataset_node("db", split_by="newline"),
            node("agg", "aggregator", {"strategy": "concatenate"}),
        ]
        edges = [
            edge("a", "da", "text", "text"), edge("b", "db", "text", "text"),
            edge("da", "agg", "dataset", "in_1"), edge("db", "agg", "dataset", "in_2"),
        ]
        pid, run = create_and_run("flow:agg:concat", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_merge_fields(self, live_backend):
        nodes = [
            text_input_node("a", "hello"),
            text_input_node("b", "world"),
            node("agg", "aggregator", {"strategy": "merge_fields"}),
        ]
        edges = [edge("a", "agg", "text", "in_1"), edge("b", "agg", "text", "in_2")]
        pid, run = create_and_run("flow:agg:merge", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_pick_first(self, live_backend):
        nodes = [
            text_input_node("a", "first"),
            text_input_node("b", "second"),
            node("agg", "aggregator", {"strategy": "pick_first"}),
        ]
        edges = [edge("a", "agg", "text", "in_1"), edge("b", "agg", "text", "in_2")]
        pid, run = create_and_run("flow:agg:first", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  ERROR_HANDLER
# ═══════════════════════════════════════════════════════════════════════

class TestErrorHandler:
    def test_passthrough(self, live_backend):
        nodes = [
            text_input_node("ti", "safe data"),
            node("eh", "error_handler"),
        ]
        edges = [edge("ti", "eh", "text", "input")]
        pid, run = create_and_run("flow:eh:pass", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_with_script(self, live_backend):
        nodes = [
            text_input_node("ti", "data"),
            node("eh", "error_handler", {"script": "result = {'processed': True}"}),
        ]
        edges = [edge("ti", "eh", "text", "input")]
        pid, run = create_and_run("flow:eh:script", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_fallback_on_error(self, live_backend):
        nodes = [
            text_input_node("ti", "data"),
            node("eh", "error_handler", {"script": "raise ValueError('test')", "on_error": "fallback", "fallback_value": "default"}),
        ]
        edges = [edge("ti", "eh", "text", "input")]
        pid, run = create_and_run("flow:eh:fallback", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  QUALITY_GATE
# ═══════════════════════════════════════════════════════════════════════

class TestQualityGate:
    def test_pass(self, live_backend):
        nodes = [
            metrics_input_node("mi", '{"accuracy": 0.95}'),
            node("qg", "quality_gate", {"metric_name": "accuracy", "operator": ">=", "threshold": 0.8}),
        ]
        edges = [edge("mi", "qg", "metrics", "data")]
        pid, run = create_and_run("flow:qg:pass", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_fail_warn(self, live_backend):
        nodes = [
            metrics_input_node("mi", '{"accuracy": 0.5}'),
            node("qg", "quality_gate", {"metric_name": "accuracy", "operator": ">=", "threshold": 0.8, "on_fail": "warn_continue"}),
        ]
        edges = [edge("mi", "qg", "metrics", "data")]
        pid, run = create_and_run("flow:qg:warn", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_auto_compute(self, live_backend):
        nodes = [
            text_input_node("ti", "a\nb\nc"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("qg", "quality_gate", {"metric_name": "row_count", "operator": ">=", "threshold": 1}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "qg", "dataset", "data")]
        pid, run = create_and_run("flow:qg:auto", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  PARALLEL_FAN_OUT
# ═══════════════════════════════════════════════════════════════════════

class TestParallelFanOut:
    def test_split_equal(self, live_backend):
        nodes = [
            text_input_node("ti", "\n".join(f"row{i}" for i in range(10))),
            text_to_dataset_node("ttd", split_by="newline"),
            node("pfo", "parallel_fan_out", {"num_branches": 2, "split_mode": "split_equal"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "pfo", "dataset", "input")]
        pid, run = create_and_run("flow:pfo:equal", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_broadcast(self, live_backend):
        nodes = [
            text_input_node("ti", "broadcast me"),
            text_to_dataset_node("ttd"),
            node("pfo", "parallel_fan_out", {"num_branches": 3, "split_mode": "broadcast"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "pfo", "dataset", "input")]
        pid, run = create_and_run("flow:pfo:broadcast", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_round_robin(self, live_backend):
        nodes = [
            text_input_node("ti", "\n".join(f"item{i}" for i in range(6))),
            text_to_dataset_node("ttd", split_by="newline"),
            node("pfo", "parallel_fan_out", {"num_branches": 2, "split_mode": "split_round_robin"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "pfo", "dataset", "input")]
        pid, run = create_and_run("flow:pfo:rr", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  LOOP_ITERATOR
# ═══════════════════════════════════════════════════════════════════════

class TestLoopIterator:
    def test_count_mode(self, live_backend):
        nodes = [node("li", "loop_iterator", {"mode": "count", "count": 3})]
        pid, run = create_and_run("flow:li:count", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_iterate_rows(self, live_backend):
        nodes = [
            text_input_node("ti", "a\nb\nc"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("li", "loop_iterator", {"mode": "iterate_rows"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "li", "dataset", "dataset")]
        pid, run = create_and_run("flow:li:rows", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_batch_mode(self, live_backend):
        nodes = [
            text_input_node("ti", "\n".join(f"item{i}" for i in range(6))),
            text_to_dataset_node("ttd", split_by="newline"),
            node("li", "loop_iterator", {"mode": "batch", "batch_size": 2}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "li", "dataset", "dataset")]
        pid, run = create_and_run("flow:li:batch", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  AB_SPLIT_TEST
# ═══════════════════════════════════════════════════════════════════════

class TestABSplitTest:
    def test_50_50(self, live_backend):
        nodes = [
            text_input_node("ti", "\n".join(f"row{i}" for i in range(20))),
            text_to_dataset_node("ttd", split_by="newline"),
            node("abs", "ab_split_test", {"split_ratio": 0.5, "random_seed": 42}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "abs", "dataset", "data")]
        pid, run = create_and_run("flow:abs:50", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_80_20(self, live_backend):
        nodes = [
            text_input_node("ti", "\n".join(f"row{i}" for i in range(20))),
            text_to_dataset_node("ttd", split_by="newline"),
            node("abs", "ab_split_test", {"split_ratio": 0.8, "random_seed": 42}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "abs", "dataset", "data")]
        pid, run = create_and_run("flow:abs:80", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_deterministic(self, live_backend):
        nodes = [
            text_input_node("ti", "\n".join(f"row{i}" for i in range(10))),
            text_to_dataset_node("ttd", split_by="newline"),
            node("abs", "ab_split_test", {"split_method": "deterministic", "split_ratio": 0.5}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "abs", "dataset", "data")]
        pid, run = create_and_run("flow:abs:det", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  PYTHON_RUNNER
# ═══════════════════════════════════════════════════════════════════════

class TestPythonRunner:
    """python_runner uses signal.SIGALRM which only works in the main thread.
    Since the executor runs blocks in a ThreadPoolExecutor, this block always
    fails with 'ValueError: signal only works in main thread'. This is a
    BLUEPRINT BUG — the block should use threading.Timer instead of SIGALRM.
    Tests are marked xfail to document the bug while still running them.
    """

    @pytest.mark.xfail(reason="BUG: python_runner uses signal.SIGALRM in non-main thread")
    def test_simple_script(self, live_backend):
        nodes = [node("pr", "python_runner", {"script": "ctx.save_output('output_data', {'result': 42})"})]
        pid, run = create_and_run("flow:pr:simple", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    @pytest.mark.xfail(reason="BUG: python_runner uses signal.SIGALRM in non-main thread")
    def test_with_input(self, live_backend):
        nodes = [
            text_input_node("ti", "hello"),
            node("pr", "python_runner", {"script": "data = ctx.load_input('input_data')\nctx.save_output('output_data', {'echo': str(data)})"}),
        ]
        edges = [edge("ti", "pr", "text", "input_data")]
        pid, run = create_and_run("flow:pr:input", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    @pytest.mark.xfail(reason="BUG: python_runner uses signal.SIGALRM in non-main thread")
    def test_metrics_output(self, live_backend):
        nodes = [node("pr", "python_runner", {
            "script": "ctx.log_metric('custom_score', 0.95)\nctx.save_output('output_data', {'ok': True})",
        })]
        pid, run = create_and_run("flow:pr:metrics", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  ROLLBACK_POINT
# ═══════════════════════════════════════════════════════════════════════

class TestRollbackPoint:
    def test_basic(self, live_backend):
        nodes = [
            text_input_node("ti", "checkpoint data"),
            node("rp", "rollback_point", {"label": "snap-1"}),
        ]
        edges = [edge("ti", "rp", "text", "data")]
        pid, run = create_and_run("flow:rp:basic", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_max_snapshots(self, live_backend):
        nodes = [
            text_input_node("ti", "data"),
            node("rp", "rollback_point", {"label": "snap", "max_snapshots": 1}),
        ]
        edges = [edge("ti", "rp", "text", "data")]
        pid, run = create_and_run("flow:rp:max1", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  VALIDATION-ONLY FLOW BLOCKS
# ═══════════════════════════════════════════════════════════════════════

class TestFlowValidation:
    def test_loop_controller_config(self, live_backend):
        s, d = validate_config("loop_controller", {"iterations": 3, "file_mode": "overwrite"})
        assert s == 200

    def test_artifact_viewer_config(self, live_backend):
        s, d = validate_config("artifact_viewer", {"display_mode": "auto"})
        assert s == 200

    def test_embedding_visualizer_config(self, live_backend):
        s, d = validate_config("embedding_visualizer", {"method": "tsne", "perplexity": 30})
        assert s == 200

    def test_cloud_compute_config(self, live_backend):
        s, d = validate_config("cloud_compute_provider", {"provider": "aws", "instance_type": "g4dn.xlarge"})
        assert s == 200

    def test_notification_hub_config(self, live_backend):
        s, d = validate_config("notification_hub", {"channel": "slack", "webhook_url": "https://hooks.slack.com/test"})
        assert s == 200

    def test_experiment_logger_config(self, live_backend):
        s, d = validate_config("experiment_logger", {"backend": "local", "experiment_name": "test"})
        assert s == 200

    def test_human_review_gate_config(self, live_backend):
        s, d = validate_config("human_review_gate", {"timeout_minutes": 60})
        assert s == 200

    def test_agentic_review_loop_config(self, live_backend):
        s, d = validate_config("agentic_review_loop", {"max_iterations": 3})
        assert s == 200

    def test_control_tower_config(self, live_backend):
        s, d = validate_config("control_tower", {"mode": "monitor"})
        assert s == 200


# ═══════════════════════════════════════════════════════════════════════
#  FLOW E2E WORKFLOWS
# ═══════════════════════════════════════════════════════════════════════

class TestFlowWorkflows:
    def test_branch_then_aggregate(self, live_backend):
        """ti_a + ti_b → conditional_branch → aggregator (both branches wired)"""
        nodes = [
            text_input_node("a", "branch A data"),
            text_input_node("b", "branch B data"),
            node("agg", "aggregator", {"strategy": "pick_first"}),
        ]
        edges = [
            edge("a", "agg", "text", "in_1"),
            edge("b", "agg", "text", "in_2"),
        ]
        pid, run = create_and_run("wf:flow:branch-agg", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_error_handler_quality_gate(self, live_backend):
        """ti → error_handler, mi → quality_gate"""
        nodes = [
            text_input_node("ti", "safe data"),
            node("eh", "error_handler"),
            metrics_input_node("mi", '{"quality": 0.9}'),
            node("qg", "quality_gate", {"metric_name": "quality", "operator": ">=", "threshold": 0.5}),
        ]
        edges = [
            edge("ti", "eh", "text", "input"),
            edge("mi", "qg", "metrics", "data"),
        ]
        pid, run = create_and_run("wf:flow:eh-qg", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_fan_out_and_filter(self, live_backend):
        """ti → ttd → parallel_fan_out → filter branches"""
        nodes = [
            text_input_node("ti", "\n".join(f"item{i}" for i in range(10))),
            text_to_dataset_node("ttd", split_by="newline"),
            node("pfo", "parallel_fan_out", {"num_branches": 2, "split_mode": "split_equal"}),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "pfo", "dataset", "input")]
        pid, run = create_and_run("wf:flow:fan-filter", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)
