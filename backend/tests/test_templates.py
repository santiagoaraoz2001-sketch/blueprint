"""Tests for the TemplateService and templates API router."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import BUILTIN_BLOCKS_DIR
from backend.services.registry import BlockRegistryService
from backend.services.templates import TemplateService, TEMPLATES_DIR
from backend.main import app

client = TestClient(app)


# ─── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def registry() -> BlockRegistryService:
    """Create a registry with builtin blocks discovered."""
    svc = BlockRegistryService()
    svc.discover_all([BUILTIN_BLOCKS_DIR])
    return svc


@pytest.fixture
def template_service(registry: BlockRegistryService) -> TemplateService:
    """Create a TemplateService with block validation enabled."""
    return TemplateService(registry=registry)


# ─── Template directory tests ────────────────────────────────────────

class TestTemplateFiles:
    """Verify template JSON files exist and are well-formed."""

    def test_templates_directory_exists(self):
        assert TEMPLATES_DIR.exists(), f"templates/ directory not found at {TEMPLATES_DIR}"

    def test_eight_template_files_exist(self):
        json_files = list(TEMPLATES_DIR.glob("*.json"))
        assert len(json_files) == 8, f"Expected 8 template files, found {len(json_files)}"

    def test_all_templates_are_valid_json(self):
        for path in TEMPLATES_DIR.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            assert "id" in data, f"{path.name} missing 'id'"
            assert "name" in data, f"{path.name} missing 'name'"
            assert "description" in data, f"{path.name} missing 'description'"
            assert "nodes" in data, f"{path.name} missing 'nodes'"
            assert "edges" in data, f"{path.name} missing 'edges'"

    def test_all_templates_have_required_fields(self):
        for path in TEMPLATES_DIR.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            assert data["difficulty"] in ("beginner", "intermediate", "advanced"), \
                f"{path.name}: invalid difficulty '{data.get('difficulty')}'"
            assert isinstance(data.get("estimated_runtime"), str), \
                f"{path.name}: missing or invalid estimated_runtime"
            assert isinstance(data.get("required_services"), list), \
                f"{path.name}: missing or invalid required_services"
            assert isinstance(data.get("required_capabilities"), list), \
                f"{path.name}: missing or invalid required_capabilities"

    def test_template_nodes_have_correct_structure(self):
        for path in TEMPLATES_DIR.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            for node in data["nodes"]:
                assert "id" in node, f"{path.name}: node missing 'id'"
                assert node.get("type") == "blockNode", \
                    f"{path.name}: node {node['id']} type should be 'blockNode'"
                assert "position" in node, f"{path.name}: node {node['id']} missing 'position'"
                nd = node.get("data", {})
                assert "type" in nd, f"{path.name}: node {node['id']} data missing 'type'"
                assert "label" in nd, f"{path.name}: node {node['id']} data missing 'label'"

    def test_template_edges_reference_valid_nodes(self):
        for path in TEMPLATES_DIR.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            node_ids = {n["id"] for n in data["nodes"]}
            for edge in data["edges"]:
                assert edge["source"] in node_ids, \
                    f"{path.name}: edge {edge['id']} references non-existent source {edge['source']}"
                assert edge["target"] in node_ids, \
                    f"{path.name}: edge {edge['id']} references non-existent target {edge['target']}"


# ─── Service-level tests ─────────────────────────────────────────────

class TestTemplateService:
    """Test TemplateService loading, validation, and instantiation."""

    def test_list_templates(self, template_service: TemplateService):
        templates = template_service.list_templates()
        assert len(templates) == 8

    def test_list_templates_returns_summaries(self, template_service: TemplateService):
        templates = template_service.list_templates()
        for tpl in templates:
            assert "id" in tpl
            assert "name" in tpl
            assert "description" in tpl
            assert "difficulty" in tpl
            assert "block_count" in tpl
            # Summaries should not contain full node data
            assert "nodes" not in tpl
            assert "edges" not in tpl

    def test_get_template(self, template_service: TemplateService):
        tpl = template_service.get_template("simple-chat")
        assert tpl is not None
        assert tpl["name"] == "Simple Chat"
        assert len(tpl["nodes"]) > 0

    def test_get_template_not_found(self, template_service: TemplateService):
        assert template_service.get_template("nonexistent") is None

    def test_validate_templates_against_registry(self, template_service: TemplateService):
        """All block types used in templates must exist in the block registry."""
        templates = template_service._load_templates()
        all_errors = []
        for tid, tpl in templates.items():
            errors = template_service.validate_template(tpl)
            if errors:
                all_errors.extend([f"{tid}: {e}" for e in errors])
        assert all_errors == [], f"Template validation errors:\n" + "\n".join(all_errors)

    def test_instantiate_creates_pipeline_data(self, template_service: TemplateService):
        result = template_service.instantiate("simple-chat")
        assert result is not None
        assert "name" in result
        assert "definition" in result
        defn = result["definition"]
        assert "nodes" in defn
        assert "edges" in defn
        assert len(defn["nodes"]) > 0

    def test_instantiate_generates_fresh_ids(self, template_service: TemplateService):
        result1 = template_service.instantiate("simple-chat")
        result2 = template_service.instantiate("simple-chat")
        ids1 = {n["id"] for n in result1["definition"]["nodes"]}
        ids2 = {n["id"] for n in result2["definition"]["nodes"]}
        # No overlap — fresh IDs each time
        assert ids1.isdisjoint(ids2), "Instantiated templates should have unique node IDs"

    def test_instantiate_remaps_edge_sources_targets(self, template_service: TemplateService):
        result = template_service.instantiate("simple-chat")
        defn = result["definition"]
        node_ids = {n["id"] for n in defn["nodes"]}
        for edge in defn["edges"]:
            assert edge["source"] in node_ids, f"Edge source {edge['source']} not in node IDs"
            assert edge["target"] in node_ids, f"Edge target {edge['target']} not in node IDs"

    def test_instantiate_not_found(self, template_service: TemplateService):
        assert template_service.instantiate("nonexistent") is None

    def test_cache_invalidation(self, template_service: TemplateService):
        # Load and cache
        templates1 = template_service.list_templates()
        # Invalidate
        template_service.invalidate_cache()
        # Should reload
        templates2 = template_service.list_templates()
        assert len(templates1) == len(templates2)


# ─── API-level tests ─────────────────────────────────────────────────

class TestTemplatesAPI:
    """Test template API endpoints."""

    def test_list_templates_endpoint(self):
        response = client.get("/api/templates")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 8

    def test_get_template_endpoint(self):
        response = client.get("/api/templates/simple-chat")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "simple-chat"
        assert "nodes" in data
        assert "edges" in data

    def test_get_template_not_found(self):
        response = client.get("/api/templates/nonexistent")
        assert response.status_code == 404

    def test_instantiate_endpoint(self):
        response = client.post("/api/templates/simple-chat/instantiate")
        assert response.status_code == 200
        data = response.json()
        assert "pipeline_id" in data
        assert "name" in data
        assert data["name"] == "Simple Chat"

    def test_instantiate_not_found(self):
        response = client.post("/api/templates/nonexistent/instantiate")
        assert response.status_code == 404

    def test_prerequisites_check_endpoint(self):
        response = client.get("/api/templates/prerequisites/check")
        assert response.status_code == 200
        data = response.json()
        assert "services" in data
        assert "capabilities" in data
        assert "ollama" in data["services"]
        assert "torch" in data["capabilities"]
        # Each entry should have the expected fields
        for entry in [data["services"]["ollama"], data["capabilities"]["torch"]]:
            assert "id" in entry
            assert "label" in entry
            assert "available" in entry
            assert isinstance(entry["available"], bool)
            assert "detail" in entry
