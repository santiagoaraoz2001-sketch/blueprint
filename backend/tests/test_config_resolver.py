"""
Tests for the Config Inheritance Resolver.

Covers the 7 acceptance criteria plus edge cases:
1. Seed propagation through a linear chain
2. Override respected (explicit value not replaced)
3. Override value propagates downstream (not reverted to original)
4. text_column propagation
5. trust_remote_code propagation
6. Original pipeline JSON not mutated
7. Provenance tracking (_inherited metadata)
"""

import copy
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.engine.config_resolver import (
    CATEGORY_PROPAGATION_KEYS,
    GLOBAL_PROPAGATION_KEYS,
    _get_all_propagation_keys,
    _get_propagation_keys,
    _is_user_override,
    _load_schema_defaults,
    resolve_configs,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_node(node_id, block_type="test_block", category="data", config=None):
    return {
        "id": node_id,
        "type": "customNode",
        "data": {
            "type": block_type,
            "category": category,
            "label": node_id,
            "config": config or {},
        },
    }


def _make_edge(source, target):
    return {"source": source, "target": target}


# Fake block directory that returns a schema with seed, text_column,
# trust_remote_code, system_prompt, training_format, and prompt_template defaults
_FAKE_SCHEMA = {
    "config": {
        "seed": {"type": "integer", "default": 42},
        "text_column": {"type": "string", "default": "text"},
        "trust_remote_code": {"type": "boolean", "default": False},
        "system_prompt": {"type": "string", "default": ""},
        "training_format": {"type": "string", "default": ""},
        "prompt_template": {"type": "string", "default": ""},
    }
}


def _fake_find_block_dir(block_type):
    """Return a fake block directory path (schema loaded via mock)."""
    return Path(f"/fake/blocks/{block_type}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_schema_loading():
    """Mock YAML loading so tests don't need real block directories."""
    import yaml

    def fake_load_defaults(block_dir_str):
        defaults = {}
        config_section = _FAKE_SCHEMA.get("config", {})
        for field_name, field_def in config_section.items():
            if isinstance(field_def, dict) and "default" in field_def:
                defaults[field_name] = field_def["default"]
        return defaults

    # Clear lru_cache before each test
    _load_schema_defaults.cache_clear()

    with patch("backend.engine.config_resolver.Path.exists", return_value=True), \
         patch("builtins.open", create=True), \
         patch("yaml.safe_load", return_value=_FAKE_SCHEMA):
        yield

    _load_schema_defaults.cache_clear()


# ===========================================================================
# Acceptance Criteria Tests
# ===========================================================================

class TestSeedPropagation:
    """Criterion 1: seed set on node A propagates to downstream B and C."""

    def test_linear_chain(self):
        nodes = [
            _make_node("a", config={"seed": 99}),
            _make_node("b"),
            _make_node("c"),
        ]
        edges = [_make_edge("a", "b"), _make_edge("b", "c")]
        order = ["a", "b", "c"]

        resolved = resolve_configs(nodes, edges, order, _fake_find_block_dir)

        assert resolved["b"]["seed"] == 99
        assert resolved["c"]["seed"] == 99


class TestOverrideRespected:
    """Criterion 2: If downstream node explicitly sets a value, it is NOT replaced."""

    def test_explicit_override_preserved(self):
        nodes = [
            _make_node("a", config={"seed": 99}),
            _make_node("b", config={"seed": 7}),  # explicit override
        ]
        edges = [_make_edge("a", "b")]
        order = ["a", "b"]

        resolved = resolve_configs(nodes, edges, order, _fake_find_block_dir)

        assert resolved["b"]["seed"] == 7  # NOT 99


class TestOverridePropagatesDownstream:
    """Criterion 3: Override value propagates further downstream."""

    def test_override_flows_downstream(self):
        nodes = [
            _make_node("a", config={"seed": 99}),
            _make_node("b", config={"seed": 7}),
            _make_node("c"),
        ]
        edges = [_make_edge("a", "b"), _make_edge("b", "c")]
        order = ["a", "b", "c"]

        resolved = resolve_configs(nodes, edges, order, _fake_find_block_dir)

        assert resolved["b"]["seed"] == 7
        assert resolved["c"]["seed"] == 7  # Gets B's override, not A's


class TestTextColumnPropagation:
    """Criterion 4: text_column propagates."""

    def test_text_column_propagates(self):
        nodes = [
            _make_node("src", config={"text_column": "content"}),
            _make_node("dst"),
        ]
        edges = [_make_edge("src", "dst")]
        order = ["src", "dst"]

        resolved = resolve_configs(nodes, edges, order, _fake_find_block_dir)

        assert resolved["dst"]["text_column"] == "content"


class TestTrustRemoteCodePropagation:
    """Criterion 5: trust_remote_code propagates."""

    def test_trust_remote_code_propagates(self):
        nodes = [
            _make_node("src", config={"trust_remote_code": True}),
            _make_node("dst"),
        ]
        edges = [_make_edge("src", "dst")]
        order = ["src", "dst"]

        resolved = resolve_configs(nodes, edges, order, _fake_find_block_dir)

        assert resolved["dst"]["trust_remote_code"] is True


class TestOriginalNotMutated:
    """Criterion 6: Original pipeline JSON is not mutated."""

    def test_no_mutation(self):
        nodes = [
            _make_node("a", config={"seed": 99}),
            _make_node("b"),
        ]
        edges = [_make_edge("a", "b")]
        order = ["a", "b"]

        original_b_config = copy.deepcopy(nodes[1]["data"]["config"])

        resolve_configs(nodes, edges, order, _fake_find_block_dir)

        assert nodes[1]["data"]["config"] == original_b_config


class TestProvenanceTracking:
    """Criterion 7: _inherited metadata tracks provenance."""

    def test_inherited_metadata_present(self):
        nodes = [
            _make_node("a", config={"seed": 99}),
            _make_node("b"),
        ]
        edges = [_make_edge("a", "b")]
        order = ["a", "b"]

        resolved = resolve_configs(nodes, edges, order, _fake_find_block_dir)

        assert "_inherited" in resolved["b"]
        inherited = resolved["b"]["_inherited"]
        assert "seed" in inherited
        assert inherited["seed"]["from_node"] == "a"
        assert inherited["seed"]["value"] == 99


# ===========================================================================
# Edge Case Tests
# ===========================================================================

class TestMultiKeyProvenance:
    """Multiple keys inherit from different upstream nodes."""

    def test_multi_key_sources(self):
        nodes = [
            _make_node("seed_src", config={"seed": 123}),
            _make_node("text_src", config={"text_column": "body"}),
            _make_node("merger"),
        ]
        edges = [
            _make_edge("seed_src", "merger"),
            _make_edge("text_src", "merger"),
        ]
        order = ["seed_src", "text_src", "merger"]

        resolved = resolve_configs(nodes, edges, order, _fake_find_block_dir)

        inherited = resolved["merger"]["_inherited"]
        assert inherited["seed"]["from_node"] == "seed_src"
        assert inherited["text_column"]["from_node"] == "text_src"


class TestDiamondDAG:
    """Diamond DAG: first upstream in topo order wins."""

    def test_diamond_first_wins(self):
        nodes = [
            _make_node("root", config={"seed": 10}),
            _make_node("left", config={"seed": 20}),
            _make_node("right", config={"seed": 30}),
            _make_node("merge"),
        ]
        edges = [
            _make_edge("root", "left"),
            _make_edge("root", "right"),
            _make_edge("left", "merge"),
            _make_edge("right", "merge"),
        ]
        order = ["root", "left", "right", "merge"]

        resolved = resolve_configs(nodes, edges, order, _fake_find_block_dir)

        # Both left and right override seed; first upstream (left) wins
        assert resolved["merge"]["seed"] == 20


class TestMissingBlockDir:
    """Block directory not found — resolver still works, just no schema defaults."""

    def test_missing_block_dir(self):
        def bad_find(block_type):
            return None

        nodes = [
            _make_node("a", config={"seed": 99}),
            _make_node("b"),
        ]
        edges = [_make_edge("a", "b")]
        order = ["a", "b"]

        # Should not crash
        resolved = resolve_configs(nodes, edges, order, bad_find)
        # Without schema defaults, inheritance can't detect defaults vs overrides,
        # so no inheritance occurs for nodes with missing block dirs
        assert "seed" not in resolved["b"] or resolved["b"].get("seed") == 99


class TestFindBlockDirRaises:
    """find_block_dir_fn raising an error — gracefully handled."""

    def test_find_raises_value_error(self):
        def raising_find(block_type):
            raise ValueError(f"Unknown block: {block_type}")

        nodes = [
            _make_node("a", config={"seed": 99}),
            _make_node("b"),
        ]
        edges = [_make_edge("a", "b")]
        order = ["a", "b"]

        # Should not crash
        resolved = resolve_configs(nodes, edges, order, raising_find)
        assert "a" in resolved
        assert "b" in resolved


class TestEmptyPipeline:
    """Empty pipeline returns empty dict."""

    def test_empty(self):
        resolved = resolve_configs([], [], [], _fake_find_block_dir)
        assert resolved == {}


class TestGroupNodeSkipped:
    """groupNode type nodes are skipped."""

    def test_group_node_ignored(self):
        nodes = [
            _make_node("a", config={"seed": 99}),
            {"id": "group1", "type": "groupNode", "data": {}},
            _make_node("b"),
        ]
        edges = [_make_edge("a", "b")]
        order = ["a", "group1", "b"]

        resolved = resolve_configs(nodes, edges, order, _fake_find_block_dir)

        assert "group1" not in resolved
        assert resolved["b"]["seed"] == 99


class TestCategoryIsolation:
    """Category-specific keys only apply to matching categories."""

    def test_system_prompt_only_for_inference(self):
        nodes = [
            _make_node("inf1", category="inference", config={"system_prompt": "Be helpful"}),
            _make_node("data1", category="data"),
            _make_node("inf2", category="inference"),
        ]
        edges = [
            _make_edge("inf1", "data1"),
            _make_edge("data1", "inf2"),
        ]
        order = ["inf1", "data1", "inf2"]

        resolved = resolve_configs(nodes, edges, order, _fake_find_block_dir)

        # system_prompt should NOT be applied to data node (wrong category)
        assert resolved["data1"].get("system_prompt", "") == ""
        # But SHOULD flow through data1 to reach inf2
        assert resolved["inf2"]["system_prompt"] == "Be helpful"


class TestCategoryFlowThroughIntermediate:
    """Category-specific values flow through intermediate blocks of different categories."""

    def test_training_format_flows_through_data(self):
        nodes = [
            _make_node("train1", category="training", config={"training_format": "alpaca"}),
            _make_node("data1", category="data"),
            _make_node("train2", category="training"),
        ]
        edges = [
            _make_edge("train1", "data1"),
            _make_edge("data1", "train2"),
        ]
        order = ["train1", "data1", "train2"]

        resolved = resolve_configs(nodes, edges, order, _fake_find_block_dir)

        assert resolved["train2"]["training_format"] == "alpaca"


class TestDisconnectedNodes:
    """Disconnected nodes receive no inheritance."""

    def test_no_inheritance_for_disconnected(self):
        nodes = [
            _make_node("a", config={"seed": 99}),
            _make_node("b"),
        ]
        edges = []  # No edges — disconnected
        order = ["a", "b"]

        resolved = resolve_configs(nodes, edges, order, _fake_find_block_dir)

        # b should NOT inherit seed from a (no edge)
        assert "seed" not in resolved["b"] or resolved["b"].get("seed") == 42


class TestLongChainPropagation:
    """Values propagate through long chains."""

    def test_five_node_chain(self):
        nodes = [_make_node(f"n{i}") for i in range(5)]
        nodes[0]["data"]["config"]["seed"] = 777

        edges = [_make_edge(f"n{i}", f"n{i+1}") for i in range(4)]
        order = [f"n{i}" for i in range(5)]

        resolved = resolve_configs(nodes, edges, order, _fake_find_block_dir)

        for i in range(1, 5):
            assert resolved[f"n{i}"]["seed"] == 777


# ===========================================================================
# Unit Tests for Internal Functions
# ===========================================================================

class TestIsUserOverride:
    def test_different_from_default(self):
        assert _is_user_override("seed", 99, 42) is True

    def test_same_as_default(self):
        assert _is_user_override("seed", 42, 42) is False

    def test_no_schema_default_with_value(self):
        assert _is_user_override("seed", 99, None) is True

    def test_no_schema_default_empty_value(self):
        assert _is_user_override("seed", "", None) is False

    def test_no_schema_default_none_value(self):
        assert _is_user_override("seed", None, None) is False


class TestGetPropagationKeys:
    def test_global_keys_always_present(self):
        keys = _get_propagation_keys("data")
        for k in GLOBAL_PROPAGATION_KEYS:
            assert k in keys

    def test_inference_includes_system_prompt(self):
        keys = _get_propagation_keys("inference")
        assert "system_prompt" in keys

    def test_training_includes_training_format(self):
        keys = _get_propagation_keys("training")
        assert "training_format" in keys
        assert "prompt_template" in keys

    def test_data_excludes_category_keys(self):
        keys = _get_propagation_keys("data")
        assert "system_prompt" not in keys
        assert "training_format" not in keys


class TestGetAllPropagationKeys:
    def test_includes_all(self):
        keys = _get_all_propagation_keys()
        assert "seed" in keys
        assert "text_column" in keys
        assert "trust_remote_code" in keys
        assert "system_prompt" in keys
        assert "training_format" in keys
        assert "prompt_template" in keys
