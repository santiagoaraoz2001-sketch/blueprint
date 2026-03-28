"""
Tests for Config Resolver — config precedence, workspace propagation, and source tracking.

5 required tests:
1. test_user_override_beats_workspace — user seed=99 wins over workspace seed=42
2. test_workspace_propagates_seed — workspace seed=42 propagates to all blocks with seed config
3. test_inheritance_through_dag — upstream block value inherited by downstream
4. test_default_fallback — no user/workspace/inherited value, falls back to schema default
5. test_config_sources_tracked — every resolved value has a source entry

Plus additional tests:
- inject_workspace_file_paths behavior
- workspace_config extraction from pipeline definition
"""

from typing import Any, Optional
from unittest.mock import patch, MagicMock

import pytest

from backend.engine.config_resolver import resolve_configs, inject_workspace_file_paths


# ---------------------------------------------------------------------------
# Fake BlockRegistryService
# ---------------------------------------------------------------------------

class FakeRegistry:
    """Minimal stand-in for BlockRegistryService that returns controlled schema data."""

    def __init__(self, schema_defaults: dict[str, Any] | None = None, version: str = "1.0.0"):
        self._defaults = schema_defaults or {
            "seed": 42,
            "text_column": "text",
            "trust_remote_code": False,
            "system_prompt": "",
            "prompt_template": "",
            "model_name": "",
        }
        self._version = version

    def get_block_schema_defaults(self, block_type: str) -> dict[str, Any]:
        return dict(self._defaults)

    def get_block_version(self, block_type: str) -> str:
        return self._version

    def get_block_info(self, block_type: str) -> Optional[dict]:
        return {"type": block_type, "category": "data", "path": f"/fake/{block_type}"}

    def get_block_config_schema(self, block_type: str) -> dict[str, Any]:
        return {k: {"type": "string", "default": v} for k, v in self._defaults.items()}

    def get_category(self, block_type: str) -> str:
        return "data"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(node_id: str, block_type: str = "test_block", category: str = "data", config: dict | None = None):
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


def _edge(source: str, target: str):
    return {"source": source, "target": target}


# ===========================================================================
# Required Acceptance Tests
# ===========================================================================


class TestUserOverrideBeatsWorkspace:
    """User sets seed=99, workspace has seed=42 — resolved should be 99 with source 'user'."""

    def test_user_override_beats_workspace(self):
        nodes = [_node("a", config={"seed": 99})]
        edges = []
        order = ["a"]
        workspace = {"seed": 42}
        registry = FakeRegistry()

        result = resolve_configs(nodes, edges, order, workspace, registry)
        resolved_config, config_sources = result["a"]

        assert resolved_config["seed"] == 99
        assert config_sources["seed"] == "user"


class TestWorkspacePropagatesSeed:
    """Workspace seed=42 propagates to ALL blocks that have seed in their schema."""

    def test_workspace_propagates_seed(self):
        nodes = [
            _node("a"),
            _node("b"),
            _node("c"),
        ]
        edges = [_edge("a", "b"), _edge("b", "c")]
        order = ["a", "b", "c"]
        workspace = {"seed": 777}
        registry = FakeRegistry()

        result = resolve_configs(nodes, edges, order, workspace, registry)

        for nid in ["a", "b", "c"]:
            cfg, src = result[nid]
            assert cfg["seed"] == 777, f"Node {nid} should have workspace seed"
            assert src["seed"] == "workspace", f"Node {nid} source should be 'workspace'"


class TestInheritanceThroughDag:
    """Upstream block sets model_name, downstream block inherits it."""

    def test_inheritance_through_dag(self):
        # model_name is in schema defaults but not a propagation key by default.
        # However, seed IS a propagation key. Use seed for this test.
        nodes = [
            _node("upstream", config={"seed": 123}),
            _node("downstream"),
        ]
        edges = [_edge("upstream", "downstream")]
        order = ["upstream", "downstream"]
        registry = FakeRegistry()

        result = resolve_configs(nodes, edges, order, None, registry)
        cfg, src = result["downstream"]

        assert cfg["seed"] == 123
        assert src["seed"] == "inherited:upstream"


class TestDefaultFallback:
    """No user/workspace/inherited value — falls back to schema default."""

    def test_default_fallback(self):
        nodes = [_node("a")]
        edges = []
        order = ["a"]
        registry = FakeRegistry()

        result = resolve_configs(nodes, edges, order, None, registry)
        cfg, src = result["a"]

        assert cfg["seed"] == 42  # schema default
        assert src["seed"] == "block_default"
        assert cfg["text_column"] == "text"
        assert src["text_column"] == "block_default"


class TestConfigSourcesTracked:
    """Every resolved value has a source entry — user, workspace, inherited, or block_default."""

    def test_config_sources_tracked(self):
        nodes = [
            _node("a", config={"seed": 99}),
            _node("b"),
        ]
        edges = [_edge("a", "b")]
        order = ["a", "b"]
        workspace = {"text_column": "body"}
        registry = FakeRegistry()

        result = resolve_configs(nodes, edges, order, workspace, registry)

        for nid in ["a", "b"]:
            cfg, src = result[nid]
            # Every key in resolved config must have a corresponding source
            for key in cfg:
                assert key in src, f"Node {nid}: key '{key}' missing from config_sources"
                assert src[key] in (
                    "user", "workspace", "block_default",
                ) or src[key].startswith("inherited:"), (
                    f"Node {nid}: key '{key}' has invalid source '{src[key]}'"
                )

        # Verify specific sources
        a_cfg, a_src = result["a"]
        assert a_src["seed"] == "user"
        assert a_src["text_column"] == "workspace"

        b_cfg, b_src = result["b"]
        assert b_src["text_column"] == "workspace"
        # seed inherited from a (user set 99, which differs from default 42)
        assert b_src["seed"] == "inherited:a"


# ===========================================================================
# inject_workspace_file_paths Tests
# ===========================================================================


class FakeRegistryWithFilePaths(FakeRegistry):
    """Registry that declares output_path as a file_path field."""

    def get_file_path_fields(self, block_type: str) -> frozenset[str]:
        return frozenset(["output_path"])


class TestInjectWorkspaceFilePathsNoOp:
    """No-op when workspace is not configured."""

    def test_noop_when_no_workspace(self):
        nodes = [_node("a")]
        resolved = resolve_configs(nodes, [], ["a"], None, FakeRegistry())

        with patch(
            "backend.engine.config_resolver._get_workspace_settings",
            return_value=(None, False),
        ):
            inject_workspace_file_paths(resolved, nodes, FakeRegistryWithFilePaths())

        # Nothing should change
        cfg, src = resolved["a"]
        assert src.get("output_path") is None or src.get("output_path") == "block_default"


class TestInjectWorkspaceFilePathsOnlyDefault:
    """Only replaces values whose source is 'block_default'."""

    def test_user_override_not_replaced(self):
        nodes = [_node("a", config={"output_path": "/my/custom/path"})]
        registry = FakeRegistry(schema_defaults={
            "seed": 42,
            "output_path": "/default/path",
        })
        resolved = resolve_configs(nodes, [], ["a"], None, registry)

        # output_path is user-set, should NOT be replaced
        cfg, src = resolved["a"]
        assert cfg["output_path"] == "/my/custom/path"
        assert src["output_path"] == "user"

        mock_manager = MagicMock()
        mock_manager.resolve_output_path.return_value = "/workspace/outputs"

        mock_ws_module = MagicMock()
        mock_ws_module.WorkspaceManager.return_value = mock_manager

        with patch(
            "backend.engine.config_resolver._get_workspace_settings",
            return_value=("/workspace", True),
        ), patch.dict(
            "sys.modules",
            {"backend.services.workspace_manager": mock_ws_module},
        ):
            file_path_registry = FakeRegistryWithFilePaths(schema_defaults={
                "seed": 42,
                "output_path": "/default/path",
            })
            inject_workspace_file_paths(resolved, nodes, file_path_registry)

        cfg, src = resolved["a"]
        assert cfg["output_path"] == "/my/custom/path"  # Still user's value
        assert src["output_path"] == "user"


class TestInjectWorkspaceFilePathsAutoFill:
    """Auto-fills block_default file_path fields with workspace paths."""

    def test_default_replaced_with_workspace(self):
        nodes = [_node("a", block_type="data_export", category="data")]
        registry = FakeRegistry(schema_defaults={
            "seed": 42,
            "output_path": "/default/path",
        })
        resolved = resolve_configs(nodes, [], ["a"], None, registry)

        # Verify it's at block_default
        cfg, src = resolved["a"]
        assert cfg["output_path"] == "/default/path"
        assert src["output_path"] == "block_default"

        mock_manager = MagicMock()
        mock_manager.resolve_output_path.return_value = "/workspace/outputs/exports"

        # Patch the lazy import inside inject_workspace_file_paths
        mock_ws_module = MagicMock()
        mock_ws_module.WorkspaceManager.return_value = mock_manager

        with patch(
            "backend.engine.config_resolver._get_workspace_settings",
            return_value=("/workspace", True),
        ), patch.dict(
            "sys.modules",
            {"backend.services.workspace_manager": mock_ws_module},
        ):
            file_path_registry = FakeRegistryWithFilePaths(schema_defaults={
                "seed": 42,
                "output_path": "/default/path",
            })
            inject_workspace_file_paths(resolved, nodes, file_path_registry)

        cfg, src = resolved["a"]
        assert cfg["output_path"] == "/workspace/outputs/exports"
        assert src["output_path"] == "workspace_auto_fill"


# ===========================================================================
# Workspace Config from Pipeline Definition
# ===========================================================================


class TestWorkspaceConfigFromDefinition:
    """workspace_config key in pipeline definition is properly used."""

    def test_definition_workspace_config_applied(self):
        """Simulate what the executor does: extract workspace_config from definition."""
        definition = {
            "nodes": [
                _node("a"),
                _node("b"),
            ],
            "edges": [_edge("a", "b")],
            "workspace_config": {"seed": 999, "text_column": "body"},
        }

        nodes = definition["nodes"]
        edges = definition["edges"]
        workspace_config = definition.get("workspace_config") or None
        order = ["a", "b"]
        registry = FakeRegistry()

        result = resolve_configs(nodes, edges, order, workspace_config, registry)

        for nid in ["a", "b"]:
            cfg, src = result[nid]
            assert cfg["seed"] == 999
            assert src["seed"] == "workspace"
            assert cfg["text_column"] == "body"
            assert src["text_column"] == "workspace"

    def test_missing_workspace_config_is_noop(self):
        """Definition without workspace_config uses defaults."""
        definition = {
            "nodes": [_node("a")],
            "edges": [],
        }

        nodes = definition["nodes"]
        edges = definition["edges"]
        workspace_config = definition.get("workspace_config") or None
        order = ["a"]
        registry = FakeRegistry()

        result = resolve_configs(nodes, edges, order, workspace_config, registry)

        cfg, src = result["a"]
        assert cfg["seed"] == 42  # block default
        assert src["seed"] == "block_default"
