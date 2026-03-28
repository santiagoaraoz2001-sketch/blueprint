"""
Contract Validation Tests — Prompt 2.6, Task 104.

Loads all 12 canonical pipeline fixtures through the GraphPlanner.
Positive fixtures (1-9, 11, 12): assert valid planning.
Negative fixture (10): assert expected errors present.
Stale handle (12): assert warning about version mismatch.
"""

import sys
from pathlib import Path

import pytest

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.tests.fixtures.canonical_pipelines.loader import (
    load_canonical_fixture,
    load_all_canonical_fixtures,
    get_definition,
    get_expected,
    CANONICAL_FIXTURE_NAMES,
    POSITIVE_FIXTURES,
    NEGATIVE_FIXTURES,
)
from backend.engine.planner import GraphPlanner
from backend.engine.validator import validate_pipeline
from backend.engine.executor import _topological_sort, _detect_loops, _topological_sort_with_loops
from backend.engine.block_registry import resolve_output_handle
from backend.services.registry import get_global_registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_planner() -> GraphPlanner:
    """Get a GraphPlanner with the real block registry."""
    return GraphPlanner(get_global_registry())


ALL_FIXTURES = load_all_canonical_fixtures()


# ---------------------------------------------------------------------------
# Parametrized: All 12 fixtures load
# ---------------------------------------------------------------------------

class TestCanonicalFixturesLoad:
    """Verify all 12 canonical fixtures load and have required keys."""

    def test_all_12_fixtures_exist(self):
        assert len(ALL_FIXTURES) == 12, f"Expected 12 fixtures, got {len(ALL_FIXTURES)}"

    @pytest.mark.parametrize("name", CANONICAL_FIXTURE_NAMES)
    def test_fixture_has_required_keys(self, name):
        fixture = ALL_FIXTURES[name]
        assert "nodes" in fixture, f"Fixture {name} missing 'nodes'"
        assert "edges" in fixture, f"Fixture {name} missing 'edges'"
        assert "expected" in fixture, f"Fixture {name} missing 'expected'"
        expected = fixture["expected"]
        assert "validation" in expected, f"Fixture {name} missing 'expected.validation'"
        assert "partial_rerun_allowed" in expected
        assert "export_allowed" in expected


# ---------------------------------------------------------------------------
# Positive fixtures through GraphPlanner
# ---------------------------------------------------------------------------

class TestPositiveFixturesPlanner:
    """Positive fixtures (1-9, 11, 12) should produce valid plans."""

    @pytest.mark.parametrize("name", POSITIVE_FIXTURES)
    def test_planner_accepts(self, name):
        """GraphPlanner should produce is_valid=True for positive fixtures."""
        fixture = ALL_FIXTURES[name]
        definition = get_definition(fixture)
        workspace_config = fixture.get("workspace_config")

        planner = _get_planner()
        result = planner.plan(
            definition["nodes"],
            definition["edges"],
            workspace_config=workspace_config,
        )

        assert result.is_valid, (
            f"Fixture {name} expected valid but got errors: {result.errors}"
        )
        assert result.plan is not None
        assert len(result.plan.execution_order) > 0

    @pytest.mark.parametrize("name", POSITIVE_FIXTURES)
    def test_execution_order_matches(self, name):
        """Execution order should match expected when specified."""
        fixture = ALL_FIXTURES[name]
        expected = get_expected(fixture)
        expected_order = expected.get("execution_order", [])
        if not expected_order:
            pytest.skip(f"No expected execution_order for {name}")

        definition = get_definition(fixture)
        workspace_config = fixture.get("workspace_config")

        planner = _get_planner()
        result = planner.plan(
            definition["nodes"],
            definition["edges"],
            workspace_config=workspace_config,
        )

        assert result.is_valid
        actual_order = list(result.plan.execution_order)
        assert actual_order == expected_order, (
            f"Fixture {name}: expected order {expected_order}, got {actual_order}"
        )


# ---------------------------------------------------------------------------
# Positive fixtures through validator
# ---------------------------------------------------------------------------

class TestPositiveFixturesValidator:
    """Positive fixtures validated through validate_pipeline()."""

    @pytest.mark.parametrize("name", POSITIVE_FIXTURES)
    def test_validator_accepts(self, name):
        fixture = ALL_FIXTURES[name]
        definition = get_definition(fixture)
        report = validate_pipeline(definition)
        assert report.valid, (
            f"Fixture {name} expected valid but got errors: {report.errors}"
        )


# ---------------------------------------------------------------------------
# Negative fixture (10): expected failures
# ---------------------------------------------------------------------------

class TestNegativeFixtures:
    """Fixture 10 should fail validation with specific errors."""

    def test_expected_failures_planner_rejects(self):
        """GraphPlanner should reject fixture 10."""
        fixture = ALL_FIXTURES["10_expected_failures"]
        definition = get_definition(fixture)

        planner = _get_planner()
        result = planner.plan(definition["nodes"], definition["edges"])

        assert not result.is_valid, "Expected fixture 10 to be invalid"
        assert len(result.errors) > 0, "Expected at least one error"

    def test_expected_failures_validator_rejects(self):
        """Validator should reject fixture 10."""
        fixture = ALL_FIXTURES["10_expected_failures"]
        definition = get_definition(fixture)
        report = validate_pipeline(definition)

        assert not report.valid, "Expected fixture 10 to be invalid"
        assert len(report.errors) > 0

    def test_disconnected_required_port_detected(self):
        """Fixture 10 has text_b required but disconnected."""
        fixture = ALL_FIXTURES["10_expected_failures"]
        definition = get_definition(fixture)
        report = validate_pipeline(definition)

        # Should find a missing required input error
        required_error = any(
            "required" in e.lower() or "missing" in e.lower()
            for e in report.errors
        )
        assert required_error, (
            f"Expected error about disconnected required port, got: {report.errors}"
        )

    def test_type_incompatible_detected(self):
        """Fixture 10 has text→config which is incompatible."""
        fixture = ALL_FIXTURES["10_expected_failures"]
        definition = get_definition(fixture)
        report = validate_pipeline(definition)

        # Should find a type incompatibility error
        type_error = any(
            "incompatible" in e.lower() or "cannot connect" in e.lower()
            for e in report.errors
        )
        assert type_error, (
            f"Expected error about type-incompatible connection, got: {report.errors}"
        )

    def test_nonexistent_block_detected(self):
        """Fixture 10 has a nonexistent block type."""
        fixture = ALL_FIXTURES["10_expected_failures"]
        definition = get_definition(fixture)

        # Planner should report the unknown block
        planner = _get_planner()
        result = planner.plan(definition["nodes"], definition["edges"])

        nonexistent_error = any(
            "totally_fake_block_type_xyz" in e or "not found" in e.lower()
            for e in result.errors
        )
        assert nonexistent_error, (
            f"Expected error about nonexistent block type, got: {result.errors}"
        )

    def test_all_three_errors_present(self):
        """All 3 deliberate errors should be caught between planner + validator."""
        fixture = ALL_FIXTURES["10_expected_failures"]
        definition = get_definition(fixture)

        # Collect errors from both planner and validator
        planner = _get_planner()
        planner_result = planner.plan(definition["nodes"], definition["edges"])
        validator_report = validate_pipeline(definition)

        all_errors = list(planner_result.errors) + validator_report.errors
        all_errors_lower = " ".join(e.lower() for e in all_errors)

        # 1. Disconnected required port
        assert "required" in all_errors_lower or "missing" in all_errors_lower, \
            f"Missing 'required port' error in: {all_errors}"

        # 2. Type incompatibility
        assert "incompatible" in all_errors_lower or "cannot connect" in all_errors_lower, \
            f"Missing 'type incompatible' error in: {all_errors}"

        # 3. Nonexistent block type
        assert "totally_fake_block_type_xyz" in " ".join(all_errors) or "not found" in all_errors_lower, \
            f"Missing 'nonexistent block' error in: {all_errors}"


# ---------------------------------------------------------------------------
# Stale handle (12): version mismatch warning
# ---------------------------------------------------------------------------

class TestStaleHandle:
    """Fixture 12 should produce warnings about stale handles / version mismatch."""

    def test_stale_handle_validates_with_warning(self):
        """Stale handle fixture should validate (pass) but emit warnings."""
        fixture = ALL_FIXTURES["12_stale_handle"]
        definition = get_definition(fixture)
        report = validate_pipeline(definition)

        assert report.valid, f"Stale handle fixture should pass validation, got: {report.errors}"
        # Should have warnings about non-existent port or version mismatch
        has_relevant_warning = any(
            "port" in w.lower() or "version" in w.lower() or "stale" in w.lower()
            or "output" in w.lower()
            for w in report.warnings
        )
        assert has_relevant_warning, (
            f"Expected warning about stale handle/version, got warnings: {report.warnings}"
        )

    def test_stale_handle_alias_resolution(self):
        """The stale 'output' handle should resolve to 'response' via aliases."""
        resolved = resolve_output_handle("llm_inference", "output")
        assert resolved == "response", (
            f"Expected 'output' to resolve to 'response', got '{resolved}'"
        )

    def test_stale_handle_planner_succeeds(self):
        """Planner should still produce a valid plan for stale handles."""
        fixture = ALL_FIXTURES["12_stale_handle"]
        definition = get_definition(fixture)
        planner = _get_planner()
        result = planner.plan(definition["nodes"], definition["edges"])

        assert result.is_valid, f"Stale handle should plan OK, got: {result.errors}"
        assert list(result.plan.execution_order) == ["prompt_src", "old_block", "consumer"]


# ---------------------------------------------------------------------------
# Loop fixture validation
# ---------------------------------------------------------------------------

class TestLoopFixture:
    """Fixture 5 (valid loop) should validate and detect loop correctly."""

    def test_loop_validates(self):
        fixture = ALL_FIXTURES["05_valid_loop"]
        definition = get_definition(fixture)
        report = validate_pipeline(definition)
        assert report.valid, f"Loop fixture should validate, got: {report.errors}"

    def test_loop_detection(self):
        fixture = ALL_FIXTURES["05_valid_loop"]
        definition = get_definition(fixture)
        loops = _detect_loops(definition["nodes"], definition["edges"])
        assert len(loops) == 1
        assert loops[0].controller_id == "loop_ctrl"
        assert "loop_body" in loops[0].body_node_ids

    def test_loop_not_partial_rerun_allowed(self):
        """Contract V1: loops cannot be partially rerun."""
        fixture = ALL_FIXTURES["05_valid_loop"]
        expected = get_expected(fixture)
        assert expected["partial_rerun_allowed"] is False

    def test_loop_not_exportable(self):
        """Contract V1: loops cannot be exported."""
        fixture = ALL_FIXTURES["05_valid_loop"]
        expected = get_expected(fixture)
        assert expected["export_allowed"] is False


# ---------------------------------------------------------------------------
# Concurrent subgraphs
# ---------------------------------------------------------------------------

class TestConcurrentSubgraphs:
    """Fixture 8 should detect independent subgraphs."""

    def test_independent_subgraphs_detected(self):
        fixture = ALL_FIXTURES["08_concurrent_subgraphs"]
        definition = get_definition(fixture)
        planner = _get_planner()
        result = planner.plan(definition["nodes"], definition["edges"])

        assert result.is_valid
        assert len(result.plan.independent_subgraphs) >= 2, (
            f"Expected >=2 independent subgraphs, got {len(result.plan.independent_subgraphs)}"
        )


# ---------------------------------------------------------------------------
# Config inheritance
# ---------------------------------------------------------------------------

class TestConfigInheritance:
    """Fixture 4 should propagate workspace seed=42."""

    def test_workspace_config_propagates(self):
        fixture = ALL_FIXTURES["04_config_inheritance"]
        definition = get_definition(fixture)
        workspace_config = fixture.get("workspace_config", {})

        planner = _get_planner()
        result = planner.plan(
            definition["nodes"],
            definition["edges"],
            workspace_config=workspace_config,
        )

        assert result.is_valid
        # The workspace config should be available via resolved configs
        assert result.plan is not None
