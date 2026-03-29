"""Performance benchmarks — validates startup, validation, and load times.

Targets:
  - App import + TestClient init < 3s  (combined cold-start)
  - Validation response < 200ms        (10-node pipeline, warmed registry)
  - Pipeline load < 500ms              (20-node pipeline from DB)
  - Pipeline list < 500ms              (20 pipelines)
  - Run list by pipeline < 500ms       (50 runs filtered by pipeline_id)

Also verifies database indexes exist and are effective via EXPLAIN QUERY PLAN.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.models.pipeline import Pipeline
from backend.models.run import Run


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_node(nid: str, config: dict | None = None) -> dict:
    return {
        "id": nid,
        "type": "blockNode",
        "position": {"x": int(nid.replace("n", "")) * 100, "y": 0},
        "data": {
            "type": "data_loader",
            "label": f"Block {nid}",
            "category": "data",
            "config": config or {"source": f"file_{nid}.csv", "batch_size": 32},
        },
    }


def _make_edge(src: str, tgt: str) -> dict:
    return {"id": f"e-{src}-{tgt}", "source": src, "target": tgt,
            "sourceHandle": "output", "targetHandle": "input"}


# ── Benchmark: App Startup ───────────────────────────────────────────

class TestAppStartup:
    """Combined import + TestClient cold-start benchmark.

    Measures end-to-end Python startup cost: loading all backend modules,
    resolving the FastAPI app, and instantiating the ASGI test transport.
    This does NOT measure uvicorn socket binding or lifespan events, which
    are server-level concerns not relevant to per-request performance.
    """

    def test_cold_start_under_3_seconds(self):
        """Importing backend.main + creating TestClient takes < 3s combined."""
        start = time.perf_counter()

        from backend.main import app  # noqa: F811
        from fastapi.testclient import TestClient
        _ = TestClient(app)

        elapsed = time.perf_counter() - start

        # On cached re-imports this will be near-instant; on first import
        # it includes module loading, block registry discovery, etc.
        assert elapsed < 3.0, (
            f"Cold start took {elapsed:.2f}s (target: <3s). "
            f"This measures Python import + TestClient, not uvicorn startup."
        )


# ── Benchmark: Validation Response ───────────────────────────────────

class TestValidationPerformance:
    """Validation endpoint timing on realistic pipeline sizes."""

    def test_validation_under_200ms_10_nodes(self, test_client):
        """10-node linear pipeline validates in < 200ms (after registry warm-up)."""
        nodes = [_make_node(f"n{i}") for i in range(10)]
        edges = [_make_edge(f"n{i}", f"n{i+1}") for i in range(9)]

        resp = test_client.post("/api/pipelines", json={
            "name": "Perf: 10-Node Validation",
            "definition": {"nodes": nodes, "edges": edges},
        })
        assert resp.status_code == 201
        pid = resp.json()["id"]

        # Warm-up: first call initializes the global block registry singleton
        test_client.post(f"/api/pipelines/{pid}/validate")

        # Benchmark: measure second call (registry cached, DB warm)
        timings = []
        for _ in range(3):
            start = time.perf_counter()
            resp = test_client.post(f"/api/pipelines/{pid}/validate")
            timings.append(time.perf_counter() - start)
            assert resp.status_code == 200

        median = sorted(timings)[1]
        assert median < 0.2, (
            f"Median validation time: {median * 1000:.1f}ms over 3 runs "
            f"(target: <200ms). Timings: {[f'{t*1000:.1f}ms' for t in timings]}"
        )

    def test_validation_50_nodes_under_500ms(self, test_client):
        """50-node pipeline validates in < 500ms (stress test)."""
        nodes = [_make_node(f"n{i}") for i in range(50)]
        edges = [_make_edge(f"n{i}", f"n{i+1}") for i in range(49)]

        resp = test_client.post("/api/pipelines", json={
            "name": "Perf: 50-Node Validation",
            "definition": {"nodes": nodes, "edges": edges},
        })
        pid = resp.json()["id"]

        # Warm-up
        test_client.post(f"/api/pipelines/{pid}/validate")

        start = time.perf_counter()
        resp = test_client.post(f"/api/pipelines/{pid}/validate")
        elapsed = time.perf_counter() - start

        assert resp.status_code == 200
        assert elapsed < 0.5, f"50-node validation took {elapsed * 1000:.1f}ms (target: <500ms)"


# ── Benchmark: Pipeline Load ────────────────────────────────────────

class TestPipelineLoadPerformance:
    """Pipeline retrieval from database."""

    def test_pipeline_load_under_500ms(self, test_client):
        """Loading a 20-node pipeline by ID takes < 500ms."""
        nodes = [_make_node(f"n{i}") for i in range(20)]
        edges = [_make_edge(f"n{i}", f"n{i+1}") for i in range(19)]

        resp = test_client.post("/api/pipelines", json={
            "name": "Perf: Load Test",
            "definition": {"nodes": nodes, "edges": edges},
        })
        pid = resp.json()["id"]

        # Warm-up
        test_client.get(f"/api/pipelines/{pid}")

        timings = []
        for _ in range(3):
            start = time.perf_counter()
            resp = test_client.get(f"/api/pipelines/{pid}")
            timings.append(time.perf_counter() - start)
            assert resp.status_code == 200

        median = sorted(timings)[1]
        assert median < 0.5, (
            f"Median load time: {median * 1000:.1f}ms over 3 runs "
            f"(target: <500ms). Timings: {[f'{t*1000:.1f}ms' for t in timings]}"
        )

    def test_pipeline_list_20_under_500ms(self, test_client):
        """Listing 20 pipelines takes < 500ms."""
        for i in range(20):
            test_client.post("/api/pipelines", json={
                "name": f"Perf: List {i}",
                "definition": {"nodes": [_make_node(f"n{i}")], "edges": []},
            })

        # Warm-up
        test_client.get("/api/pipelines")

        start = time.perf_counter()
        resp = test_client.get("/api/pipelines")
        elapsed = time.perf_counter() - start

        assert resp.status_code == 200
        assert elapsed < 0.5, f"Pipeline list took {elapsed * 1000:.1f}ms (target: <500ms)"


# ── Benchmark: Run Query Performance ────────────────────────────────

class TestRunQueryPerformance:
    """Run listing with pipeline_id filter (exercises idx_runs_pipeline index)."""

    def test_run_list_by_pipeline_under_500ms(self, test_client, test_db):
        """Listing 50 runs filtered by pipeline_id takes < 500ms."""
        resp = test_client.post("/api/pipelines", json={
            "name": "Perf: Run Query",
            "definition": {"nodes": [], "edges": []},
        })
        pid = resp.json()["id"]

        for i in range(50):
            run = Run(
                id=str(uuid.uuid4()),
                pipeline_id=pid,
                status="complete" if i % 3 else "failed",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                duration_seconds=float(i),
                metrics={"loss": 0.1 * i},
            )
            test_db.add(run)
        test_db.commit()

        # Warm-up
        test_client.get(f"/api/runs?pipeline_id={pid}")

        timings = []
        for _ in range(3):
            start = time.perf_counter()
            resp = test_client.get(f"/api/runs?pipeline_id={pid}")
            timings.append(time.perf_counter() - start)
            assert resp.status_code == 200

        median = sorted(timings)[1]
        assert median < 0.5, (
            f"Median run list time: {median * 1000:.1f}ms over 3 runs "
            f"(target: <500ms). Timings: {[f'{t*1000:.1f}ms' for t in timings]}"
        )


# ── Database Indexes ─────────────────────────────────────────────────

class TestDatabaseIndexes:
    """Verify that critical indexes exist and are used by queries."""

    def test_indexes_exist_on_runs(self, test_db):
        """Verify idx_runs_pipeline exists on blueprint_runs.pipeline_id."""
        from sqlalchemy import inspect

        inspector = inspect(test_db.get_bind())
        indexes = inspector.get_indexes("blueprint_runs")

        indexed_columns = set()
        for idx in indexes:
            for col in idx["column_names"]:
                indexed_columns.add(col)

        assert "pipeline_id" in indexed_columns, (
            f"Missing index on runs.pipeline_id. "
            f"Found indexes on: {indexed_columns}"
        )

    def test_indexes_exist_on_execution_decisions(self, test_db):
        """Verify composite (run_id, node_id) and timestamp indexes on execution_decisions."""
        from sqlalchemy import inspect

        inspector = inspect(test_db.get_bind())
        indexes = inspector.get_indexes("execution_decisions")

        # Collect both single-column and composite index info
        single_cols = set()
        composites = []
        for idx in indexes:
            cols = tuple(idx["column_names"])
            composites.append(cols)
            for col in cols:
                single_cols.add(col)

        assert "run_id" in single_cols, "Missing index on execution_decisions.run_id"
        assert "node_id" in single_cols, "Missing index on execution_decisions.node_id"

        # Verify composite index (run_id, node_id) exists
        has_composite = any(
            "run_id" in cols and "node_id" in cols
            for cols in composites
        )
        assert has_composite, (
            f"Missing composite index on (run_id, node_id). "
            f"Found composites: {composites}"
        )

    def test_indexes_exist_on_artifact_cache(self, test_db):
        """Verify run_id index on blueprint_artifact_cache."""
        from sqlalchemy import inspect

        inspector = inspect(test_db.get_bind())
        indexes = inspector.get_indexes("blueprint_artifact_cache")

        indexed_columns = set()
        for idx in indexes:
            for col in idx["column_names"]:
                indexed_columns.add(col)

        assert "run_id" in indexed_columns, (
            f"Missing index on artifact_cache.run_id. "
            f"Found indexes on: {indexed_columns}"
        )

    def test_query_plan_uses_index_for_run_filter(self, test_db):
        """EXPLAIN QUERY PLAN shows index usage for runs filtered by pipeline_id."""
        # SQLite's EXPLAIN QUERY PLAN shows whether an index scan is used
        result = test_db.execute(
            text("EXPLAIN QUERY PLAN SELECT * FROM blueprint_runs WHERE pipeline_id = 'test'")
        )
        plan_rows = [str(row) for row in result.fetchall()]
        plan_text = " ".join(plan_rows).lower()

        # SQLite should use the index — look for "index" in the plan
        # (vs "SCAN TABLE" which means full table scan)
        assert "index" in plan_text or "search" in plan_text, (
            f"Query plan for runs.pipeline_id filter does not use an index. "
            f"Plan: {plan_rows}"
        )
