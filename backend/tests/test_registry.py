"""Tests for the BlockRegistryService and the registry API router."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import BUILTIN_BLOCKS_DIR
from backend.models.block_schema import BlockSchema
from backend.services.registry import BlockRegistryService
from backend.main import app


# ─── Service-level tests ─────────────────────────────────────────────

@pytest.fixture
def registry() -> BlockRegistryService:
    """Create a registry with only builtin blocks discovered."""
    svc = BlockRegistryService()
    svc.discover_all([BUILTIN_BLOCKS_DIR])
    return svc


def _count_block_yamls(base: Path) -> int:
    """Count block.yaml files under a directory (matches `find blocks -name block.yaml | wc -l`)."""
    count = 0
    for category_dir in base.iterdir():
        if not category_dir.is_dir() or category_dir.name.startswith((".", "_")):
            continue
        for block_dir in category_dir.iterdir():
            if not block_dir.is_dir() or block_dir.name.startswith((".", "_")):
                continue
            if (block_dir / "block.yaml").exists():
                count += 1
    return count


class TestDiscovery:
    def test_discovers_all_builtin_blocks(self, registry: BlockRegistryService):
        """Registry should discover exactly as many blocks as there are block.yaml files."""
        expected = _count_block_yamls(BUILTIN_BLOCKS_DIR)
        actual = len(registry.list_all())
        assert actual == expected, (
            f"Expected {expected} blocks from block.yaml scan, got {actual}"
        )

    def test_schema_required_fields(self, registry: BlockRegistryService):
        """Every discovered block must have block_type, category, and at least one port."""
        for block in registry.list_all():
            assert block.block_type, f"Block missing block_type: {block}"
            assert block.category, f"Block {block.block_type} missing category"
            has_ports = bool(block.inputs) or bool(block.outputs)
            if block.maturity != "broken":
                assert has_ports, f"Block {block.block_type} has no inputs or outputs"

    def test_version_is_set(self, registry: BlockRegistryService):
        """Every valid block should have a non-empty version."""
        for block in registry.list_all():
            if block.maturity != "broken":
                assert block.version, f"Block {block.block_type} has no version"


class TestLookups:
    def test_get_existing_block(self, registry: BlockRegistryService):
        block = registry.get("train_val_test_split")
        assert block is not None
        assert block.category == "data"
        assert block.label == "Train/Val/Test Split"

    def test_nonexistent_block_returns_none(self, registry: BlockRegistryService):
        assert registry.get("__nonexistent_block_type__") is None

    def test_list_by_category(self, registry: BlockRegistryService):
        data_blocks = registry.list_all(category="data")
        assert len(data_blocks) > 0
        assert all(b.category == "data" for b in data_blocks)

    def test_health_report_accurate(self, registry: BlockRegistryService):
        health = registry.get_health()
        assert health["total"] == len(registry.list_all())
        assert health["valid"] == health["total"] - health["broken"]
        assert health["version"] >= 1


class TestPortCompatibility:
    def test_compatible_connection(self, registry: BlockRegistryService):
        """model -> llm should be allowed (per the compatibility matrix)."""
        assert registry.is_port_compatible("model", "llm") is True

    def test_incompatible_connection(self, registry: BlockRegistryService):
        """text -> model should NOT be allowed."""
        assert registry.is_port_compatible("text", "model") is False

    def test_any_accepts_everything(self, registry: BlockRegistryService):
        """'any' source should connect to any target."""
        for target in ["dataset", "text", "model", "config", "metrics", "embedding", "artifact", "agent", "llm"]:
            assert registry.is_port_compatible("any", target), f"any -> {target} should be valid"

    def test_everything_connects_to_any(self, registry: BlockRegistryService):
        """Every type should be able to connect to 'any'."""
        for source in ["dataset", "text", "model", "config", "metrics", "embedding", "artifact", "agent", "llm"]:
            assert registry.is_port_compatible(source, "any"), f"{source} -> any should be valid"

    def test_alias_resolution(self, registry: BlockRegistryService):
        """Legacy aliases like 'data' -> 'dataset' should work."""
        assert registry.is_port_compatible("data", "dataset") is True
        assert registry.is_port_compatible("llm_config", "llm") is True

    def test_validate_connection_with_real_blocks(self, registry: BlockRegistryService):
        """validate_connection should work with actual block types and port IDs."""
        # train_val_test_split outputs 'train' (dataset) -> lora_finetuning input 'dataset' (dataset)
        result = registry.validate_connection(
            "train_val_test_split", "train",
            "lora_finetuning", "dataset",
        )
        assert result["valid"] is True

    def test_validate_connection_incompatible(self, registry: BlockRegistryService):
        """validate_connection should reject incompatible port connections."""
        # train_val_test_split outputs 'stats' (metrics) -> lora_finetuning input 'model' (model)
        result = registry.validate_connection(
            "train_val_test_split", "stats",
            "lora_finetuning", "model",
        )
        assert result["valid"] is False
        assert result["error"] is not None

    def test_validate_connection_unknown_block(self, registry: BlockRegistryService):
        result = registry.validate_connection(
            "__fake__", "out", "lora_finetuning", "dataset",
        )
        assert result["valid"] is False
        assert "Unknown source block" in result["error"]


class TestAppImport:
    def test_app_import_succeeds(self):
        """Verify `from backend.main import app` works (registry loads)."""
        from backend.main import app
        assert app is not None
        assert app.title == "Blueprint API"


# ─── API-level tests (registry router) ───────────────────────────────

client = TestClient(app)


def test_api_list_blocks():
    response = client.get("/api/registry/blocks")
    assert response.status_code == 200
    blocks = response.json()
    assert isinstance(blocks, list)
    assert len(blocks) > 0
    block = blocks[0]
    assert "type" in block
    assert "name" in block
    assert "category" in block
    assert "inputs" in block
    assert "outputs" in block
    assert "configFields" in block


def test_api_list_blocks_by_category():
    response = client.get("/api/registry/blocks?category=agents")
    assert response.status_code == 200
    blocks = response.json()
    assert all(b["category"] == "agents" for b in blocks)


def test_api_get_single_block():
    list_resp = client.get("/api/registry/blocks")
    blocks = list_resp.json()
    block_type = blocks[0]["type"]

    response = client.get(f"/api/registry/blocks/{block_type}")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == block_type


def test_api_get_unknown_block_404():
    response = client.get("/api/registry/blocks/nonexistent_block_xyz")
    assert response.status_code == 404


def test_api_registry_version():
    response = client.get("/api/registry/version")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert isinstance(data["version"], int)
    assert data["version"] >= 1


def test_api_validate_connection_compatible():
    response = client.post("/api/registry/validate-connection", json={
        "src_type": "text_block",
        "src_port": "dataset",
        "dst_type": "other_block",
        "dst_port": "text",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["error"] is None


def test_api_validate_connection_incompatible():
    response = client.post("/api/registry/validate-connection", json={
        "src_type": "text_block",
        "src_port": "agent",
        "dst_type": "other_block",
        "dst_port": "model",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["error"] is not None


def test_api_registry_health():
    response = client.get("/api/registry/health")
    assert response.status_code == 200
    data = response.json()
    assert "total_blocks" in data
    assert "categories" in data
    assert "broken_blocks" in data
    assert data["total_blocks"] > 0


def test_api_refresh_registry():
    response = client.post("/api/registry/refresh")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert data["version"] >= 1
