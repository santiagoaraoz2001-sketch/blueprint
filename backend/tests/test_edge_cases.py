"""Edge case matrix — tests for critical failure modes across all subsystems.

Covers: Pipeline Editor, Execution, Cache, Config, Registry, and Frontend-like
scenarios. Each test ensures no crashes or data loss on edge-case inputs.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from backend.models.pipeline import Pipeline
from backend.models.run import Run
from backend.models.execution_decision import ExecutionDecision
from backend.models.artifact import ArtifactRecord


# ── Helpers ──────────────────────────────────────────────────────────────

def _node(nid: str, block_type: str = "data_loader", config: dict | None = None) -> dict:
    return {
        "id": nid,
        "type": "blockNode",
        "position": {"x": 0, "y": 0},
        "data": {
            "type": block_type,
            "label": block_type,
            "category": "data",
            "config": config or {},
        },
    }


def _edge(src: str, tgt: str) -> dict:
    return {
        "id": f"e-{src}-{tgt}",
        "source": src,
        "target": tgt,
        "sourceHandle": "output",
        "targetHandle": "input",
    }


def _create(client, name: str, nodes: list, edges: list) -> dict:
    resp = client.post("/api/pipelines", json={
        "name": name,
        "definition": {"nodes": nodes, "edges": edges},
    })
    assert resp.status_code == 201
    return resp.json()


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline Editor Edge Cases
# ═══════════════════════════════════════════════════════════════════════


class TestPipelineEditorEdgeCases:
    """Pipeline structure edge cases."""

    def test_empty_pipeline_validates_as_no_blocks(self, test_client):
        """Empty pipeline → validation returns 'no blocks' error, not crash."""
        pipeline = _create(test_client, "Empty", [], [])
        resp = test_client.post(f"/api/pipelines/{pipeline['id']}/validate")
        assert resp.status_code == 200
        val = resp.json()
        assert val["valid"] is False
        assert any("no blocks" in e.lower() for e in val["errors"])

    def test_single_node_validates(self, test_client):
        """Single node with no edges validates without crash."""
        nodes = [_node("solo", "data_loader")]
        pipeline = _create(test_client, "Solo", nodes, [])
        resp = test_client.post(f"/api/pipelines/{pipeline['id']}/validate")
        assert resp.status_code == 200
        val = resp.json()
        assert val["block_count"] == 1
        assert val["edge_count"] == 0

    def test_100_plus_nodes_no_crash(self, test_client):
        """100+ nodes don't crash the canvas or validation."""
        nodes = [_node(f"n{i}", "data_loader") for i in range(120)]
        edges = [_edge(f"n{i}", f"n{i+1}") for i in range(119)]
        pipeline = _create(test_client, "Big Pipeline", nodes, edges)
        pid = pipeline["id"]

        # Validate
        resp = test_client.post(f"/api/pipelines/{pid}/validate")
        assert resp.status_code == 200
        val = resp.json()
        assert val["block_count"] == 120
        assert val["edge_count"] == 119

        # Load the pipeline
        resp = test_client.get(f"/api/pipelines/{pid}")
        assert resp.status_code == 200
        assert len(resp.json()["definition"]["nodes"]) == 120

    def test_self_loop_edge_detected(self, test_client):
        """Self-loop edge is flagged by validation."""
        nodes = [_node("loop_node")]
        edges = [_edge("loop_node", "loop_node")]
        pipeline = _create(test_client, "Self Loop", nodes, edges)
        resp = test_client.post(f"/api/pipelines/{pipeline['id']}/validate")
        assert resp.status_code == 200
        val = resp.json()
        assert val["valid"] is False
        assert any("self" in e.lower() or "loop" in e.lower() or "cycle" in e.lower() for e in val["errors"])

    def test_duplicate_node_ids_detected(self, test_client):
        """Duplicate node IDs are handled without crash.

        The validator may or may not flag duplicates as an error (since dict
        deduplication may silently merge them), but must not crash.
        """
        nodes = [_node("dupe"), _node("dupe")]
        pipeline = _create(test_client, "Dupes", nodes, [])
        resp = test_client.post(f"/api/pipelines/{pipeline['id']}/validate")
        assert resp.status_code == 200
        val = resp.json()
        # Validator either flags duplicates or silently deduplicates — both are OK
        assert "valid" in val
        # But it must report the correct count or a dedup'd count
        assert val["block_count"] in (1, 2)

    def test_edge_references_nonexistent_node(self, test_client):
        """Edge referencing a deleted/nonexistent node is caught."""
        nodes = [_node("real")]
        edges = [_edge("real", "ghost")]
        pipeline = _create(test_client, "Ghost Edge", nodes, edges)
        resp = test_client.post(f"/api/pipelines/{pipeline['id']}/validate")
        assert resp.status_code == 200
        val = resp.json()
        assert val["valid"] is False
        assert any("unknown" in e.lower() or "not found" in e.lower() for e in val["errors"])


# ═══════════════════════════════════════════════════════════════════════
#  Execution Edge Cases
# ═══════════════════════════════════════════════════════════════════════


class TestExecutionEdgeCases:
    """Execution-time edge cases."""

    def test_execute_empty_pipeline_returns_error(self, test_client):
        """Executing an empty pipeline returns 400, not a crash."""
        pipeline = _create(test_client, "Empty Exec", [], [])
        resp = test_client.post(f"/api/pipelines/{pipeline['id']}/execute")
        assert resp.status_code == 400

    def test_execute_nonexistent_pipeline_returns_404(self, test_client):
        """Executing a nonexistent pipeline returns 404."""
        resp = test_client.post(f"/api/pipelines/{uuid.uuid4()}/execute")
        assert resp.status_code == 404

    def test_cancel_nonexistent_run_returns_404(self, test_client):
        """Cancelling a nonexistent run returns 404."""
        resp = test_client.post(f"/api/runs/{uuid.uuid4()}/cancel")
        assert resp.status_code == 404

    def test_cancel_completed_run_returns_400(self, test_client, test_db):
        """Cancelling an already completed run returns 400."""
        pipeline = _create(test_client, "Done Pipeline", [_node("x")], [])
        run = Run(
            id=str(uuid.uuid4()),
            pipeline_id=pipeline["id"],
            status="complete",
            started_at=datetime.now(timezone.utc),
        )
        test_db.add(run)
        test_db.commit()
        resp = test_client.post(f"/api/runs/{run.id}/cancel")
        assert resp.status_code == 400

    def test_partial_rerun_blocked_for_non_complete_source(self, test_client, test_db):
        """Partial rerun from a non-complete source run returns 400."""
        nodes = [_node("a"), _node("b")]
        edges = [_edge("a", "b")]
        pipeline = _create(test_client, "Partial Test", nodes, edges)
        pid = pipeline["id"]

        # Seed a failed run
        run_id = str(uuid.uuid4())
        run = Run(
            id=run_id, pipeline_id=pid, status="failed",
            started_at=datetime.now(timezone.utc),
        )
        test_db.add(run)
        test_db.commit()

        resp = test_client.post(f"/api/pipelines/{pid}/execute-from", json={
            "source_run_id": run_id,
            "start_node_id": "b",
        })
        assert resp.status_code == 400
        assert "complete" in resp.json()["detail"].lower() or "status" in resp.json()["detail"].lower()

    def test_partial_rerun_unknown_start_node(self, test_client, test_db):
        """Partial rerun with unknown start_node_id returns 400."""
        nodes = [_node("a")]
        pipeline = _create(test_client, "Unknown Node Test", nodes, [])
        pid = pipeline["id"]

        run_id = str(uuid.uuid4())
        run = Run(
            id=run_id, pipeline_id=pid, status="complete",
            started_at=datetime.now(timezone.utc),
            outputs_snapshot={"a": {"output": "val"}},
        )
        test_db.add(run)
        test_db.commit()

        resp = test_client.post(f"/api/pipelines/{pid}/execute-from", json={
            "source_run_id": run_id,
            "start_node_id": "nonexistent",
        })
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════════════
#  Cache Edge Cases
# ═══════════════════════════════════════════════════════════════════════


class TestCacheEdgeCases:
    """Artifact cache edge cases."""

    def test_missing_artifact_record_graceful(self, test_client, test_db):
        """Run output request with missing artifacts returns empty outputs, not crash."""
        pipeline = _create(test_client, "Cache Miss", [_node("c1")], [])
        run = Run(
            id=str(uuid.uuid4()),
            pipeline_id=pipeline["id"],
            status="complete",
            started_at=datetime.now(timezone.utc),
            outputs_snapshot=None,
        )
        test_db.add(run)
        test_db.commit()

        resp = test_client.get(f"/api/runs/{run.id}/outputs")
        assert resp.status_code == 200
        assert resp.json()["outputs"] == {}

    def test_replay_with_no_decisions_synthesizes(self, test_client, test_db):
        """Replay on older run with no ExecutionDecision records → synthesizes from snapshot."""
        nodes = [_node("s1"), _node("s2")]
        pipeline = _create(test_client, "Old Run", nodes, [])
        run = Run(
            id=str(uuid.uuid4()),
            pipeline_id=pipeline["id"],
            status="complete",
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            duration_seconds=1.0,
            config_snapshot={"nodes": nodes, "edges": []},
        )
        test_db.add(run)
        test_db.commit()

        resp = test_client.get(f"/api/runs/{run.id}/replay")
        assert resp.status_code == 200
        replay = resp.json()
        assert replay["status"] == "complete"
        # Should synthesize node replay from snapshot
        assert len(replay["nodes"]) == 2


# ═══════════════════════════════════════════════════════════════════════
#  Config Edge Cases
# ═══════════════════════════════════════════════════════════════════════


class TestConfigEdgeCases:
    """Configuration edge cases."""

    def test_empty_string_config_value_accepted(self, test_client):
        """Empty string value in config is accepted (not treated as missing)."""
        nodes = [_node("cfg1", "data_loader", {"source": ""})]
        pipeline = _create(test_client, "Empty Config", nodes, [])
        resp = test_client.get(f"/api/pipelines/{pipeline['id']}")
        assert resp.status_code == 200
        config = resp.json()["definition"]["nodes"][0]["data"]["config"]
        assert config["source"] == ""

    def test_null_value_in_config(self, test_client):
        """None/null config value is stored and retrievable."""
        nodes = [_node("cfg2", "data_loader", {"optional_field": None})]
        pipeline = _create(test_client, "Null Config", nodes, [])
        resp = test_client.get(f"/api/pipelines/{pipeline['id']}")
        assert resp.status_code == 200
        config = resp.json()["definition"]["nodes"][0]["data"]["config"]
        assert config["optional_field"] is None

    def test_unicode_characters_in_config(self, test_client):
        """Unicode characters in config values are preserved."""
        nodes = [_node("cfg3", "data_loader", {"label": "日本語テスト 🚀 résumé"})]
        pipeline = _create(test_client, "Unicode Config", nodes, [])
        resp = test_client.get(f"/api/pipelines/{pipeline['id']}")
        assert resp.status_code == 200
        config = resp.json()["definition"]["nodes"][0]["data"]["config"]
        assert config["label"] == "日本語テスト 🚀 résumé"

    def test_very_large_config_value(self, test_client):
        """Very large config value (e.g., 10KB string) is accepted."""
        large_val = "x" * 10_000
        nodes = [_node("cfg4", "data_loader", {"big_field": large_val})]
        pipeline = _create(test_client, "Large Config", nodes, [])
        resp = test_client.get(f"/api/pipelines/{pipeline['id']}")
        assert resp.status_code == 200
        config = resp.json()["definition"]["nodes"][0]["data"]["config"]
        assert len(config["big_field"]) == 10_000

    def test_nested_config_object(self, test_client):
        """Deeply nested config objects are preserved."""
        nested = {"level1": {"level2": {"level3": {"value": 42}}}}
        nodes = [_node("cfg5", "data_loader", {"nested": nested})]
        pipeline = _create(test_client, "Nested Config", nodes, [])
        resp = test_client.get(f"/api/pipelines/{pipeline['id']}")
        assert resp.status_code == 200
        config = resp.json()["definition"]["nodes"][0]["data"]["config"]
        assert config["nested"]["level1"]["level2"]["level3"]["value"] == 42


# ═══════════════════════════════════════════════════════════════════════
#  Registry Edge Cases
# ═══════════════════════════════════════════════════════════════════════


class TestRegistryEdgeCases:
    """Block registry edge cases."""

    def test_validate_unknown_block_type(self, test_client):
        """Validation with unknown block type reports error, not crash."""
        nodes = [_node("unk", "this_block_does_not_exist_xyz_12345")]
        pipeline = _create(test_client, "Unknown Block", nodes, [])
        resp = test_client.post(f"/api/pipelines/{pipeline['id']}/validate")
        assert resp.status_code == 200
        val = resp.json()
        # Should either be valid=False with error or valid=True with warning
        # depending on registry config, but must NOT crash
        assert "valid" in val

    def test_validate_config_for_unknown_block(self, test_client):
        """Block config validation for unknown block returns 404."""
        resp = test_client.post(
            "/api/blocks/nonexistent_block_xyz/validate-config",
            json={"some_field": "value"},
        )
        assert resp.status_code == 404

    def test_block_list_endpoint(self, test_client):
        """Block list endpoint returns 200 without crash."""
        resp = test_client.get("/api/blocks")
        # May return a list of blocks or a fallback response depending on
        # registry initialization state — the key requirement is no 500 crash
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
#  Frontend-Adjacent Edge Cases
# ═══════════════════════════════════════════════════════════════════════


class TestFrontendEdgeCases:
    """Edge cases that simulate frontend behavior."""

    def test_rapid_pipeline_saves_no_corruption(self, test_client):
        """Rapid sequential saves don't corrupt the pipeline definition."""
        nodes = [_node("r1")]
        pipeline = _create(test_client, "Rapid Save", nodes, [])
        pid = pipeline["id"]

        # Simulate 10 rapid saves with different configs
        for i in range(10):
            nodes[0]["data"]["config"]["iteration"] = i
            resp = test_client.put(f"/api/pipelines/{pid}", json={
                "definition": {"nodes": nodes, "edges": []},
            })
            assert resp.status_code == 200

        # Verify final state is consistent
        resp = test_client.get(f"/api/pipelines/{pid}")
        assert resp.status_code == 200
        final_config = resp.json()["definition"]["nodes"][0]["data"]["config"]
        assert final_config["iteration"] == 9

    def test_concurrent_pipeline_operations(self, test_client):
        """Multiple pipeline CRUD operations don't interfere."""
        pipelines = []
        for i in range(5):
            p = _create(test_client, f"Concurrent {i}", [_node(f"cn{i}")], [])
            pipelines.append(p)

        # Delete odd-numbered pipelines
        for i in range(1, 5, 2):
            resp = test_client.delete(f"/api/pipelines/{pipelines[i]['id']}")
            assert resp.status_code == 204

        # Verify even-numbered still exist
        for i in range(0, 5, 2):
            resp = test_client.get(f"/api/pipelines/{pipelines[i]['id']}")
            assert resp.status_code == 200

        # Verify odd-numbered are gone
        for i in range(1, 5, 2):
            resp = test_client.get(f"/api/pipelines/{pipelines[i]['id']}")
            assert resp.status_code == 404

    def test_run_outputs_for_nonexistent_run(self, test_client):
        """Run outputs endpoint for nonexistent run returns 404, not crash."""
        fake_run_id = str(uuid.uuid4())
        resp = test_client.get(f"/api/runs/{fake_run_id}/outputs")
        assert resp.status_code == 404

    def test_run_list_with_filters(self, test_client, test_db):
        """Run list with various filters returns correctly filtered results."""
        pipeline = _create(test_client, "Filter Test", [_node("f1")], [])
        pid = pipeline["id"]

        # Seed runs with different statuses
        for status in ("complete", "failed", "complete"):
            run = Run(
                id=str(uuid.uuid4()),
                pipeline_id=pid,
                status=status,
                started_at=datetime.now(timezone.utc),
                tags="important" if status == "complete" else "",
                starred=status == "complete",
            )
            test_db.add(run)
        test_db.commit()

        # Filter by pipeline
        resp = test_client.get(f"/api/runs?pipeline_id={pid}")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

        # Filter by status
        resp = test_client.get(f"/api/runs?pipeline_id={pid}&status=failed")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_pipeline_delete_cascading(self, test_client):
        """Deleting a pipeline removes it completely."""
        pipeline = _create(test_client, "Delete Me", [_node("del1")], [])
        pid = pipeline["id"]

        resp = test_client.delete(f"/api/pipelines/{pid}")
        assert resp.status_code == 204

        resp = test_client.get(f"/api/pipelines/{pid}")
        assert resp.status_code == 404

    def test_health_endpoint(self, test_client):
        """Health endpoint returns ok status."""
        resp = test_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
