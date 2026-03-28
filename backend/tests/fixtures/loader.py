"""
Fixture loader for canonical pipeline contract fixtures.

Usage:
    from backend.tests.fixtures.loader import load_fixture, load_all_fixtures

    fixture = load_fixture("simple_dag")
    all_fixtures = load_all_fixtures()
"""

import json
from pathlib import Path
from typing import Any

CONTRACTS_DIR = Path(__file__).parent / "contracts"

# All canonical fixture names
FIXTURE_NAMES = [
    "simple_dag",
    "branching_dag",
    "legal_loop",
    "illegal_cycle",
    "stale_handle",
    "input_satisfies_config",
    "partial_rerun_safe",
    "partial_rerun_unsafe",
    "port_compat_drift",
]


def load_fixture(name: str) -> dict[str, Any]:
    """Load a single fixture by name.

    Args:
        name: Fixture name (e.g., "simple_dag"). Must match a .json file in contracts/.

    Returns:
        Parsed fixture dict with keys: name, description, nodes, edges, expected.

    Raises:
        FileNotFoundError: If the fixture file does not exist.
        json.JSONDecodeError: If the fixture is not valid JSON.
    """
    path = CONTRACTS_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found: {path}")
    with open(path) as f:
        return json.load(f)


def load_all_fixtures() -> dict[str, dict[str, Any]]:
    """Load all canonical fixtures.

    Returns:
        Dict mapping fixture name to parsed fixture dict.
    """
    fixtures = {}
    for path in sorted(CONTRACTS_DIR.glob("*.json")):
        with open(path) as f:
            data = json.load(f)
        fixtures[path.stem] = data
    return fixtures


def get_definition(fixture: dict) -> dict:
    """Extract the pipeline definition (nodes + edges) from a fixture.

    This is the format expected by executor, validator, compiler, etc.
    """
    return {
        "nodes": fixture.get("nodes", []),
        "edges": fixture.get("edges", []),
    }


def get_expected(fixture: dict) -> dict:
    """Extract the expected sidecar from a fixture."""
    return fixture.get("expected", {})
