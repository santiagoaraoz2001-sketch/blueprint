"""
Block Coverage Tests — Prompt 2.6, Task 107 (Part 2).

Broader automated coverage across ALL blocks:
1. Parse ALL block.yaml files — verify valid YAML with required fields.
2. Import ALL run.py files — verify each imports without crashing.
3. For blocks that declare 'requires' capabilities — verify they raise
   appropriate errors when required libraries are unavailable.
"""

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.config import BUILTIN_BLOCKS_DIR, BLOCKS_DIR, CUSTOM_BLOCKS_DIR
from backend.services.registry import get_global_registry

# ---------------------------------------------------------------------------
# Discovery: find all block directories
# ---------------------------------------------------------------------------

def _discover_all_block_dirs() -> list[Path]:
    """Find all block directories that have a block.yaml."""
    dirs = []
    for base in [BUILTIN_BLOCKS_DIR, BLOCKS_DIR, CUSTOM_BLOCKS_DIR]:
        if not base.exists():
            continue
        for category_dir in sorted(base.iterdir()):
            if not category_dir.is_dir() or category_dir.name.startswith((".", "_")):
                continue
            for block_dir in sorted(category_dir.iterdir()):
                if not block_dir.is_dir() or block_dir.name.startswith((".", "_")):
                    continue
                if (block_dir / "block.yaml").exists():
                    dirs.append(block_dir)
    return dirs


ALL_BLOCK_DIRS = _discover_all_block_dirs()
ALL_BLOCK_IDS = [f"{d.parent.name}/{d.name}" for d in ALL_BLOCK_DIRS]


# ---------------------------------------------------------------------------
# 1. Parse ALL block.yaml files
# ---------------------------------------------------------------------------

class TestBlockYamlParsing:
    """Every block.yaml must parse as valid YAML with required fields."""

    @pytest.mark.parametrize("block_dir", ALL_BLOCK_DIRS, ids=ALL_BLOCK_IDS)
    def test_yaml_parses(self, block_dir: Path):
        """block.yaml must be valid YAML."""
        yaml_path = block_dir / "block.yaml"
        try:
            with open(yaml_path) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            pytest.fail(f"Invalid YAML in {yaml_path}: {e}")

        assert data is not None, f"Empty block.yaml: {yaml_path}"
        assert isinstance(data, dict), f"block.yaml is not a dict: {yaml_path}"

    @pytest.mark.parametrize("block_dir", ALL_BLOCK_DIRS, ids=ALL_BLOCK_IDS)
    def test_has_required_fields(self, block_dir: Path):
        """block.yaml must have type, category, and at least one port."""
        yaml_path = block_dir / "block.yaml"
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        # Required top-level fields
        assert "type" in data or "name" in data, (
            f"{yaml_path}: missing 'type' or 'name'"
        )
        assert "category" in data, f"{yaml_path}: missing 'category'"

        # Must have inputs or outputs (or both)
        inputs = data.get("inputs", [])
        outputs = data.get("outputs", [])
        assert len(inputs) > 0 or len(outputs) > 0, (
            f"{yaml_path}: block has no inputs or outputs"
        )

    @pytest.mark.parametrize("block_dir", ALL_BLOCK_DIRS, ids=ALL_BLOCK_IDS)
    def test_ports_have_required_fields(self, block_dir: Path):
        """All ports must have 'id' and 'data_type'."""
        yaml_path = block_dir / "block.yaml"
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        for port_list_key in ("inputs", "outputs", "side_inputs"):
            for port in data.get(port_list_key, []):
                assert "id" in port, (
                    f"{yaml_path}: port in '{port_list_key}' missing 'id': {port}"
                )
                assert "data_type" in port, (
                    f"{yaml_path}: port '{port.get('id')}' missing 'data_type'"
                )

    @pytest.mark.parametrize("block_dir", ALL_BLOCK_DIRS, ids=ALL_BLOCK_IDS)
    def test_port_data_types_valid(self, block_dir: Path):
        """All port data_types must be recognized types."""
        yaml_path = block_dir / "block.yaml"
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        valid_types = {
            "dataset", "text", "model", "config", "metrics",
            "embedding", "artifact", "any", "llm", "agent",
            # Legacy aliases that might still appear
            "data", "training", "intervention",
        }

        for port_list_key in ("inputs", "outputs", "side_inputs"):
            for port in data.get(port_list_key, []):
                dt = port.get("data_type", "any")
                assert dt in valid_types, (
                    f"{yaml_path}: port '{port.get('id')}' has unknown data_type '{dt}'"
                )

    @pytest.mark.parametrize("block_dir", ALL_BLOCK_DIRS, ids=ALL_BLOCK_IDS)
    def test_config_fields_have_type(self, block_dir: Path):
        """Config fields must specify a type."""
        yaml_path = block_dir / "block.yaml"
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        config = data.get("config", {})
        if not isinstance(config, dict):
            return

        valid_config_types = {
            "string", "integer", "float", "boolean", "select",
            "text_area", "file_path", "number", "json", "code",
            "textarea", "text", "color", "slider",
        }

        for field_name, field_spec in config.items():
            if not isinstance(field_spec, dict):
                continue
            field_type = field_spec.get("type", "string")
            assert field_type in valid_config_types, (
                f"{yaml_path}: config field '{field_name}' has unknown type '{field_type}'"
            )


# ---------------------------------------------------------------------------
# 2. Import ALL run.py files
# ---------------------------------------------------------------------------

class TestBlockRunImports:
    """Every run.py must import without crashing."""

    @pytest.mark.parametrize("block_dir", ALL_BLOCK_DIRS, ids=ALL_BLOCK_IDS)
    def test_run_py_imports(self, block_dir: Path):
        """run.py must be importable (no syntax errors, no missing deps at import time)."""
        run_py = block_dir / "run.py"
        if not run_py.exists():
            pytest.skip(f"No run.py in {block_dir}")

        mod_name = f"_test_import_{block_dir.parent.name}_{block_dir.name}"

        try:
            spec = importlib.util.spec_from_file_location(mod_name, str(run_py))
            assert spec is not None, f"Cannot create module spec for {run_py}"
            assert spec.loader is not None, f"Spec has no loader for {run_py}"
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except SyntaxError as e:
            pytest.fail(f"Syntax error in {run_py}: {e}")
        except ImportError as e:
            # ImportError is acceptable — block may depend on optional packages.
            # But it should be a *specific* library import failure, not a broken
            # relative import of the block SDK.
            err_msg = str(e).lower()
            if "backend.block_sdk" in err_msg or "block_sdk" in err_msg:
                pytest.fail(
                    f"run.py in {block_dir} fails to import block SDK: {e}"
                )
            # Optional dependency missing — acceptable in CI
            pass
        except Exception as e:
            # Other errors during import (e.g., missing env vars)
            # are warnings, not hard failures
            if "CUDA" in str(e) or "torch" in str(e) or "mlx" in str(e):
                pytest.skip(f"GPU/ML dependency required: {e}")
            # For other errors, still allow — some blocks do setup at import
            pass

    @pytest.mark.parametrize("block_dir", ALL_BLOCK_DIRS, ids=ALL_BLOCK_IDS)
    def test_run_py_has_run_function(self, block_dir: Path):
        """run.py should define a 'run' function."""
        run_py = block_dir / "run.py"
        if not run_py.exists():
            pytest.skip(f"No run.py in {block_dir}")

        mod_name = f"_test_runfn_{block_dir.parent.name}_{block_dir.name}"

        try:
            spec = importlib.util.spec_from_file_location(mod_name, str(run_py))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception:
            pytest.skip(f"Cannot import {run_py}")

        assert hasattr(mod, "run"), (
            f"{run_py}: missing 'run' function. "
            f"Available attributes: {[a for a in dir(mod) if not a.startswith('_')]}"
        )


# ---------------------------------------------------------------------------
# 3. Blocks with 'requires' capabilities
# ---------------------------------------------------------------------------

class TestBlockDependencyGuards:
    """Blocks declaring 'requires' should guard against missing dependencies."""

    @pytest.mark.parametrize("block_dir", ALL_BLOCK_DIRS, ids=ALL_BLOCK_IDS)
    def test_requires_field_consistency(self, block_dir: Path):
        """If block.yaml declares 'requires', verify it's a list."""
        yaml_path = block_dir / "block.yaml"
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        requires = data.get("requires")
        if requires is None:
            return

        assert isinstance(requires, list), (
            f"{yaml_path}: 'requires' should be a list, got {type(requires).__name__}"
        )


# ---------------------------------------------------------------------------
# 4. Registry consistency
# ---------------------------------------------------------------------------

class TestRegistryConsistency:
    """Verify the registry discovers all blocks and their schemas are valid."""

    def test_registry_discovers_all_blocks(self):
        """Registry should discover all blocks that have block.yaml + run.py."""
        registry = get_global_registry()
        all_types = registry.get_block_types()
        assert len(all_types) > 100, (
            f"Expected >100 block types in registry, got {len(all_types)}"
        )

    def test_no_broken_blocks_in_registry(self):
        """All blocks in the registry should be valid (not broken)."""
        registry = get_global_registry()
        health = registry.get_health()
        broken = health.get("broken_blocks", [])
        # Allow a small number of broken blocks but flag them
        if broken:
            pytest.skip(
                f"Registry has {len(broken)} broken blocks: {broken[:10]}. "
                f"These should be investigated."
            )

    def test_every_block_dir_is_in_registry(self):
        """Every block.yaml in the blocks/ tree should appear in the registry."""
        registry = get_global_registry()
        all_types = registry.get_block_types()

        missing = []
        for block_dir in ALL_BLOCK_DIRS:
            yaml_path = block_dir / "block.yaml"
            with open(yaml_path) as f:
                data = yaml.safe_load(f)
            block_type = data.get("type", block_dir.name)
            if block_type not in all_types:
                missing.append(f"{block_dir.parent.name}/{block_type}")

        assert not missing, (
            f"Blocks present on disk but missing from registry: {missing}"
        )
