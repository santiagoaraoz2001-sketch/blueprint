"""Tests for the presets API router and config validation endpoint.

Uses the ``test_client`` fixture from conftest.py which provides an
isolated in-memory database — no mutations reach the user's real DB.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestPresetsAPI:
    """CRUD operations on the /api/presets endpoint."""

    def test_list_presets_includes_builtins(self, test_client):
        resp = test_client.get("/api/presets?block_type=lora_finetuning")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        builtin_names = [p["name"] for p in data if p.get("builtin")]
        assert "Quick Test" in builtin_names
        assert "Production" in builtin_names
        assert "Memory-Efficient" in builtin_names

    def test_list_all_presets(self, test_client):
        resp = test_client.get("/api/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 5  # At least the built-in presets

    def test_builtin_presets_have_valid_config(self, test_client):
        """Every built-in preset must have parseable JSON config."""
        resp = test_client.get("/api/presets")
        for preset in resp.json():
            if preset.get("builtin"):
                config = json.loads(preset["config_json"])
                assert isinstance(config, dict), f"Preset {preset['name']} config is not a dict"
                assert len(config) > 0, f"Preset {preset['name']} config is empty"

    def test_create_preset(self, test_client):
        payload = {
            "block_type": "test_block",
            "name": "My Test Preset",
            "config_json": json.dumps({"lr": 0.001, "epochs": 5}),
        }
        resp = test_client.post("/api/presets", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "My Test Preset"
        assert data["block_type"] == "test_block"
        assert data["builtin"] is False
        assert "id" in data

    def test_create_preset_invalid_json(self, test_client):
        payload = {
            "block_type": "test_block",
            "name": "Bad Preset",
            "config_json": "not valid json{{{",
        }
        resp = test_client.post("/api/presets", json=payload)
        assert resp.status_code == 400

    def test_delete_preset(self, test_client):
        # Create one first
        payload = {
            "block_type": "test_block",
            "name": "To Delete",
            "config_json": json.dumps({"x": 1}),
        }
        create_resp = test_client.post("/api/presets", json=payload)
        assert create_resp.status_code == 200
        preset_id = create_resp.json()["id"]

        # Delete it
        resp = test_client.delete(f"/api/presets/{preset_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_builtin_fails(self, test_client):
        resp = test_client.delete("/api/presets/builtin-lora-quick-test")
        assert resp.status_code == 400

    def test_delete_nonexistent(self, test_client):
        resp = test_client.delete("/api/presets/99999")
        assert resp.status_code == 404

    def test_preset_round_trip(self, test_client):
        """Create a preset, list it, verify config matches."""
        config = {"r": 8, "alpha": 16, "lr": 1e-4}
        payload = {
            "block_type": "lora_finetuning",
            "name": "Round Trip Test",
            "config_json": json.dumps(config),
        }
        create_resp = test_client.post("/api/presets", json=payload)
        assert create_resp.status_code == 200

        # List and find our preset
        list_resp = test_client.get("/api/presets?block_type=lora_finetuning")
        data = list_resp.json()
        our_preset = next((p for p in data if p["name"] == "Round Trip Test"), None)
        assert our_preset is not None
        stored_config = json.loads(our_preset["config_json"])
        assert stored_config["r"] == 8
        assert stored_config["alpha"] == 16

    def test_filter_by_block_type_excludes_others(self, test_client):
        """Filtering by block_type should not return presets for other types."""
        # Create a preset for a unique block type
        test_client.post("/api/presets", json={
            "block_type": "unique_test_block_xyz",
            "name": "Unique",
            "config_json": json.dumps({"x": 1}),
        })

        # List for a different type — should not include the one we just made
        resp = test_client.get("/api/presets?block_type=lora_finetuning")
        names = [p["name"] for p in resp.json()]
        assert "Unique" not in names


class TestValidateConfig:
    """Server-side cross-field config validation via /api/registry/validate-config."""

    def test_validate_config_returns_failures(self, test_client):
        resp = test_client.post("/api/registry/validate-config", json={
            "block_type": "lora_finetuning",
            "config": {"batch_size": 200, "epochs": 100, "r": 128, "lr": 0.005, "alpha": 1},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 2  # product_lte + lte failures at minimum
        messages = [r["message"] for r in data]
        assert any("training times" in m.lower() or "batch" in m.lower() for m in messages)
        assert any("rank" in m.lower() or "lora" in m.lower() for m in messages)

    def test_validate_config_all_pass(self, test_client):
        resp = test_client.post("/api/registry/validate-config", json={
            "block_type": "lora_finetuning",
            "config": {"batch_size": 4, "epochs": 3, "r": 16, "lr": 0.0001, "alpha": 32},
        })
        assert resp.status_code == 200
        assert resp.json() == []

    def test_validate_config_unknown_block(self, test_client):
        resp = test_client.post("/api/registry/validate-config", json={
            "block_type": "nonexistent_block",
            "config": {},
        })
        assert resp.status_code == 404

    def test_validate_config_block_without_rules(self, test_client):
        """Blocks without config_validation should return empty list."""
        resp = test_client.post("/api/registry/validate-config", json={
            "block_type": "data_export",
            "config": {"format": "csv"},
        })
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert resp.json() == []

    def test_validate_returns_severity_levels(self, test_client):
        """Validation results should include correct severity levels."""
        resp = test_client.post("/api/registry/validate-config", json={
            "block_type": "lora_finetuning",
            "config": {"batch_size": 200, "epochs": 100, "r": 128, "lr": 0.005, "alpha": 32},
        })
        assert resp.status_code == 200
        data = resp.json()
        severities = {r["severity"] for r in data}
        # All our LoRA rules are 'warning' severity (alpha >= 1 passes with alpha=32)
        assert "warning" in severities

    def test_validate_returns_affected_fields(self, test_client):
        """Each result should list the fields it applies to."""
        resp = test_client.post("/api/registry/validate-config", json={
            "block_type": "lora_finetuning",
            "config": {"batch_size": 200, "epochs": 100},
        })
        assert resp.status_code == 200
        data = resp.json()
        for result in data:
            assert "fields" in result
            assert isinstance(result["fields"], list)
            assert len(result["fields"]) > 0
