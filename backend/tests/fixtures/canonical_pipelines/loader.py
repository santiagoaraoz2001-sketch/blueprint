"""
Loader for the 12 canonical pipeline fixtures (prompt 2.6).

Usage:
    from backend.tests.fixtures.canonical_pipelines.loader import (
        load_canonical_fixture,
        load_all_canonical_fixtures,
        CANONICAL_FIXTURE_NAMES,
        POSITIVE_FIXTURES,
        NEGATIVE_FIXTURES,
        EXECUTABLE_FIXTURES,
        EXPORTABLE_FIXTURES,
    )
"""

import json
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).parent

# Ordered list of all 12 canonical fixtures
CANONICAL_FIXTURE_NAMES = [
    "01_simple_three_block_dag",
    "02_branching_fan_out_fan_in",
    "03_eight_block_chain",
    "04_config_inheritance",
    "05_valid_loop",
    "06_model_substitution",
    "07_custom_code",
    "08_concurrent_subgraphs",
    "09_partial_rerun",
    "10_expected_failures",
    "11_aliased_ports",
    "12_stale_handle",
]

# Fixtures 1-9 and 11 are positive (validation=pass)
POSITIVE_FIXTURES = [
    "01_simple_three_block_dag",
    "02_branching_fan_out_fan_in",
    "03_eight_block_chain",
    "04_config_inheritance",
    "05_valid_loop",
    "06_model_substitution",
    "07_custom_code",
    "08_concurrent_subgraphs",
    "09_partial_rerun",
    "11_aliased_ports",
    "12_stale_handle",
]

# Fixture 10 is negative (validation=fail)
NEGATIVE_FIXTURES = [
    "10_expected_failures",
]

# Executable fixtures (1-9): can be executed end-to-end
EXECUTABLE_FIXTURES = [
    "01_simple_three_block_dag",
    "02_branching_fan_out_fan_in",
    "03_eight_block_chain",
    "04_config_inheritance",
    "05_valid_loop",
    "06_model_substitution",
    "07_custom_code",
    "08_concurrent_subgraphs",
    "09_partial_rerun",
]

# Exportable fixtures (can compile to standalone Python)
EXPORTABLE_FIXTURES = [
    "01_simple_three_block_dag",
    "02_branching_fan_out_fan_in",
    "03_eight_block_chain",
    "04_config_inheritance",
    "06_model_substitution",
    "08_concurrent_subgraphs",
    "09_partial_rerun",
    "11_aliased_ports",
]

# Non-exportable: loops and custom code
NON_EXPORTABLE_FIXTURES = [
    "05_valid_loop",
    "07_custom_code",
]


def load_canonical_fixture(name: str) -> dict[str, Any]:
    """Load a single canonical fixture by name."""
    path = FIXTURES_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Canonical fixture not found: {path}")
    with open(path) as f:
        return json.load(f)


def load_all_canonical_fixtures() -> dict[str, dict[str, Any]]:
    """Load all 12 canonical fixtures as {name: data}."""
    fixtures = {}
    for name in CANONICAL_FIXTURE_NAMES:
        fixtures[name] = load_canonical_fixture(name)
    return fixtures


def get_definition(fixture: dict) -> dict:
    """Extract {nodes, edges} from a fixture for passing to validators/planners."""
    return {
        "nodes": fixture.get("nodes", []),
        "edges": fixture.get("edges", []),
    }


def get_expected(fixture: dict) -> dict:
    """Extract the expected sidecar from a fixture."""
    return fixture.get("expected", {})
