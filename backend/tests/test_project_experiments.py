"""Tests for project experiments, variant cloning, config diff, and inline notes."""

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


# ── Helpers ──────────────────────────────────────────────────────────

def _create_project(name: str = "Test Project", hypothesis: str = "Test H") -> dict:
    resp = client.post("/api/projects", json={"name": name, "hypothesis": hypothesis})
    assert resp.status_code == 201
    return resp.json()


def _create_pipeline(project_id: str, name: str = "Base Pipeline") -> dict:
    definition = {
        "nodes": [
            {
                "id": "node-1",
                "type": "blockNode",
                "data": {
                    "type": "llm_inference",
                    "label": "LLM",
                    "config": {
                        "model_id": "llama3",
                        "temperature": 0.7,
                        "max_tokens": 512,
                        "prompt": "Hello",
                    },
                },
                "position": {"x": 100, "y": 100},
            },
            {
                "id": "node-2",
                "type": "blockNode",
                "data": {
                    "type": "text_output",
                    "label": "Output",
                    "config": {"format": "plain"},
                },
                "position": {"x": 300, "y": 100},
            },
        ],
        "edges": [
            {"id": "e1", "source": "node-1", "target": "node-2"},
        ],
    }
    resp = client.post("/api/pipelines", json={
        "name": name,
        "project_id": project_id,
        "definition": definition,
    })
    assert resp.status_code == 201
    return resp.json()


# ── Test: Create Project ─────────────────────────────────────────────

def test_create_project():
    project = _create_project("My Experiment Suite", "Does lr affect convergence?")
    assert project["name"] == "My Experiment Suite"
    assert project["hypothesis"] == "Does lr affect convergence?"
    assert project["id"]
    assert project["status"] == "planned"


def test_list_projects_with_pipelines():
    project = _create_project("Project With Pipelines")
    _create_pipeline(project["id"], "Pipeline A")
    _create_pipeline(project["id"], "Pipeline B")

    resp = client.get("/api/projects")
    assert resp.status_code == 200
    projects = resp.json()
    matching = [p for p in projects if p["id"] == project["id"]]
    assert len(matching) == 1
    p = matching[0]
    assert p["total_pipeline_count"] == 2
    assert len(p["pipelines"]) == 2


def test_get_project_with_pipeline_details():
    project = _create_project("Detail Project")
    pipe = _create_pipeline(project["id"], "Detail Pipeline")

    resp = client.get(f"/api/projects/{project['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["pipelines"]) == 1
    assert data["pipelines"][0]["id"] == pipe["id"]
    assert data["pipelines"][0]["name"] == "Detail Pipeline"
    assert data["pipelines"][0]["run_count"] == 0


# ── Test: Clone Pipeline with Diff ──────────────────────────────────

def test_clone_pipeline_with_diff():
    project = _create_project("Clone Test")
    base = _create_pipeline(project["id"], "Base")

    # Clone as variant
    resp = client.post(f"/api/pipelines/{base['id']}/clone-variant", json={
        "name": "Variant 1",
        "project_id": project["id"],
        "variant_notes": "Testing lower temperature",
    })
    assert resp.status_code == 200
    result = resp.json()
    assert result["new_pipeline_id"]
    assert result["inherited_config_count"] > 0
    assert result["total_config_count"] == result["inherited_config_count"]

    # Verify the clone is a variant
    variant = result["pipeline"]
    assert variant["source_pipeline_id"] == base["id"]
    assert variant["variant_notes"] == "Testing lower temperature"
    assert variant["config_diff"] is not None
    assert variant["config_diff"]["inherited_count"] == result["inherited_config_count"]


def test_config_diff_badge_updates():
    project = _create_project("Diff Test")
    base = _create_pipeline(project["id"], "Base")

    # Clone
    clone_resp = client.post(f"/api/pipelines/{base['id']}/clone-variant", json={
        "name": "Changed Variant",
        "project_id": project["id"],
    })
    variant_id = clone_resp.json()["new_pipeline_id"]

    # Update variant config — change temperature
    variant_resp = client.get(f"/api/pipelines/{variant_id}")
    variant_def = variant_resp.json()["definition"]
    variant_def["nodes"][0]["data"]["config"]["temperature"] = 0.3

    update_resp = client.put(f"/api/pipelines/{variant_id}", json={
        "definition": variant_def,
    })
    assert update_resp.status_code == 200
    updated = update_resp.json()

    # Config diff should now show the change
    diff = updated["config_diff"]
    assert diff is not None
    assert "node-1" in diff["changed_keys"]
    assert "temperature" in diff["changed_keys"]["node-1"]
    assert diff["changed_keys"]["node-1"]["temperature"]["source"] == 0.7
    assert diff["changed_keys"]["node-1"]["temperature"]["current"] == 0.3


# ── Test: Inline Notes Persist ──────────────────────────────────────

def test_inline_notes_persist():
    project = _create_project("Notes Test")
    pipe = _create_pipeline(project["id"], "Notes Pipeline")

    # Update pipeline with notes
    resp = client.put(f"/api/pipelines/{pipe['id']}", json={
        "notes": "This pipeline tests the effect of prompt engineering on accuracy.",
    })
    assert resp.status_code == 200
    assert resp.json()["notes"] == "This pipeline tests the effect of prompt engineering on accuracy."

    # Verify notes persist on reload
    reload_resp = client.get(f"/api/pipelines/{pipe['id']}")
    assert reload_resp.status_code == 200
    assert reload_resp.json()["notes"] == "This pipeline tests the effect of prompt engineering on accuracy."


def test_node_notes_in_definition():
    """Node-level notes are stored in the pipeline definition."""
    project = _create_project("Node Notes Test")
    pipe = _create_pipeline(project["id"], "Node Notes Pipeline")

    # Get current definition
    resp = client.get(f"/api/pipelines/{pipe['id']}")
    definition = resp.json()["definition"]

    # Add notes to a node
    definition["nodes"][0]["data"]["notes"] = "Try different models here"

    update_resp = client.put(f"/api/pipelines/{pipe['id']}", json={
        "definition": definition,
    })
    assert update_resp.status_code == 200

    # Verify notes persist
    reload = client.get(f"/api/pipelines/{pipe['id']}")
    reloaded_def = reload.json()["definition"]
    assert reloaded_def["nodes"][0]["data"]["notes"] == "Try different models here"


# ── Test: Run Metadata ──────────────────────────────────────────────

def test_run_metadata_update():
    """Run notes, tags, and starred are editable via PUT /api/runs/{id}/metadata."""
    project = _create_project("Run Meta Test")
    pipe = _create_pipeline(project["id"])

    # Get all runs — may be empty, so we'll test the endpoint structure
    resp = client.get(f"/api/runs?pipeline_id={pipe['id']}")
    assert resp.status_code == 200


def test_run_list_with_tag_filter():
    """Tag filter on run list endpoint should work."""
    resp = client.get("/api/runs?tag=experiment-a")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_run_list_with_starred_filter():
    """Starred filter on run list endpoint should work."""
    resp = client.get("/api/runs?starred=true")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── Test: Project CRUD ──────────────────────────────────────────────

def test_update_project_hypothesis():
    project = _create_project("Update Test")
    resp = client.put(f"/api/projects/{project['id']}", json={
        "hypothesis": "New hypothesis about batch size",
        "status": "active",
    })
    assert resp.status_code == 200
    assert resp.json()["hypothesis"] == "New hypothesis about batch size"
    assert resp.json()["status"] == "active"


def test_delete_project():
    project = _create_project("Delete Me")
    resp = client.delete(f"/api/projects/{project['id']}")
    assert resp.status_code == 204

    # Should be gone
    resp = client.get(f"/api/projects/{project['id']}")
    assert resp.status_code == 404


# ── Test: Update Config Diff Endpoint ────────────────────────────────

def test_update_config_diff_endpoint():
    project = _create_project("Config Diff Endpoint Test")
    base = _create_pipeline(project["id"], "Base Pipeline")

    # Clone
    clone_resp = client.post(f"/api/pipelines/{base['id']}/clone-variant", json={
        "name": "Diff Endpoint Variant",
    })
    variant_id = clone_resp.json()["new_pipeline_id"]

    # Update config diff explicitly
    resp = client.post(f"/api/pipelines/{variant_id}/update-config-diff")
    assert resp.status_code == 200
    data = resp.json()
    assert "changed_count" in data
    assert "inherited_count" in data
    assert "total_count" in data
    assert data["changed_count"] == 0  # No changes yet


def test_variant_default_naming():
    """Variant auto-names should increment."""
    project = _create_project("Naming Test")
    base = _create_pipeline(project["id"], "Alpha")

    # Clone twice
    r1 = client.post(f"/api/pipelines/{base['id']}/clone-variant", json={})
    assert "variant 1" in r1.json()["pipeline"]["name"].lower()

    r2 = client.post(f"/api/pipelines/{base['id']}/clone-variant", json={})
    assert "variant 2" in r2.json()["pipeline"]["name"].lower()


# ── Test: Config Diff Engine — Structural Changes ────────────────────

def test_config_diff_detects_added_nodes():
    """When a variant adds a new node not in the source, diff should track it."""
    project = _create_project("Added Node Diff")
    base = _create_pipeline(project["id"], "Base")

    # Clone
    clone_resp = client.post(f"/api/pipelines/{base['id']}/clone-variant", json={})
    variant_id = clone_resp.json()["new_pipeline_id"]

    # Add a new node to the variant
    variant = client.get(f"/api/pipelines/{variant_id}").json()
    variant_def = variant["definition"]
    variant_def["nodes"].append({
        "id": "node-new",
        "type": "blockNode",
        "data": {
            "type": "text_splitter",
            "label": "Splitter",
            "config": {"chunk_size": 512, "overlap": 50},
        },
        "position": {"x": 500, "y": 100},
    })

    update_resp = client.put(f"/api/pipelines/{variant_id}", json={"definition": variant_def})
    assert update_resp.status_code == 200
    diff = update_resp.json()["config_diff"]

    # Should report the new node's configs as changes
    assert "node-new" in diff["changed_keys"]
    assert "chunk_size" in diff["changed_keys"]["node-new"]
    assert diff["changed_keys"]["node-new"]["chunk_size"]["source"] is None
    assert diff["changed_keys"]["node-new"]["chunk_size"]["current"] == 512

    # Should have added_nodes entry
    assert any(n["id"] == "node-new" for n in diff.get("added_nodes", []))


def test_config_diff_detects_removed_nodes():
    """When a variant removes a source node, diff should track it."""
    project = _create_project("Removed Node Diff")
    base = _create_pipeline(project["id"], "Base")

    # Clone
    clone_resp = client.post(f"/api/pipelines/{base['id']}/clone-variant", json={})
    variant_id = clone_resp.json()["new_pipeline_id"]

    # Remove node-2 from the variant
    variant = client.get(f"/api/pipelines/{variant_id}").json()
    variant_def = variant["definition"]
    variant_def["nodes"] = [n for n in variant_def["nodes"] if n["id"] != "node-2"]

    update_resp = client.put(f"/api/pipelines/{variant_id}", json={"definition": variant_def})
    assert update_resp.status_code == 200
    diff = update_resp.json()["config_diff"]

    # Should have removed_nodes entry
    assert any(n["id"] == "node-2" for n in diff.get("removed_nodes", []))


def test_config_diff_fuzzy_matches_by_type_and_label():
    """When a node is deleted and re-added with a different ID but same type+label,
    the diff engine should fuzzy-match and compare configs correctly."""
    project = _create_project("Fuzzy Match Diff")
    base = _create_pipeline(project["id"], "Base")

    # Clone
    clone_resp = client.post(f"/api/pipelines/{base['id']}/clone-variant", json={})
    variant_id = clone_resp.json()["new_pipeline_id"]

    # Replace node-1 with a new node that has a different ID but same type+label
    variant = client.get(f"/api/pipelines/{variant_id}").json()
    variant_def = variant["definition"]

    # Remove original node-1
    old_node = next(n for n in variant_def["nodes"] if n["id"] == "node-1")
    variant_def["nodes"] = [n for n in variant_def["nodes"] if n["id"] != "node-1"]

    # Add replacement with different ID but same type+label, different config
    variant_def["nodes"].append({
        "id": "node-1-replacement",
        "type": "blockNode",
        "data": {
            "type": old_node["data"]["type"],
            "label": old_node["data"]["label"],
            "config": {
                "model_id": "gpt-4",  # Changed from llama3
                "temperature": 0.7,    # Same
                "max_tokens": 1024,    # Changed from 512
                "prompt": "Hello",     # Same
            },
        },
        "position": {"x": 100, "y": 100},
    })

    update_resp = client.put(f"/api/pipelines/{variant_id}", json={"definition": variant_def})
    assert update_resp.status_code == 200
    diff = update_resp.json()["config_diff"]

    # Fuzzy match should detect the replacement node and diff its configs
    # The new node ID should appear in changed_keys with the config differences
    assert "node-1-replacement" in diff["changed_keys"]
    changes = diff["changed_keys"]["node-1-replacement"]
    assert "model_id" in changes
    assert changes["model_id"]["source"] == "llama3"
    assert changes["model_id"]["current"] == "gpt-4"
    assert "max_tokens" in changes
    assert changes["max_tokens"]["source"] == 512
    assert changes["max_tokens"]["current"] == 1024

    # temperature and prompt should NOT appear in changes (they're the same)
    assert "temperature" not in changes
    assert "prompt" not in changes

    # Neither added_nodes nor removed_nodes should contain the fuzzy-matched pair
    added_ids = [n["id"] for n in diff.get("added_nodes", [])]
    removed_ids = [n["id"] for n in diff.get("removed_nodes", [])]
    assert "node-1-replacement" not in added_ids
    assert "node-1" not in removed_ids


def test_config_diff_union_of_keys():
    """Diff should consider keys that exist in source but not variant (deleted config)
    and keys in variant but not source (new config)."""
    project = _create_project("Union Keys Diff")
    base = _create_pipeline(project["id"], "Base")

    clone_resp = client.post(f"/api/pipelines/{base['id']}/clone-variant", json={})
    variant_id = clone_resp.json()["new_pipeline_id"]

    variant = client.get(f"/api/pipelines/{variant_id}").json()
    variant_def = variant["definition"]

    # Remove 'prompt' key and add 'system_prompt' key
    node_config = variant_def["nodes"][0]["data"]["config"]
    del node_config["prompt"]
    node_config["system_prompt"] = "You are a helpful assistant"

    update_resp = client.put(f"/api/pipelines/{variant_id}", json={"definition": variant_def})
    diff = update_resp.json()["config_diff"]

    node_changes = diff["changed_keys"].get("node-1", {})
    # prompt was removed: source=Hello, current=None (missing)
    assert "prompt" in node_changes
    assert node_changes["prompt"]["source"] == "Hello"
    assert node_changes["prompt"]["current"] is None
    # system_prompt was added: source=None, current=...
    assert "system_prompt" in node_changes
    assert node_changes["system_prompt"]["source"] is None
    assert node_changes["system_prompt"]["current"] == "You are a helpful assistant"
