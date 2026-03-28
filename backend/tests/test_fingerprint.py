"""
Tests for Cache Fingerprints — deterministic Merkle-chain hashing.

4 required tests:
1. test_fingerprint_deterministic — same inputs produce same hash every time
2. test_fingerprint_changes_with_config — different seed = different fingerprint
3. test_fingerprint_cascades_downstream — change upstream config, downstream changes too
4. test_fingerprint_stable_across_runs — run computation twice with identical input, same result

Plus additional tests for:
- _extract_block_types helper
- groupNode skipping
"""

from typing import Any, Optional

import pytest

from backend.engine.fingerprint import compute_fingerprints, _extract_block_types


# ---------------------------------------------------------------------------
# Fake BlockRegistryService
# ---------------------------------------------------------------------------

class FakeRegistry:
    """Minimal stand-in for BlockRegistryService."""

    def __init__(self, version: str = "1.0.0"):
        self._version = version

    def get_block_version(self, block_type: str) -> str:
        return self._version

    def get_block_schema_defaults(self, block_type: str) -> dict[str, Any]:
        return {}

    def get_block_info(self, block_type: str) -> Optional[dict]:
        return {"type": block_type, "category": "data", "path": f"/fake/{block_type}"}

    def get_block_config_schema(self, block_type: str) -> dict[str, Any]:
        return {}

    def get_category(self, block_type: str) -> str:
        return "data"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_resolved(node_configs: dict[str, dict]) -> dict[str, tuple[dict, dict]]:
    """Build a nodes_resolved dict from simple {node_id: config} mapping."""
    return {
        nid: (cfg, {k: "user" for k in cfg})
        for nid, cfg in node_configs.items()
    }


def _node(node_id: str, block_type: str = "test_block", category: str = "data"):
    return {
        "id": node_id,
        "type": "customNode",
        "data": {"type": block_type, "category": category, "label": node_id, "config": {}},
    }


def _edge(source: str, target: str):
    return {"source": source, "target": target}


# ===========================================================================
# Required Tests
# ===========================================================================


class TestFingerprintDeterministic:
    """Same inputs produce the same hash every time."""

    def test_fingerprint_deterministic(self):
        nodes_resolved = _make_resolved({
            "a": {"seed": 42, "text_column": "text"},
            "b": {"seed": 42},
        })
        edges = [_edge("a", "b")]
        order = ["a", "b"]
        nodes = [_node("a", "loader"), _node("b", "processor")]
        registry = FakeRegistry()

        fp1 = compute_fingerprints(nodes_resolved, order, edges, registry, nodes)
        fp2 = compute_fingerprints(nodes_resolved, order, edges, registry, nodes)

        assert fp1["a"] == fp2["a"]
        assert fp1["b"] == fp2["b"]
        # Fingerprints should be valid hex SHA-256
        assert len(fp1["a"]) == 64
        assert all(c in "0123456789abcdef" for c in fp1["a"])


class TestFingerprintChangesWithConfig:
    """Different seed value produces a different fingerprint."""

    def test_fingerprint_changes_with_config(self):
        edges = []
        order = ["a"]
        nodes = [_node("a", "loader")]
        registry = FakeRegistry()

        resolved_a = _make_resolved({"a": {"seed": 42}})
        resolved_b = _make_resolved({"a": {"seed": 99}})

        fp_a = compute_fingerprints(resolved_a, order, edges, registry, nodes)
        fp_b = compute_fingerprints(resolved_b, order, edges, registry, nodes)

        assert fp_a["a"] != fp_b["a"]


class TestFingerprintCascadesDownstream:
    """Change upstream config — verify downstream fingerprints also change."""

    def test_fingerprint_cascades_downstream(self):
        edges = [_edge("a", "b"), _edge("b", "c")]
        order = ["a", "b", "c"]
        nodes = [_node("a", "loader"), _node("b", "processor"), _node("c", "exporter")]
        registry = FakeRegistry()

        resolved_v1 = _make_resolved({
            "a": {"seed": 42},
            "b": {"mode": "train"},
            "c": {"format": "csv"},
        })
        resolved_v2 = _make_resolved({
            "a": {"seed": 99},  # Only upstream changed
            "b": {"mode": "train"},
            "c": {"format": "csv"},
        })

        fp_v1 = compute_fingerprints(resolved_v1, order, edges, registry, nodes)
        fp_v2 = compute_fingerprints(resolved_v2, order, edges, registry, nodes)

        # Upstream changed → its fingerprint changes
        assert fp_v1["a"] != fp_v2["a"]
        # Downstream fingerprints must also change (Merkle cascade)
        assert fp_v1["b"] != fp_v2["b"]
        assert fp_v1["c"] != fp_v2["c"]


class TestFingerprintStableAcrossRuns:
    """Run the computation twice with identical input — same result."""

    def test_fingerprint_stable_across_runs(self):
        nodes_resolved = _make_resolved({
            "x": {"lr": 0.001, "epochs": 10},
            "y": {"batch_size": 32},
            "z": {"output_format": "json"},
        })
        edges = [_edge("x", "y"), _edge("y", "z")]
        order = ["x", "y", "z"]
        nodes = [_node("x", "trainer"), _node("y", "evaluator"), _node("z", "exporter")]
        registry = FakeRegistry()

        # Run 1
        fp_run1 = compute_fingerprints(nodes_resolved, order, edges, registry, nodes)
        # Run 2 — identical inputs
        fp_run2 = compute_fingerprints(nodes_resolved, order, edges, registry, nodes)

        assert fp_run1 == fp_run2
        for nid in ["x", "y", "z"]:
            assert fp_run1[nid] == fp_run2[nid]


# ===========================================================================
# Additional Tests
# ===========================================================================


class TestExtractBlockTypes:
    """_extract_block_types correctly maps node IDs to block types."""

    def test_basic_extraction(self):
        nodes = [_node("a", "loader"), _node("b", "processor")]
        result = _extract_block_types(nodes)
        assert result == {"a": "loader", "b": "processor"}

    def test_skips_group_nodes(self):
        nodes = [
            _node("a", "loader"),
            {"id": "g1", "type": "groupNode", "data": {}},
            _node("b", "processor"),
        ]
        result = _extract_block_types(nodes)
        assert "g1" not in result
        assert result == {"a": "loader", "b": "processor"}


class TestFingerprintVersionSensitivity:
    """Different block versions produce different fingerprints."""

    def test_version_changes_fingerprint(self):
        nodes_resolved = _make_resolved({"a": {"seed": 42}})
        edges = []
        order = ["a"]
        nodes = [_node("a", "loader")]

        fp_v1 = compute_fingerprints(nodes_resolved, order, edges, FakeRegistry("1.0.0"), nodes)
        fp_v2 = compute_fingerprints(nodes_resolved, order, edges, FakeRegistry("2.0.0"), nodes)

        assert fp_v1["a"] != fp_v2["a"]
