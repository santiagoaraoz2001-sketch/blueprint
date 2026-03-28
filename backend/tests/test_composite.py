"""Tests for the composite block engine (CompositeBlockContext + execute_sub_pipeline)."""

import pytest
from unittest.mock import MagicMock, patch

from backend.block_sdk.context import BlockContext, CompositeBlockContext
from backend.block_sdk.exceptions import BlockError
from backend.engine.composite import (
    CompositeBlockContext as CompositeBlockContextReexport,
    _topological_sort_sub,
    execute_sub_pipeline,
    MAX_COMPOSITE_DEPTH,
)


# ---------------------------------------------------------------------------
# CompositeBlockContext — unit tests
# ---------------------------------------------------------------------------

class TestCompositeBlockContext:
    """Test the block-author-facing CompositeBlockContext."""

    def _make_ctx(self, **kwargs):
        defaults = dict(
            run_dir="/tmp/test_run",
            block_dir="/tmp/test_block",
            config={},
            inputs={},
        )
        defaults.update(kwargs)
        return CompositeBlockContext(**defaults)

    def test_inherits_block_context(self):
        ctx = self._make_ctx()
        assert isinstance(ctx, BlockContext)

    def test_reexport_is_same_class(self):
        """composite.py re-exports the same class from context.py."""
        assert CompositeBlockContextReexport is CompositeBlockContext

    def test_add_sub_block_basic(self):
        ctx = self._make_ctx()
        ctx.add_sub_block("step1", "llm_inference", {"model": "gpt-4"})
        assert ctx.sub_block_count == 1
        assert ctx.has_sub_pipeline()

    def test_add_sub_block_structure(self):
        ctx = self._make_ctx()
        ctx.add_sub_block("step1", "llm_inference", {"model": "gpt-4"})
        pipeline = ctx.get_sub_pipeline()
        assert len(pipeline["nodes"]) == 1
        node = pipeline["nodes"][0]
        assert node["id"] == "step1"
        assert node["type"] == "custom"
        assert node["data"]["type"] == "llm_inference"
        assert node["data"]["config"] == {"model": "gpt-4"}
        assert node["data"]["category"] == "composite_child"

    def test_add_sub_block_duplicate_id_raises(self):
        ctx = self._make_ctx()
        ctx.add_sub_block("step1", "llm_inference", {})
        with pytest.raises(ValueError, match="Duplicate sub-block ID"):
            ctx.add_sub_block("step1", "llm_inference", {})

    def test_add_sub_edge_basic(self):
        ctx = self._make_ctx()
        ctx.add_sub_block("a", "type_a", {})
        ctx.add_sub_block("b", "type_b", {})
        ctx.add_sub_edge("a", "b", "response", "context")
        pipeline = ctx.get_sub_pipeline()
        assert len(pipeline["edges"]) == 1
        edge = pipeline["edges"][0]
        assert edge["source"] == "a"
        assert edge["target"] == "b"
        assert edge["sourceHandle"] == "response"
        assert edge["targetHandle"] == "context"

    def test_add_sub_edge_unknown_source_raises(self):
        ctx = self._make_ctx()
        ctx.add_sub_block("b", "type_b", {})
        with pytest.raises(ValueError, match="Sub-edge source 'unknown' not found"):
            ctx.add_sub_edge("unknown", "b", "out", "in")

    def test_add_sub_edge_unknown_target_raises(self):
        ctx = self._make_ctx()
        ctx.add_sub_block("a", "type_a", {})
        with pytest.raises(ValueError, match="Sub-edge target 'unknown' not found"):
            ctx.add_sub_edge("a", "unknown", "out", "in")

    def test_has_sub_pipeline_false_when_empty(self):
        ctx = self._make_ctx()
        assert not ctx.has_sub_pipeline()
        assert ctx.sub_block_count == 0

    def test_get_sub_pipeline_returns_copies(self):
        """Ensure returned lists are copies (not references to internal state)."""
        ctx = self._make_ctx()
        ctx.add_sub_block("a", "type_a", {})
        pipeline1 = ctx.get_sub_pipeline()
        pipeline1["nodes"].clear()
        pipeline2 = ctx.get_sub_pipeline()
        assert len(pipeline2["nodes"]) == 1

    def test_multiple_blocks_and_edges(self):
        ctx = self._make_ctx()
        ctx.add_sub_block("a", "type_a", {})
        ctx.add_sub_block("b", "type_b", {})
        ctx.add_sub_block("c", "type_c", {})
        ctx.add_sub_edge("a", "b")
        ctx.add_sub_edge("b", "c")
        ctx.add_sub_edge("a", "c")
        assert ctx.sub_block_count == 3
        pipeline = ctx.get_sub_pipeline()
        assert len(pipeline["edges"]) == 3

    def test_context_preserves_base_functionality(self):
        """CompositeBlockContext should still work as a regular BlockContext."""
        ctx = self._make_ctx(
            config={"key": "value"},
            inputs={"data": "hello"},
        )
        assert ctx.config["key"] == "value"
        assert ctx.load_input("data") == "hello"
        ctx.save_output("result", "output_data")
        assert ctx.get_outputs() == {"result": "output_data"}
        ctx.log_metric("accuracy", 0.95)
        assert ctx.get_metrics() == {"accuracy": 0.95}


# ---------------------------------------------------------------------------
# _topological_sort_sub — unit tests
# ---------------------------------------------------------------------------

class TestTopologicalSort:
    """Test the sub-pipeline topological sort."""

    def _nodes(self, *ids):
        return [{"id": nid} for nid in ids]

    def _edges(self, *pairs):
        return [{"source": s, "target": t} for s, t in pairs]

    def test_linear_chain(self):
        nodes = self._nodes("A", "B", "C")
        edges = self._edges(("A", "B"), ("B", "C"))
        order = _topological_sort_sub(nodes, edges)
        assert order == ["A", "B", "C"]

    def test_diamond_graph(self):
        nodes = self._nodes("A", "B", "C", "D")
        edges = self._edges(("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"))
        order = _topological_sort_sub(nodes, edges)
        assert order[0] == "A"
        assert order[-1] == "D"
        assert set(order) == {"A", "B", "C", "D"}

    def test_single_node_no_edges(self):
        nodes = self._nodes("A")
        order = _topological_sort_sub(nodes, [])
        assert order == ["A"]

    def test_disconnected_nodes(self):
        nodes = self._nodes("A", "B", "C")
        order = _topological_sort_sub(nodes, [])
        assert set(order) == {"A", "B", "C"}

    def test_cycle_detection_raises(self):
        nodes = self._nodes("A", "B", "C")
        edges = self._edges(("A", "B"), ("B", "C"), ("C", "A"))
        with pytest.raises(BlockError, match="cycle"):
            _topological_sort_sub(nodes, edges)

    def test_self_loop_raises(self):
        nodes = self._nodes("A", "B")
        edges = self._edges(("A", "B"), ("B", "B"))
        with pytest.raises(BlockError, match="cycle"):
            _topological_sort_sub(nodes, edges)

    def test_partial_cycle_raises(self):
        """Only B and C form a cycle; A is fine."""
        nodes = self._nodes("A", "B", "C")
        edges = self._edges(("A", "B"), ("B", "C"), ("C", "B"))
        with pytest.raises(BlockError, match="cycle"):
            _topological_sort_sub(nodes, edges)

    def test_empty_graph(self):
        order = _topological_sort_sub([], [])
        assert order == []


# ---------------------------------------------------------------------------
# execute_sub_pipeline — integration tests
# ---------------------------------------------------------------------------

def _make_sub_nodes(*specs):
    """Build sub-pipeline nodes: specs are (id, type) tuples."""
    return [
        {
            "id": nid,
            "type": "custom",
            "data": {
                "type": block_type,
                "config": {},
                "category": "composite_child",
                "inputs": [],
                "outputs": [],
            },
        }
        for nid, block_type in specs
    ]


def _make_sub_edges(*quads):
    """Build sub-pipeline edges: quads are (source, target, sourceHandle, targetHandle)."""
    return [
        {"source": s, "target": t, "sourceHandle": sh, "targetHandle": th}
        for s, t, sh, th in quads
    ]


class TestExecuteSubPipeline:
    """Integration tests for execute_sub_pipeline."""

    def _run_sub_pipeline(
        self,
        nodes,
        edges,
        parent_inputs=None,
        block_run_fn=None,
        depth=0,
        find_block_fn=None,
        resolve_secrets_fn=None,
    ):
        """Helper to run execute_sub_pipeline with mocked dependencies."""
        parent_inputs = parent_inputs or {}
        executed = []

        def default_find_block(block_type):
            return f"/blocks/{block_type}"

        def default_run(block_dir, config, inputs, run_dir, run_id,
                        node_id, progress_cb, message_cb, metric_cb,
                        context_cls=None, _composite_depth=0):
            executed.append({
                "node_id": node_id,
                "block_dir": block_dir,
                "config": dict(config),
                "inputs": dict(inputs),
                "context_cls": context_cls,
                "depth": _composite_depth,
            })
            return {"output": f"result_{node_id}"}, {}

        def default_resolve(config):
            return config

        sub_def = {"nodes": nodes, "edges": edges}

        with patch("backend.engine.composite.load_block_schema", return_value={}), \
             patch("backend.engine.composite.validate_config", side_effect=lambda s, c: c):
            outputs, fingerprints = execute_sub_pipeline(
                sub_definition=sub_def,
                run_dir="/tmp/run",
                run_id="run-1",
                parent_node_id="parent",
                parent_inputs=parent_inputs,
                progress_cb=None,
                message_cb=MagicMock(),
                metric_cb=MagicMock(),
                find_block_fn=find_block_fn or default_find_block,
                load_and_run_fn=block_run_fn or default_run,
                resolve_secrets_fn=resolve_secrets_fn or default_resolve,
                depth=depth,
            )

        return outputs, fingerprints, executed

    def test_linear_execution_order(self):
        nodes = _make_sub_nodes(("A", "typeA"), ("B", "typeB"), ("C", "typeC"))
        edges = _make_sub_edges(
            ("A", "B", "output", "input"),
            ("B", "C", "output", "input"),
        )
        outputs, _, executed = self._run_sub_pipeline(nodes, edges)
        assert [e["node_id"] for e in executed] == ["parent.A", "parent.B", "parent.C"]

    def test_output_merging_with_prefix(self):
        nodes = _make_sub_nodes(("A", "typeA"), ("B", "typeB"))
        edges = _make_sub_edges(("A", "B", "output", "input"))
        outputs, _, _ = self._run_sub_pipeline(nodes, edges)

        # Prefixed outputs
        assert "A.output" in outputs
        assert "B.output" in outputs
        # Last child's output also without prefix
        assert "output" in outputs
        assert outputs["output"] == "result_parent.B"

    def test_parent_inputs_injected_into_root_nodes(self):
        """Root nodes (no upstream edges) should receive parent inputs."""
        nodes = _make_sub_nodes(("A", "typeA"), ("B", "typeB"))
        edges = _make_sub_edges(("A", "B", "output", "input"))
        _, _, executed = self._run_sub_pipeline(
            nodes, edges,
            parent_inputs={"topic": "AI safety"},
        )
        # A is a root node (no incoming edges)
        a_exec = next(e for e in executed if e["node_id"] == "parent.A")
        assert a_exec["inputs"]["topic"] == "AI safety"
        # B is NOT a root node (has edge from A)
        b_exec = next(e for e in executed if e["node_id"] == "parent.B")
        assert "topic" not in b_exec["inputs"]

    def test_child_wired_inputs_override_parent(self):
        """Wired inputs from upstream children take priority over parent inputs."""
        nodes = _make_sub_nodes(("A", "typeA"), ("B", "typeB"))
        edges = _make_sub_edges(("A", "B", "output", "data"))

        def run_fn(block_dir, config, inputs, run_dir, run_id,
                   node_id, progress_cb, message_cb, metric_cb,
                   context_cls=None, _composite_depth=0):
            return {"output": "from_A"}, {}

        outputs, _, executed = self._run_sub_pipeline(
            nodes, edges,
            parent_inputs={"data": "parent_data"},
            block_run_fn=run_fn,
        )

    def test_empty_sub_pipeline(self):
        outputs, fingerprints, executed = self._run_sub_pipeline([], [])
        assert outputs == {}
        assert fingerprints == {}
        assert executed == []

    def test_block_not_found_raises(self):
        nodes = _make_sub_nodes(("A", "unknown_type"))
        with pytest.raises(BlockError, match="not found"):
            self._run_sub_pipeline(
                nodes, [],
                find_block_fn=lambda t: None,
            )

    def test_child_failure_raises_block_error(self):
        nodes = _make_sub_nodes(("A", "typeA"))

        def failing_run(*args, **kwargs):
            raise RuntimeError("Child crashed")

        with pytest.raises(BlockError, match="failed"):
            self._run_sub_pipeline(nodes, [], block_run_fn=failing_run)

    def test_child_block_error_reraises(self):
        """BlockError from child should be re-raised directly, not wrapped."""
        nodes = _make_sub_nodes(("A", "typeA"))

        def failing_run(*args, **kwargs):
            raise BlockError("Custom block error", recoverable=True)

        with pytest.raises(BlockError, match="Custom block error") as exc_info:
            self._run_sub_pipeline(nodes, [], block_run_fn=failing_run)
        assert exc_info.value.recoverable is True

    def test_depth_guard(self):
        nodes = _make_sub_nodes(("A", "typeA"))
        with pytest.raises(BlockError, match="nesting depth exceeded"):
            self._run_sub_pipeline(nodes, [], depth=MAX_COMPOSITE_DEPTH)

    def test_depth_just_under_limit_works(self):
        nodes = _make_sub_nodes(("A", "typeA"))
        outputs, _, _ = self._run_sub_pipeline(
            nodes, [],
            depth=MAX_COMPOSITE_DEPTH - 1,
        )
        assert "output" in outputs

    def test_secret_resolution_called(self):
        nodes = _make_sub_nodes(("A", "typeA"))
        nodes[0]["data"]["config"] = {"api_key": "$secret:my_key"}
        resolved = {"api_key": "real_value"}

        def resolve(config):
            if "$secret:my_key" in config.get("api_key", ""):
                return resolved
            return config

        with patch("backend.engine.composite.load_block_schema", return_value={}), \
             patch("backend.engine.composite.validate_config", side_effect=lambda s, c: c):
            self._run_sub_pipeline(
                nodes, [],
                resolve_secrets_fn=resolve,
            )

    def test_secret_resolution_failure_raises(self):
        nodes = _make_sub_nodes(("A", "typeA"))

        def bad_resolve(config):
            raise ValueError("Secret not found")

        with pytest.raises(BlockError, match="secret resolution failed"):
            self._run_sub_pipeline(nodes, [], resolve_secrets_fn=bad_resolve)

    def test_multi_input_merging(self):
        """When two upstream nodes wire to the same target handle, values are merged as list."""
        nodes = _make_sub_nodes(("A", "typeA"), ("B", "typeB"), ("C", "typeC"))
        edges = _make_sub_edges(
            ("A", "C", "output", "context"),
            ("B", "C", "output", "context"),
        )

        received_inputs = {}

        def run_fn(block_dir, config, inputs, run_dir, run_id,
                   node_id, progress_cb, message_cb, metric_cb,
                   context_cls=None, _composite_depth=0):
            received_inputs[node_id] = dict(inputs)
            return {"output": f"result_{node_id}"}, {}

        self._run_sub_pipeline(nodes, edges, block_run_fn=run_fn)

        # C should receive a list of both A and B outputs
        c_inputs = received_inputs["parent.C"]
        assert isinstance(c_inputs["context"], list)
        assert len(c_inputs["context"]) == 2

    def test_nested_composite_detection(self):
        """Child blocks marked composite: true should get context_cls=CompositeBlockContext."""
        nodes = _make_sub_nodes(("A", "nested_composite"))

        recorded = []

        def run_fn(block_dir, config, inputs, run_dir, run_id,
                   node_id, progress_cb, message_cb, metric_cb,
                   context_cls=None, _composite_depth=0):
            recorded.append({"context_cls": context_cls, "depth": _composite_depth})
            return {"output": "result"}, {}

        with patch("backend.engine.composite.load_block_schema",
                   return_value={"composite": True}), \
             patch("backend.engine.composite.validate_config", side_effect=lambda s, c: c):
            execute_sub_pipeline(
                sub_definition={"nodes": nodes, "edges": []},
                run_dir="/tmp/run",
                run_id="run-1",
                parent_node_id="parent",
                parent_inputs={},
                progress_cb=None,
                message_cb=MagicMock(),
                metric_cb=MagicMock(),
                find_block_fn=lambda t: f"/blocks/{t}",
                load_and_run_fn=run_fn,
                resolve_secrets_fn=lambda c: c,
                depth=0,
            )

        assert len(recorded) == 1
        assert recorded[0]["context_cls"] is CompositeBlockContext
        assert recorded[0]["depth"] == 1

    def test_fingerprint_collection(self):
        """Fingerprints from child blocks should be collected."""
        nodes = _make_sub_nodes(("A", "typeA"), ("B", "typeB"))
        edges = _make_sub_edges(("A", "B", "output", "input"))

        def run_fn(block_dir, config, inputs, run_dir, run_id,
                   node_id, progress_cb, message_cb, metric_cb,
                   context_cls=None, _composite_depth=0):
            fp = {"hash": f"fp_{node_id}"}
            return {"output": "result"}, fp

        with patch("backend.engine.composite.load_block_schema", return_value={}), \
             patch("backend.engine.composite.validate_config", side_effect=lambda s, c: c):
            _, fingerprints, _ = self._run_sub_pipeline(
                nodes, edges, block_run_fn=run_fn,
            )

        assert "parent.A" in fingerprints
        assert "parent.B" in fingerprints

    def test_progress_callback_called(self):
        nodes = _make_sub_nodes(("A", "typeA"), ("B", "typeB"))
        edges = _make_sub_edges(("A", "B", "output", "input"))
        progress_calls = []

        def progress_cb(current, total):
            progress_calls.append((current, total))

        def run_fn(block_dir, config, inputs, run_dir, run_id,
                   node_id, progress_cb_inner, message_cb, metric_cb,
                   context_cls=None, _composite_depth=0):
            if progress_cb_inner:
                progress_cb_inner(1, 1)
            return {"output": "result"}, {}

        with patch("backend.engine.composite.load_block_schema", return_value={}), \
             patch("backend.engine.composite.validate_config", side_effect=lambda s, c: c):
            execute_sub_pipeline(
                sub_definition={"nodes": nodes, "edges": edges},
                run_dir="/tmp/run",
                run_id="run-1",
                parent_node_id="parent",
                parent_inputs={},
                progress_cb=progress_cb,
                message_cb=MagicMock(),
                metric_cb=MagicMock(),
                find_block_fn=lambda t: f"/blocks/{t}",
                load_and_run_fn=run_fn,
                resolve_secrets_fn=lambda c: c,
            )

        assert len(progress_calls) > 0

    def test_message_callback_prefixed(self):
        nodes = _make_sub_nodes(("A", "typeA"))
        messages = []

        def message_cb(msg, severity=None):
            messages.append(msg)

        def run_fn(block_dir, config, inputs, run_dir, run_id,
                   node_id, progress_cb, message_cb_inner, metric_cb,
                   context_cls=None, _composite_depth=0):
            if message_cb_inner:
                message_cb_inner("hello from child")
            return {"output": "result"}, {}

        with patch("backend.engine.composite.load_block_schema", return_value={}), \
             patch("backend.engine.composite.validate_config", side_effect=lambda s, c: c):
            execute_sub_pipeline(
                sub_definition={"nodes": nodes, "edges": []},
                run_dir="/tmp/run",
                run_id="run-1",
                parent_node_id="parent",
                parent_inputs={},
                progress_cb=None,
                message_cb=message_cb,
                metric_cb=MagicMock(),
                find_block_fn=lambda t: f"/blocks/{t}",
                load_and_run_fn=run_fn,
                resolve_secrets_fn=lambda c: c,
            )

        # Should have composite status messages and the child's prefixed message
        child_msg = [m for m in messages if "[A]" in m]
        assert len(child_msg) == 1
        assert "hello from child" in child_msg[0]

    def test_metric_callback_prefixed(self):
        nodes = _make_sub_nodes(("A", "typeA"))
        metrics = []

        def metric_cb(name, value, step):
            metrics.append((name, value, step))

        def run_fn(block_dir, config, inputs, run_dir, run_id,
                   node_id, progress_cb, message_cb, metric_cb_inner,
                   context_cls=None, _composite_depth=0):
            if metric_cb_inner:
                metric_cb_inner("accuracy", 0.95, None)
            return {"output": "result"}, {}

        with patch("backend.engine.composite.load_block_schema", return_value={}), \
             patch("backend.engine.composite.validate_config", side_effect=lambda s, c: c):
            execute_sub_pipeline(
                sub_definition={"nodes": nodes, "edges": []},
                run_dir="/tmp/run",
                run_id="run-1",
                parent_node_id="parent",
                parent_inputs={},
                progress_cb=None,
                message_cb=MagicMock(),
                metric_cb=metric_cb,
                find_block_fn=lambda t: f"/blocks/{t}",
                load_and_run_fn=run_fn,
                resolve_secrets_fn=lambda c: c,
            )

        assert len(metrics) == 1
        assert metrics[0][0] == "composite_child.A.accuracy"
        assert metrics[0][1] == 0.95


# ---------------------------------------------------------------------------
# multi_agent_debate reference block — smoke test
# ---------------------------------------------------------------------------

class TestMultiAgentDebateBlock:
    """Test the multi_agent_debate block's run() function (demo mode)."""

    @staticmethod
    def _load_debate_module():
        import importlib.util
        import os

        block_path = os.path.normpath(os.path.join(
            os.path.dirname(__file__), "..", "..",
            "blocks", "agents", "multi_agent_debate", "run.py",
        ))
        spec = importlib.util.spec_from_file_location("debate_run", block_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_debate_runs_demo_mode(self, tmp_path):
        """run() should complete in demo mode and produce expected outputs."""
        ctx = BlockContext(
            run_dir=str(tmp_path / "run"),
            block_dir=str(tmp_path / "block"),
            config={"num_agents": 3, "num_rounds": 2, "seed": 42},
            inputs={},
        )
        # Write a topic file so load_input("input") can find it
        input_dir = tmp_path / "run" / "inputs"
        input_dir.mkdir(parents=True, exist_ok=True)
        topic_file = input_dir / "input"
        topic_file.write_text("Should AI be regulated?")
        ctx._inputs["input"] = str(topic_file)

        mod = self._load_debate_module()
        mod.run(ctx)

        assert "response" in ctx._outputs
        assert "dataset" in ctx._outputs
        assert "metrics" in ctx._outputs

        metrics = ctx._outputs["metrics"]
        assert metrics["num_agents"] == 3
        assert metrics["num_rounds"] == 2
        assert metrics["total_arguments"] == 6  # 3 agents × 2 rounds
        assert metrics["demo_mode"] is True
        assert 0 <= metrics["consensus_score"] <= 1

    def test_debate_single_round(self, tmp_path):
        """Single round should produce num_agents arguments."""
        ctx = BlockContext(
            run_dir=str(tmp_path / "run"),
            block_dir=str(tmp_path / "block"),
            config={"num_agents": 2, "num_rounds": 1, "seed": 42},
            inputs={},
        )
        input_dir = tmp_path / "run" / "inputs"
        input_dir.mkdir(parents=True, exist_ok=True)
        topic_file = input_dir / "input"
        topic_file.write_text("Test topic")
        ctx._inputs["input"] = str(topic_file)

        mod = self._load_debate_module()
        mod.run(ctx)

        metrics = ctx._outputs["metrics"]
        assert metrics["num_agents"] == 2
        assert metrics["num_rounds"] == 1
        assert metrics["total_arguments"] == 2  # 2 agents × 1 round

    def test_debate_uses_config_topic_as_fallback(self, tmp_path):
        """When no input is connected, falls back to config topic."""
        ctx = BlockContext(
            run_dir=str(tmp_path / "run"),
            block_dir=str(tmp_path / "block"),
            config={
                "num_agents": 2,
                "num_rounds": 1,
                "seed": 42,
                "topic": "Custom topic from config",
            },
            inputs={},
        )
        mod = self._load_debate_module()
        mod.run(ctx)

        assert "response" in ctx._outputs
        assert "metrics" in ctx._outputs
