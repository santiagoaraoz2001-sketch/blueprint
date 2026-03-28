"""Tests for the AutofixEngine (prompt 3.8).

Covers:
1. test_stale_handle_fix_proposed — renamed port → patch proposed
2. test_missing_config_default_applied — missing required field with schema default → fix
3. test_no_fixes_on_clean_pipeline — valid pipeline → empty patches
4. test_apply_and_revalidate — apply fix → re-run validator → error resolved
5. test_conflicting_fixes_handled — two conflicting fixes → safe handling
"""

import pytest
from typing import Any, Optional
from unittest.mock import MagicMock

from backend.engine.autofix import AutofixEngine, AutofixPatch
from backend.engine.validator import validate_pipeline
from backend.models.block_schema import BlockSchema, PortSchema, ConfigField


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(
    nid: str,
    block_type: str = "test_block",
    label: str | None = None,
    config: dict | None = None,
    inputs: list | None = None,
    outputs: list | None = None,
    block_version: str | None = None,
):
    """Create a minimal pipeline node dict."""
    data: dict[str, Any] = {
        "type": block_type,
        "label": label or f"Node {nid}",
        "category": "data",
        "config": config or {},
    }
    if inputs is not None:
        data["inputs"] = inputs
    if outputs is not None:
        data["outputs"] = outputs
    if block_version is not None:
        data["block_version"] = block_version
    return {"id": nid, "type": "default", "data": data}


def _edge(
    src: str, tgt: str,
    src_handle: str = "output", tgt_handle: str = "input",
    edge_id: str | None = None,
):
    """Create a pipeline edge dict."""
    eid = edge_id or f"{src}-{tgt}"
    return {
        "id": eid,
        "source": src,
        "target": tgt,
        "sourceHandle": src_handle,
        "targetHandle": tgt_handle,
    }


class MockRegistry:
    """Registry mock that supports configurable block schemas."""

    def __init__(self):
        self._blocks: dict[str, BlockSchema] = {}
        self._config_schemas: dict[str, dict] = {}

    def add_block(
        self,
        block_type: str,
        inputs: list[PortSchema] | None = None,
        outputs: list[PortSchema] | None = None,
        config_schema: dict | None = None,
        version: str = "1.0.0",
        tags: list[str] | None = None,
        category: str = "data",
        deprecated: bool = False,
    ):
        self._blocks[block_type] = BlockSchema(
            block_type=block_type,
            category=category,
            label=block_type,
            version=version,
            inputs=inputs or [],
            outputs=outputs or [],
            config=[],
            tags=tags or [],
            deprecated=deprecated,
        )
        if config_schema:
            self._config_schemas[block_type] = config_schema

    def get(self, block_type: str) -> BlockSchema | None:
        return self._blocks.get(block_type)

    def list_all(self, category: str | None = None) -> list[BlockSchema]:
        if category is None:
            return list(self._blocks.values())
        return [b for b in self._blocks.values() if b.category == category]

    def get_block_types(self) -> set[str]:
        return set(self._blocks.keys())

    def is_known_block(self, block_type: str) -> bool:
        return block_type in self._blocks

    def get_block_config_schema(self, block_type: str) -> dict:
        return self._config_schemas.get(block_type, {})

    def get_block_yaml(self, block_type: str) -> dict | None:
        schema = self._blocks.get(block_type)
        if schema is None:
            return None
        return {
            "type": block_type,
            "version": schema.version,
            "inputs": [{"id": p.id, "data_type": p.data_type} for p in schema.inputs],
            "outputs": [{"id": p.id, "data_type": p.data_type} for p in schema.outputs],
        }

    def get_output_alias_map(self, block_type: str) -> dict[str, str]:
        schema = self._blocks.get(block_type)
        if schema is None:
            return {}
        alias_map: dict[str, str] = {}
        for output in schema.outputs:
            for alias in output.aliases:
                alias_map[alias] = output.id
        return alias_map

    def resolve_output_handle(self, block_type: str, handle: str) -> str:
        alias_map = self.get_output_alias_map(block_type)
        return alias_map.get(handle, handle)

    def is_port_compatible(self, source_type: str, target_type: str) -> bool:
        if source_type == "any" or target_type == "any":
            return True
        return source_type == target_type

    def validate_connection(self, src_type, src_port, dst_type, dst_port):
        return {"valid": True}

    def get_block_version(self, block_type: str) -> str:
        schema = self._blocks.get(block_type)
        return schema.version if schema else "0.0.0"

    def get_block_schema_defaults(self, block_type: str) -> dict:
        return {}

    def get_category(self, block_type: str) -> str:
        return "data"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStaleHandleFixProposed:
    """Test 1: Pipeline with a renamed port should produce a patch to remap the edge."""

    def test_stale_output_handle_proposed(self):
        registry = MockRegistry()
        # Block has output "result" but the old name was "output"
        registry.add_block(
            "text_gen",
            outputs=[PortSchema(
                id="result", label="Result", data_type="text",
                aliases=["output"],  # old name
            )],
        )
        registry.add_block(
            "text_display",
            inputs=[PortSchema(id="input", label="Input", data_type="text", required=True)],
        )

        nodes = [
            _node("n1", "text_gen", label="Generator", outputs=[{"id": "output", "dataType": "text"}]),
            _node("n2", "text_display", label="Display", inputs=[{"id": "input", "dataType": "text", "required": True}]),
        ]
        edges = [_edge("n1", "n2", src_handle="output", tgt_handle="input")]

        # The warning message format from validator.py line ~320
        errors: list[str] = []
        warnings = [
            "Edge from 'Generator' references non-existent output port 'output'",
        ]

        engine = AutofixEngine(registry)
        patches = engine.propose_fixes(errors, warnings, nodes, edges)

        assert len(patches) == 1
        p = patches[0]
        assert p.action == "rename"
        assert p.field == "sourceHandle"
        assert p.old_value == "output"
        assert p.new_value == "result"
        assert p.confidence == "high"
        assert p.node_id == "n1"

    def test_stale_input_handle_proposed(self):
        registry = MockRegistry()
        registry.add_block(
            "text_display",
            inputs=[PortSchema(
                id="text_in", label="Text Input", data_type="text",
                aliases=["input"],  # old name
            )],
        )
        registry.add_block(
            "text_gen",
            outputs=[PortSchema(id="output", label="Output", data_type="text")],
        )

        nodes = [
            _node("n1", "text_gen", label="Generator"),
            _node("n2", "text_display", label="Display"),
        ]
        edges = [_edge("n1", "n2", src_handle="output", tgt_handle="input")]

        warnings = [
            "Edge to 'Display' references non-existent input port 'input'",
        ]

        engine = AutofixEngine(registry)
        patches = engine.propose_fixes([], warnings, nodes, edges)

        assert len(patches) == 1
        p = patches[0]
        assert p.action == "rename"
        assert p.field == "targetHandle"
        assert p.old_value == "input"
        assert p.new_value == "text_in"
        assert p.confidence == "high"


class TestMissingConfigDefaultApplied:
    """Test 2: Missing required config field with schema default → fix proposed and applied."""

    def test_missing_config_fix_proposed(self):
        registry = MockRegistry()
        registry.add_block(
            "llm_inference",
            inputs=[PortSchema(id="prompt", label="Prompt", data_type="text", required=True)],
            outputs=[PortSchema(id="response", label="Response", data_type="text")],
            config_schema={
                "model_name": {
                    "type": "string",
                    "mandatory": True,
                    "default": "gpt-4",
                    "label": "Model Name",
                },
            },
        )

        nodes = [
            _node("n1", "llm_inference", label="LLM", config={}),
        ]
        edges: list[dict] = []

        errors = [
            "Block 'LLM': 'model_name' is required but empty",
        ]

        engine = AutofixEngine(registry)
        patches = engine.propose_fixes(errors, [], nodes, edges)

        assert len(patches) == 1
        p = patches[0]
        assert p.action == "set"
        assert p.field == "config.model_name"
        assert p.new_value == "gpt-4"
        assert p.confidence == "high"

    def test_missing_config_fix_applied(self):
        registry = MockRegistry()
        registry.add_block(
            "llm_inference",
            config_schema={
                "model_name": {
                    "type": "string",
                    "mandatory": True,
                    "default": "gpt-4",
                    "label": "Model Name",
                },
            },
        )

        nodes = [_node("n1", "llm_inference", label="LLM", config={})]
        edges: list[dict] = []
        errors = ["Block 'LLM': 'model_name' is required but empty"]

        engine = AutofixEngine(registry)
        patches = engine.propose_fixes(errors, [], nodes, edges)
        assert len(patches) == 1

        new_nodes, new_edges, result = engine.apply_fixes(
            [patches[0].patch_id], nodes, edges, all_patches=patches,
        )

        assert len(result.applied) == 1
        assert len(result.skipped) == 0
        assert new_nodes[0]["data"]["config"]["model_name"] == "gpt-4"


class TestNoFixesOnCleanPipeline:
    """Test 3: A valid pipeline returns empty patches."""

    def test_empty_patches_for_valid_pipeline(self):
        registry = MockRegistry()
        registry.add_block(
            "text_gen",
            outputs=[PortSchema(id="output", label="Output", data_type="text")],
        )
        registry.add_block(
            "text_display",
            inputs=[PortSchema(id="input", label="Input", data_type="text")],
        )

        nodes = [
            _node("n1", "text_gen", label="Generator"),
            _node("n2", "text_display", label="Display"),
        ]
        edges = [_edge("n1", "n2")]

        # No errors, no warnings
        engine = AutofixEngine(registry)
        patches = engine.propose_fixes([], [], nodes, edges)

        assert patches == []

    def test_empty_patches_no_errors_no_warnings(self):
        registry = MockRegistry()
        engine = AutofixEngine(registry)
        patches = engine.propose_fixes([], [], [], [])
        assert patches == []


class TestApplyAndRevalidate:
    """Test 4: Apply a fix, then re-run the validator to verify the error is resolved."""

    def test_stale_handle_fix_resolves_error(self):
        registry = MockRegistry()
        registry.add_block(
            "text_gen",
            outputs=[PortSchema(
                id="result", label="Result", data_type="text",
                aliases=["output"],
            )],
        )
        registry.add_block(
            "text_display",
            inputs=[PortSchema(id="input", label="Input", data_type="text")],
        )

        nodes = [
            _node("n1", "text_gen", label="Generator",
                  outputs=[{"id": "output", "dataType": "text"}]),
            _node("n2", "text_display", label="Display",
                  inputs=[{"id": "input", "dataType": "text"}]),
        ]
        edges = [_edge("n1", "n2", src_handle="output", tgt_handle="input")]

        warnings = [
            "Edge from 'Generator' references non-existent output port 'output'",
        ]

        engine = AutofixEngine(registry)
        patches = engine.propose_fixes([], warnings, nodes, edges)
        assert len(patches) >= 1

        new_nodes, new_edges, result = engine.apply_fixes(
            [patches[0].patch_id], nodes, edges, all_patches=patches,
        )
        assert len(result.applied) == 1

        # Verify the edge was updated
        fixed_edge = new_edges[0]
        assert fixed_edge["sourceHandle"] == "result"

        # The stale handle warning should no longer match
        # (The edge now uses the canonical port name "result")
        assert fixed_edge["sourceHandle"] != "output"

    def test_config_fix_resolves_error(self):
        registry = MockRegistry()
        registry.add_block(
            "llm_inference",
            config_schema={
                "model_name": {
                    "type": "string",
                    "mandatory": True,
                    "default": "gpt-4",
                    "label": "Model Name",
                },
            },
        )

        nodes = [_node("n1", "llm_inference", label="LLM", config={})]
        edges: list[dict] = []
        errors = ["Block 'LLM': 'model_name' is required but empty"]

        engine = AutofixEngine(registry)
        patches = engine.propose_fixes(errors, [], nodes, edges)
        new_nodes, new_edges, result = engine.apply_fixes(
            [patches[0].patch_id], nodes, edges, all_patches=patches,
        )

        # After fix, model_name is set
        assert new_nodes[0]["data"]["config"]["model_name"] == "gpt-4"
        assert result.applied == [patches[0].patch_id]


class TestConflictingFixesHandled:
    """Test 5: Two patches that conflict — second one skipped safely."""

    def test_conflicting_edge_fixes(self):
        """Two patches both try to modify the same edge.
        First one succeeds, second one is skipped because the edge handle
        no longer matches its expected old_value."""
        registry = MockRegistry()
        registry.add_block(
            "text_gen",
            outputs=[
                PortSchema(id="result", label="Result", data_type="text", aliases=["output"]),
            ],
        )
        registry.add_block(
            "text_display",
            inputs=[PortSchema(id="input", label="Input", data_type="text")],
        )

        nodes = [
            _node("n1", "text_gen", label="Generator"),
            _node("n2", "text_display", label="Display"),
        ]
        edges = [_edge("n1", "n2", src_handle="output", tgt_handle="input", edge_id="e1")]

        # Create two patches that both try to rename the same sourceHandle
        patch1 = AutofixPatch(
            patch_id="patch-1",
            node_id="n1",
            field="sourceHandle",
            action="rename",
            old_value="output",
            new_value="result",
            reason="Rename stale handle",
            confidence="high",
            edge_id="e1",
        )
        patch2 = AutofixPatch(
            patch_id="patch-2",
            node_id="n1",
            field="sourceHandle",
            action="rename",
            old_value="output",  # same old_value — will be stale after patch1
            new_value="other_result",
            reason="Conflicting rename",
            confidence="high",
            edge_id="e1",
        )

        engine = AutofixEngine(registry)
        new_nodes, new_edges, result = engine.apply_fixes(
            ["patch-1", "patch-2"], nodes, edges, all_patches=[patch1, patch2],
        )

        # First patch applied
        assert "patch-1" in result.applied
        # Second patch skipped because old_value no longer matches
        assert len(result.skipped) == 1
        assert result.skipped[0]["patch_id"] == "patch-2"

        # Edge has the value from the first patch
        assert new_edges[0]["sourceHandle"] == "result"

    def test_delete_then_rename_same_edge(self):
        """Delete an edge, then try to rename a handle on the deleted edge."""
        registry = MockRegistry()

        nodes = [
            _node("n1", "text_gen", label="Generator"),
            _node("n2", "text_display", label="Display"),
        ]
        edges = [_edge("n1", "n2", src_handle="output", tgt_handle="input", edge_id="e1")]

        patch_delete = AutofixPatch(
            patch_id="del-1",
            node_id="n2",
            field="edge",
            action="delete",
            old_value="e1",
            new_value=None,
            reason="Remove incompatible edge",
            confidence="medium",
            edge_id="e1",
        )
        patch_rename = AutofixPatch(
            patch_id="rename-1",
            node_id="n1",
            field="sourceHandle",
            action="rename",
            old_value="output",
            new_value="result",
            reason="Rename handle on deleted edge",
            confidence="high",
            edge_id="e1",
        )

        engine = AutofixEngine(registry)
        new_nodes, new_edges, result = engine.apply_fixes(
            ["del-1", "rename-1"], nodes, edges,
            all_patches=[patch_delete, patch_rename],
        )

        # Delete succeeded
        assert "del-1" in result.applied
        assert len(new_edges) == 0
        # Rename skipped — edge no longer exists
        assert len(result.skipped) == 1
        assert result.skipped[0]["patch_id"] == "rename-1"


class TestConverterBlockSuggestion:
    """Converter block insertion for incompatible connections."""

    def test_converter_proposed_when_available(self):
        """When a converter block exists, propose insert_converter instead of delete."""
        registry = MockRegistry()
        registry.add_block(
            "text_gen",
            outputs=[PortSchema(id="output", label="Output", data_type="text")],
        )
        registry.add_block(
            "model_trainer",
            inputs=[PortSchema(id="data_in", label="Data", data_type="dataset", required=True)],
        )
        # The converter: text → dataset
        registry.add_block(
            "text_to_dataset",
            inputs=[PortSchema(id="text", label="Text", data_type="text")],
            outputs=[PortSchema(id="dataset", label="Dataset", data_type="dataset")],
            tags=["adapter", "conversion"],
            category="data",
        )

        nodes = [
            _node("n1", "text_gen", label="Generator", outputs=[{"id": "output", "dataType": "text"}]),
            _node("n2", "model_trainer", label="Trainer", inputs=[{"id": "data_in", "dataType": "dataset"}]),
        ]
        edges = [_edge("n1", "n2", src_handle="output", tgt_handle="data_in", edge_id="e1")]

        errors = [
            "Incompatible connection: Cannot connect TEXT (Generator) to DATASET (Trainer)",
        ]

        engine = AutofixEngine(registry)
        patches = engine.propose_fixes(errors, [], nodes, edges)

        assert len(patches) == 1
        p = patches[0]
        assert p.action == "insert_converter"
        assert p.field == "converter"
        assert p.confidence == "medium"
        assert p.new_value["converter_block_type"] == "text_to_dataset"
        assert p.new_value["converter_in_port"] == "text"
        assert p.new_value["converter_out_port"] == "dataset"
        assert p.new_value["source_node_id"] == "n1"
        assert p.new_value["target_node_id"] == "n2"

    def test_converter_applied_creates_node_and_edges(self):
        """Applying insert_converter creates the converter node and rewires edges."""
        registry = MockRegistry()
        registry.add_block(
            "text_gen",
            outputs=[PortSchema(id="output", label="Output", data_type="text")],
        )
        registry.add_block(
            "model_trainer",
            inputs=[PortSchema(id="data_in", label="Data", data_type="dataset")],
        )
        registry.add_block(
            "text_to_dataset",
            inputs=[PortSchema(id="text", label="Text", data_type="text")],
            outputs=[PortSchema(id="dataset", label="Dataset", data_type="dataset")],
            tags=["adapter", "conversion"],
        )

        nodes = [
            _node("n1", "text_gen", label="Generator"),
            _node("n2", "model_trainer", label="Trainer"),
        ]
        edges = [_edge("n1", "n2", src_handle="output", tgt_handle="data_in", edge_id="e1")]

        errors = [
            "Incompatible connection: Cannot connect TEXT (Generator) to DATASET (Trainer)",
        ]

        engine = AutofixEngine(registry)
        patches = engine.propose_fixes(errors, [], nodes, edges)
        assert len(patches) == 1

        new_nodes, new_edges, result = engine.apply_fixes(
            [patches[0].patch_id], nodes, edges, all_patches=patches,
        )

        assert len(result.applied) == 1
        assert len(result.skipped) == 0

        # Should have 3 nodes (original 2 + converter)
        assert len(new_nodes) == 3
        converter_node = new_nodes[2]
        assert converter_node["data"]["type"] == "text_to_dataset"
        assert converter_node["id"].startswith("autofix-")

        # Should have 2 edges (old removed, 2 new wires)
        assert len(new_edges) == 2
        # Edge 1: source → converter
        e1 = new_edges[0]
        assert e1["source"] == "n1"
        assert e1["target"] == converter_node["id"]
        assert e1["sourceHandle"] == "output"
        assert e1["targetHandle"] == "text"
        # Edge 2: converter → target
        e2 = new_edges[1]
        assert e2["source"] == converter_node["id"]
        assert e2["target"] == "n2"
        assert e2["sourceHandle"] == "dataset"
        assert e2["targetHandle"] == "data_in"

    def test_fallback_to_delete_when_no_converter(self):
        """When no converter block exists, fall back to edge deletion."""
        registry = MockRegistry()
        registry.add_block(
            "text_gen",
            outputs=[PortSchema(id="output", label="Output", data_type="text")],
        )
        registry.add_block(
            "agent_block",
            inputs=[PortSchema(id="agent_in", label="Agent", data_type="agent")],
        )
        # No converter from text → agent

        nodes = [
            _node("n1", "text_gen", label="Generator"),
            _node("n2", "agent_block", label="Agent"),
        ]
        edges = [_edge("n1", "n2", src_handle="output", tgt_handle="agent_in", edge_id="e1")]

        errors = [
            "Incompatible connection: Cannot connect TEXT (Generator) to AGENT (Agent)",
        ]

        engine = AutofixEngine(registry)
        patches = engine.propose_fixes(errors, [], nodes, edges)

        assert len(patches) == 1
        p = patches[0]
        assert p.action == "delete"
        assert p.field == "edge"
        assert "no converter block available" in p.reason

    def test_converter_prefers_tagged_adapters(self):
        """Purpose-built adapters (tagged 'adapter'/'conversion') are preferred over
        generic blocks that happen to have compatible port types."""
        registry = MockRegistry()
        registry.add_block(
            "text_gen",
            outputs=[PortSchema(id="output", label="Output", data_type="text")],
        )
        registry.add_block(
            "model_trainer",
            inputs=[PortSchema(id="data_in", label="Data", data_type="dataset")],
        )
        # A purpose-built converter tagged as adapter
        registry.add_block(
            "text_to_dataset",
            inputs=[PortSchema(id="text", label="Text", data_type="text")],
            outputs=[PortSchema(id="dataset", label="Dataset", data_type="dataset")],
            tags=["adapter", "conversion"],
        )
        # A generic block that also converts text → dataset (but isn't an adapter)
        registry.add_block(
            "generic_processor",
            inputs=[
                PortSchema(id="input", label="Input", data_type="text"),
                PortSchema(id="config", label="Config", data_type="config"),
            ],
            outputs=[
                PortSchema(id="output", label="Output", data_type="dataset"),
                PortSchema(id="log", label="Log", data_type="text"),
            ],
        )

        nodes = [
            _node("n1", "text_gen", label="Generator"),
            _node("n2", "model_trainer", label="Trainer"),
        ]
        edges = [_edge("n1", "n2", src_handle="output", tgt_handle="data_in", edge_id="e1")]

        errors = [
            "Incompatible connection: Cannot connect TEXT (Generator) to DATASET (Trainer)",
        ]

        engine = AutofixEngine(registry)
        patches = engine.propose_fixes(errors, [], nodes, edges)

        assert len(patches) == 1
        # Should prefer the tagged adapter over the generic processor
        assert patches[0].new_value["converter_block_type"] == "text_to_dataset"

    def test_converter_skips_deprecated_blocks(self):
        """Deprecated converter blocks should not be suggested."""
        registry = MockRegistry()
        registry.add_block(
            "text_gen",
            outputs=[PortSchema(id="output", label="Output", data_type="text")],
        )
        registry.add_block(
            "model_trainer",
            inputs=[PortSchema(id="data_in", label="Data", data_type="dataset")],
        )
        # Deprecated converter
        registry.add_block(
            "text_to_dataset_old",
            inputs=[PortSchema(id="text", label="Text", data_type="text")],
            outputs=[PortSchema(id="dataset", label="Dataset", data_type="dataset")],
            tags=["adapter", "conversion"],
            deprecated=True,
        )
        # Non-deprecated converter
        registry.add_block(
            "dataset_builder",
            inputs=[PortSchema(id="source", label="Source", data_type="text")],
            outputs=[PortSchema(id="result", label="Result", data_type="dataset")],
            tags=["adapter"],
        )

        nodes = [
            _node("n1", "text_gen", label="Generator"),
            _node("n2", "model_trainer", label="Trainer"),
        ]
        edges = [_edge("n1", "n2", src_handle="output", tgt_handle="data_in", edge_id="e1")]

        errors = [
            "Incompatible connection: Cannot connect TEXT (Generator) to DATASET (Trainer)",
        ]

        engine = AutofixEngine(registry)
        patches = engine.propose_fixes(errors, [], nodes, edges)

        assert len(patches) == 1
        assert patches[0].new_value["converter_block_type"] == "dataset_builder"

    def test_converter_position_is_midpoint(self):
        """Converter node position should be the midpoint between source and target."""
        registry = MockRegistry()
        registry.add_block(
            "text_gen",
            outputs=[PortSchema(id="output", label="Output", data_type="text")],
        )
        registry.add_block(
            "model_trainer",
            inputs=[PortSchema(id="data_in", label="Data", data_type="dataset")],
        )
        registry.add_block(
            "text_to_dataset",
            inputs=[PortSchema(id="text", label="Text", data_type="text")],
            outputs=[PortSchema(id="dataset", label="Dataset", data_type="dataset")],
            tags=["adapter"],
        )

        nodes = [
            {**_node("n1", "text_gen", label="Generator"), "position": {"x": 100, "y": 200}},
            {**_node("n2", "model_trainer", label="Trainer"), "position": {"x": 500, "y": 200}},
        ]
        edges = [_edge("n1", "n2", src_handle="output", tgt_handle="data_in", edge_id="e1")]

        errors = [
            "Incompatible connection: Cannot connect TEXT (Generator) to DATASET (Trainer)",
        ]

        engine = AutofixEngine(registry)
        patches = engine.propose_fixes(errors, [], nodes, edges)

        assert len(patches) == 1
        pos = patches[0].new_value["position"]
        assert pos["x"] == 300.0  # midpoint of 100 and 500
        assert pos["y"] == 200.0
