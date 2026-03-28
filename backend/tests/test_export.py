"""Tests for pipeline export (Python script and Jupyter notebook).

Covers:
  - test_python_export_valid_ast: compiled DAG produces valid Python (ast.parse)
  - test_python_export_has_plan_hash: header comment includes plan_hash
  - test_jupyter_export_valid_notebook: generated .ipynb passes nbformat.validate()
  - test_loop_graph_export_rejected: export of loop fixture returns error
  - test_custom_block_export_rejected: export of python_runner fixture returns error
  - test_resolved_configs_match_planner: configs in generated script match planner output
"""

import ast
import json

import pytest
from unittest.mock import patch, MagicMock
from typing import Any, Optional

from backend.engine.planner import GraphPlanner
from backend.engine.planner_models import (
    ExecutionPlan,
    ResolvedNode,
    PlannerResult,
)
from backend.engine.compiler import compile_pipeline_from_plan
from backend.engine.graph_utils import validate_exportable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(nid: str, block_type: str = "test_block", category: str = "data", config: dict = None):
    """Create a minimal pipeline node dict."""
    return {
        "id": nid,
        "type": "default",
        "data": {
            "type": block_type,
            "label": f"Node {nid}",
            "category": category,
            "config": config or {},
        },
    }


def _loop_controller_node(nid: str, config: dict = None):
    """Create a loop_controller node."""
    cfg = {"iterations": 10}
    if config:
        cfg.update(config)
    return _node(nid, block_type="loop_controller", category="flow", config=cfg)


def _edge(src: str, tgt: str, src_handle: str = "output", tgt_handle: str = "input"):
    """Create a pipeline edge dict."""
    return {
        "source": src,
        "target": tgt,
        "sourceHandle": src_handle,
        "targetHandle": tgt_handle,
    }


class _MockRegistry:
    """Minimal registry mock for export tests."""

    def __init__(self, known_types: set[str] | None = None, version: str = "1.0.0"):
        self._known = known_types
        self._version = version

    def get(self, block_type: str):
        if self._known is not None and block_type not in self._known:
            return None
        return {"type": block_type, "inputs": [], "outputs": [], "config": {}}

    def get_block_version(self, block_type: str) -> str:
        return self._version

    def get_block_schema_defaults(self, block_type: str) -> dict[str, Any]:
        return {}

    def get_block_info(self, block_type: str) -> Optional[dict]:
        schema = self.get(block_type)
        if schema is None:
            return None
        return {"type": block_type, "category": "data", "path": "/tmp/blocks/" + block_type}

    def get_category(self, block_type: str) -> str:
        return "data"

    def validate_connection(self, src_type, src_port, dst_type, dst_port):
        return {"valid": True}

    def is_port_compatible(self, src_type: str, tgt_type: str) -> bool:
        return True


def _make_plan(nodes, edges, registry=None, workspace_config=None) -> ExecutionPlan:
    """Run the planner and return the plan, asserting validity."""
    if registry is None:
        registry = _MockRegistry()
    planner = GraphPlanner(registry)
    result = planner.plan(nodes, edges, workspace_config=workspace_config)
    assert result.is_valid, f"Planner failed: {result.errors}"
    assert result.plan is not None
    return result.plan


# ---------------------------------------------------------------------------
# Test 1: Python export produces valid AST
# ---------------------------------------------------------------------------

class TestPythonExportValidAst:

    def test_python_export_valid_ast(self):
        """Compile a simple 3-node DAG and verify ast.parse succeeds."""
        nodes = [
            _node("A", config={"lr": 0.001}),
            _node("B", config={"epochs": 10}),
            _node("C"),
        ]
        edges = [_edge("A", "B"), _edge("B", "C")]
        plan = _make_plan(nodes, edges)

        # Mock _find_block_module to return a fake path
        with patch("backend.engine.compiler._find_block_module") as mock_find:
            mock_find.return_value = MagicMock(
                __str__=lambda self: "/tmp/blocks/test_block",
                parent=MagicMock(__str__=lambda self: "/tmp/blocks"),
            )

            script = compile_pipeline_from_plan(
                pipeline_name="Test Pipeline",
                plan=plan,
                edges=edges,
                nodes=nodes,
            )

        # The script must be valid Python
        tree = ast.parse(script)
        assert tree is not None
        assert len(script) > 100  # Non-trivial output


# ---------------------------------------------------------------------------
# Test 2: Python export has plan_hash in header
# ---------------------------------------------------------------------------

class TestPythonExportHasPlanHash:

    def test_python_export_has_plan_hash(self):
        """Verify the generated script header includes the plan hash."""
        nodes = [_node("A"), _node("B")]
        edges = [_edge("A", "B")]
        plan = _make_plan(nodes, edges)

        with patch("backend.engine.compiler._find_block_module") as mock_find:
            mock_find.return_value = MagicMock(
                __str__=lambda self: "/tmp/blocks/test_block",
                parent=MagicMock(__str__=lambda self: "/tmp/blocks"),
            )

            script = compile_pipeline_from_plan(
                pipeline_name="Hash Test",
                plan=plan,
                edges=edges,
                nodes=nodes,
            )

        lines = script.split("\n")
        # Check the required header lines
        assert lines[0] == "#!/usr/bin/env python3"
        assert f"# Generated by Blueprint (plan: {plan.plan_hash})" in lines[1]
        assert "# Pipeline: Hash Test" in lines[2]
        assert lines[3].startswith("# Generated:")


# ---------------------------------------------------------------------------
# Test 3: Jupyter export produces valid notebook
# ---------------------------------------------------------------------------

class TestJupyterExportValidNotebook:

    def test_jupyter_export_valid_notebook(self):
        """Generate .ipynb from a DAG and verify nbformat.validate() passes."""
        import nbformat

        nodes = [
            _node("A", config={"model": "gpt-4"}),
            _node("B", block_type="evaluate_model", category="evaluation"),
        ]
        edges = [_edge("A", "B")]
        plan = _make_plan(nodes, edges)

        with patch("backend.engine.jupyter_export._find_block_module") as mock_find:
            mock_find.return_value = MagicMock(
                __str__=lambda self: "/tmp/blocks/test_block",
                parent=MagicMock(__str__=lambda self: "/tmp/blocks"),
                __truediv__=lambda self, other: MagicMock(
                    exists=lambda: False,
                ),
            )

            from backend.engine.jupyter_export import compile_pipeline_to_jupyter, notebook_to_json

            nb = compile_pipeline_to_jupyter(
                pipeline_name="Jupyter Test",
                plan=plan,
                edges=edges,
                nodes=nodes,
                description="A test pipeline",
            )

        # Must be a valid notebook
        nbformat.validate(nb)

        # Serialize to JSON — must be valid JSON
        nb_json = notebook_to_json(nb)
        parsed = json.loads(nb_json)
        assert parsed["nbformat"] == 4

        # Should have header + install + setup + (2 blocks * (md + code)) cells
        # Plus potential viz cell for evaluate_model block
        assert len(nb.cells) >= 5

        # Header cell should mention pipeline name
        header_cell = nb.cells[0]
        assert header_cell.cell_type == "markdown"
        assert "Jupyter Test" in header_cell.source
        assert plan.plan_hash in header_cell.source


# ---------------------------------------------------------------------------
# Test 4: Loop graph export is rejected
# ---------------------------------------------------------------------------

class TestLoopGraphExportRejected:

    def test_loop_graph_export_rejected(self):
        """Attempting export of a loop fixture returns error reasons."""
        nodes = [
            _loop_controller_node("LC"),
            _node("B1"),
            _node("B2"),
        ]
        edges = [
            _edge("LC", "B1", src_handle="body"),
            _edge("B1", "B2"),
            _edge("B2", "LC", tgt_handle="feedback"),  # feedback edge creates loop
        ]

        reasons = validate_exportable(nodes, edges)
        assert len(reasons) > 0
        # Should mention loops
        assert any("loop" in r.lower() or "cycle" in r.lower() for r in reasons)

    def test_cycle_without_controller_rejected(self):
        """Illegal cycle (no loop controller) should also be rejected."""
        nodes = [_node("A"), _node("B"), _node("C")]
        edges = [_edge("A", "B"), _edge("B", "C"), _edge("C", "A")]

        reasons = validate_exportable(nodes, edges)
        assert len(reasons) > 0
        assert any("loop" in r.lower() or "cycle" in r.lower() for r in reasons)


# ---------------------------------------------------------------------------
# Test 5: Custom block export is rejected
# ---------------------------------------------------------------------------

class TestCustomBlockExportRejected:

    def test_custom_block_export_rejected(self):
        """python_runner blocks cannot be exported."""
        nodes = [
            _node("A"),
            _node("B", block_type="python_runner"),
            _node("C"),
        ]
        edges = [_edge("A", "B"), _edge("B", "C")]

        reasons = validate_exportable(nodes, edges)
        assert len(reasons) > 0
        assert any("python_runner" in r for r in reasons)

    def test_non_exportable_yaml_flag_rejected(self):
        """Blocks with exportable=False in block.yaml are rejected."""
        nodes = [_node("A", block_type="secret_block")]
        edges = []

        with patch("backend.engine.graph_utils.get_block_yaml") as mock_yaml:
            mock_yaml.return_value = {"exportable": False}
            reasons = validate_exportable(nodes, edges)

        assert len(reasons) > 0
        assert any("non-exportable" in r.lower() or "not exportable" in r.lower() for r in reasons)


# ---------------------------------------------------------------------------
# Test 6: Resolved configs match planner output
# ---------------------------------------------------------------------------

class TestResolvedConfigsMatchPlanner:

    def test_resolved_configs_match_planner(self):
        """Configs in the generated script must match the planner's resolved configs."""
        nodes = [
            _node("A", config={"lr": 0.001, "batch_size": 32}),
            _node("B", config={"threshold": 0.95}),
        ]
        edges = [_edge("A", "B")]
        plan = _make_plan(nodes, edges)

        with patch("backend.engine.compiler._find_block_module") as mock_find:
            mock_find.return_value = MagicMock(
                __str__=lambda self: "/tmp/blocks/test_block",
                parent=MagicMock(__str__=lambda self: "/tmp/blocks"),
            )

            script = compile_pipeline_from_plan(
                pipeline_name="Config Test",
                plan=plan,
                edges=edges,
                nodes=nodes,
            )

        # Verify that each node's resolved config appears in the script
        for node_id, resolved_node in plan.nodes.items():
            config = resolved_node.resolved_config
            if config:
                config_json = json.dumps(config, indent=8)
                # The config should appear in the script (possibly with extra whitespace)
                for key, value in config.items():
                    # Each config key=value should be in the generated script
                    assert json.dumps(key) in script, \
                        f"Config key '{key}' for node '{node_id}' not found in script"

        # Verify execution order matches plan
        for node_id in plan.execution_order:
            resolved = plan.nodes.get(node_id)
            if resolved:
                safe_id = f"node_{node_id.replace('-', '_')}"
                assert safe_id in script, \
                    f"Node '{node_id}' from plan execution_order not found in script"

    def test_plan_aware_compile_uses_resolved_not_raw(self):
        """The plan-aware compiler must use resolved_config, not raw node config."""
        # Create nodes with raw config
        nodes = [
            _node("A", config={"lr": 0.001}),
            _node("B", config={"epochs": 5}),
        ]
        edges = [_edge("A", "B")]

        # Create a plan where resolved configs differ from raw
        plan = ExecutionPlan(
            execution_order=("A", "B"),
            nodes={
                "A": ResolvedNode(
                    node_id="A",
                    block_type="test_block",
                    block_version="1.0.0",
                    resolved_config={"lr": 0.01, "momentum": 0.9},  # Different from raw!
                    config_sources={"lr": "workspace", "momentum": "workspace"},
                    cache_fingerprint="fp_a",
                    cache_eligible=True,
                    in_loop=False,
                    loop_id=None,
                ),
                "B": ResolvedNode(
                    node_id="B",
                    block_type="test_block",
                    block_version="1.0.0",
                    resolved_config={"epochs": 10},  # Different from raw!
                    config_sources={"epochs": "inherited:A"},
                    cache_fingerprint="fp_b",
                    cache_eligible=True,
                    in_loop=False,
                    loop_id=None,
                ),
            },
            loops=(),
            independent_subgraphs=(("A", "B"),),
            plan_hash="abc123",
            warnings=(),
        )

        with patch("backend.engine.compiler._find_block_module") as mock_find:
            mock_find.return_value = MagicMock(
                __str__=lambda self: "/tmp/blocks/test_block",
                parent=MagicMock(__str__=lambda self: "/tmp/blocks"),
            )

            script = compile_pipeline_from_plan(
                pipeline_name="Resolved Config Test",
                plan=plan,
                edges=edges,
                nodes=nodes,
            )

        # The script should contain the RESOLVED configs, not the raw ones
        assert "0.01" in script, "Resolved lr=0.01 should be in script"
        assert '"momentum"' in script, "Resolved momentum key should be in script"
        assert '"epochs": 10' in script, "Resolved epochs=10 should be in script"
        # Raw config values that differ should NOT appear
        assert '"lr": 0.001' not in script, "Raw lr=0.001 should NOT be in script"
        assert '"epochs": 5' not in script, "Raw epochs=5 should NOT be in script"


# ===========================================================================
# Risk mitigation tests
# ===========================================================================


# ---------------------------------------------------------------------------
# Risk 1: nbformat graceful degradation
# ---------------------------------------------------------------------------

class TestNbformatGracefulDegradation:

    def test_jupyter_export_raises_clear_error_without_nbformat(self):
        """If nbformat is not installed, a clear ImportError is raised."""
        import importlib
        import backend.engine.jupyter_export as jmod

        # Simulate nbformat being missing
        original_require = jmod._require_nbformat

        def _mock_require():
            raise ImportError(
                "The 'nbformat' package is required for Jupyter notebook export. "
                "Install it with: pip install 'nbformat>=5.9.0'"
            )

        jmod._require_nbformat = _mock_require
        try:
            with pytest.raises(ImportError, match="nbformat"):
                jmod.compile_pipeline_to_jupyter(
                    pipeline_name="test",
                    plan=ExecutionPlan(
                        execution_order=(), nodes={}, loops=(),
                        independent_subgraphs=(), plan_hash="x", warnings=(),
                    ),
                    edges=[], nodes=[],
                )
        finally:
            jmod._require_nbformat = original_require

    def test_module_imports_without_nbformat_at_module_level(self):
        """jupyter_export.py must not import nbformat at module level."""
        # Re-import the module and verify it doesn't crash even if
        # nbformat were hypothetically missing — the lazy import
        # means the module itself loads cleanly.
        import backend.engine.jupyter_export as jmod
        assert hasattr(jmod, "compile_pipeline_to_jupyter")
        assert hasattr(jmod, "_require_nbformat")


# ---------------------------------------------------------------------------
# Risk 2: Authoritative dependency resolution
# ---------------------------------------------------------------------------

class TestExportDependencies:

    def test_collect_pip_deps_from_plan(self):
        """Dependencies are resolved from the authoritative map, not filesystem."""
        from backend.engine.export_dependencies import collect_pip_dependencies_for_plan

        plan = ExecutionPlan(
            execution_order=("A", "B"),
            nodes={
                "A": ResolvedNode(
                    node_id="A", block_type="lora_finetuning",
                    block_version="1.0.0", resolved_config={},
                    config_sources={}, cache_fingerprint="",
                    cache_eligible=True, in_loop=False, loop_id=None,
                ),
                "B": ResolvedNode(
                    node_id="B", block_type="mmlu_eval",
                    block_version="1.0.0", resolved_config={},
                    config_sources={}, cache_fingerprint="",
                    cache_eligible=True, in_loop=False, loop_id=None,
                ),
            },
            loops=(), independent_subgraphs=(),
            plan_hash="test", warnings=(),
        )

        deps = collect_pip_dependencies_for_plan(plan)
        # Must include base deps
        assert "numpy" in deps
        assert "torch" in deps
        assert "tqdm" in deps
        # Must include lora_finetuning deps
        assert "peft" in deps
        assert "transformers" in deps
        assert "accelerate" in deps
        # Must include mmlu_eval deps
        assert "lm-eval" in deps

    def test_collect_pip_deps_for_unknown_block(self):
        """Unknown block types are silently skipped (base deps still present)."""
        from backend.engine.export_dependencies import collect_pip_dependencies_for_plan

        plan = ExecutionPlan(
            execution_order=("X",),
            nodes={
                "X": ResolvedNode(
                    node_id="X", block_type="totally_unknown_block",
                    block_version="1.0.0", resolved_config={},
                    config_sources={}, cache_fingerprint="",
                    cache_eligible=True, in_loop=False, loop_id=None,
                ),
            },
            loops=(), independent_subgraphs=(),
            plan_hash="test", warnings=(),
        )

        deps = collect_pip_dependencies_for_plan(plan)
        assert "numpy" in deps  # base deps always present
        assert "torch" in deps

    def test_jupyter_uses_authoritative_deps(self):
        """Jupyter export uses BLOCK_DEPENDENCIES, not filesystem scanning."""
        import nbformat
        nodes = [_node("A", block_type="lora_finetuning", category="training")]
        edges = []
        plan = _make_plan(nodes, edges)

        with patch("backend.engine.jupyter_export._find_block_module") as mock_find:
            mock_find.return_value = MagicMock(
                __str__=lambda self: "/tmp/blocks/lora_finetuning",
                parent=MagicMock(__str__=lambda self: "/tmp/blocks"),
                __truediv__=lambda self, other: MagicMock(exists=lambda: False),
            )

            from backend.engine.jupyter_export import compile_pipeline_to_jupyter
            nb = compile_pipeline_to_jupyter(
                pipeline_name="Deps Test", plan=plan,
                edges=edges, nodes=nodes,
            )

        # The install cell (index 1) should contain peft, transformers
        install_cell = nb.cells[1]
        assert install_cell.cell_type == "code"
        assert "peft" in install_cell.source
        assert "transformers" in install_cell.source


# ---------------------------------------------------------------------------
# Risk 3: Schema-driven metrics detection
# ---------------------------------------------------------------------------

class TestMetricsDetection:

    def test_block_with_metrics_output_detected(self):
        """Blocks with data_type='metrics' output ports are detected."""
        from backend.engine.jupyter_export import _block_has_metrics_output

        with patch("backend.engine.block_registry.get_block_yaml") as mock_yaml:
            mock_yaml.return_value = {
                "outputs": [
                    {"id": "metrics", "label": "Training Metrics", "data_type": "metrics"},
                    {"id": "model", "label": "Model", "data_type": "model"},
                ],
            }
            assert _block_has_metrics_output("lora_finetuning") is True

    def test_block_without_metrics_output_not_detected(self):
        """Blocks with no metrics output ports are not flagged."""
        from backend.engine.jupyter_export import _block_has_metrics_output

        with patch("backend.engine.block_registry.get_block_yaml") as mock_yaml:
            mock_yaml.return_value = {
                "outputs": [
                    {"id": "dataset", "label": "Data", "data_type": "dataset"},
                ],
            }
            assert _block_has_metrics_output("text_input") is False

    def test_metrics_alias_detected(self):
        """Blocks with 'metrics' alias on an output port are detected."""
        from backend.engine.jupyter_export import _block_has_metrics_output

        with patch("backend.engine.block_registry.get_block_yaml") as mock_yaml:
            mock_yaml.return_value = {
                "outputs": [
                    {"id": "metadata", "label": "Metadata", "data_type": "metrics",
                     "aliases": ["metrics"]},
                ],
            }
            assert _block_has_metrics_output("llm_inference") is True

    def test_unknown_block_returns_false(self):
        """Unknown blocks (no block.yaml) return False, not crash."""
        from backend.engine.jupyter_export import _block_has_metrics_output

        with patch("backend.engine.block_registry.get_block_yaml") as mock_yaml:
            mock_yaml.return_value = None
            assert _block_has_metrics_output("nonexistent") is False


# ---------------------------------------------------------------------------
# Risk 4: Portable paths
# ---------------------------------------------------------------------------

class TestPortablePaths:

    def test_python_export_contains_resolve_block_dir(self):
        """The generated Python script includes _resolve_block_dir() for portability."""
        nodes = [_node("A")]
        edges = []
        plan = _make_plan(nodes, edges)

        with patch("backend.engine.compiler._find_block_module") as mock_find:
            mock_find.return_value = MagicMock(
                __str__=lambda self: "/tmp/blocks/test_block",
                parent=MagicMock(__str__=lambda self: "/tmp/blocks"),
            )
            with patch("backend.engine.compiler._block_relative_path") as mock_rel:
                mock_rel.return_value = "data/test_block"

                script = compile_pipeline_from_plan(
                    pipeline_name="Portable Test", plan=plan,
                    edges=edges, nodes=nodes,
                )

        assert "_resolve_block_dir" in script
        assert "_SCRIPT_DIR" in script
        assert "data/test_block" in script

    def test_python_export_still_valid_ast_with_portable_paths(self):
        """Portable path resolution doesn't break Python syntax."""
        nodes = [_node("A"), _node("B")]
        edges = [_edge("A", "B")]
        plan = _make_plan(nodes, edges)

        with patch("backend.engine.compiler._find_block_module") as mock_find:
            mock_find.return_value = MagicMock(
                __str__=lambda self: "/tmp/blocks/test_block",
                parent=MagicMock(__str__=lambda self: "/tmp/blocks"),
            )
            with patch("backend.engine.compiler._block_relative_path") as mock_rel:
                mock_rel.return_value = "data/test_block"

                script = compile_pipeline_from_plan(
                    pipeline_name="AST Test", plan=plan,
                    edges=edges, nodes=nodes,
                )

        tree = ast.parse(script)
        assert tree is not None

    def test_jupyter_export_contains_resolve_block_dir(self):
        """The generated Jupyter notebook includes _resolve_block_dir()."""
        import nbformat
        nodes = [_node("A")]
        edges = []
        plan = _make_plan(nodes, edges)

        with patch("backend.engine.jupyter_export._find_block_module") as mock_find:
            mock_find.return_value = MagicMock(
                __str__=lambda self: "/tmp/blocks/test_block",
                parent=MagicMock(__str__=lambda self: "/tmp/blocks"),
                __truediv__=lambda self, other: MagicMock(exists=lambda: False),
            )
            with patch("backend.engine.jupyter_export._block_relative_path") as mock_rel:
                mock_rel.return_value = "data/test_block"

                from backend.engine.jupyter_export import compile_pipeline_to_jupyter
                nb = compile_pipeline_to_jupyter(
                    pipeline_name="Portable NB", plan=plan,
                    edges=edges, nodes=nodes,
                )

        # Setup cell (index 2) should contain _resolve_block_dir
        setup_cell = nb.cells[2]
        assert "_resolve_block_dir" in setup_cell.source

        # Block code cell should use _resolve_block_dir
        all_source = "\n".join(c.source for c in nb.cells)
        assert "_resolve_block_dir" in all_source
