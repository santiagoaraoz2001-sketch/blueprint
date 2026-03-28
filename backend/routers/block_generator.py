"""Block Generator API — generate, validate, install, and test LLM-generated blocks."""

import ast
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import BUILTIN_BLOCKS_DIR
from ..services.registry import reset_global_registry
from ..services.llm_block_gen import VALID_CATEGORIES, generate_block as _generate_block

logger = logging.getLogger("blueprint.block_generator")

router = APIRouter(prefix="/api/block-generator", tags=["block-generator"])

SAFE_TYPE_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


# ── Request / Response Models ──


class GenerateRequest(BaseModel):
    description: str
    category: str | None = None
    name: str | None = None


class InstallRequest(BaseModel):
    block_yaml: str
    run_py: str
    block_type: str
    category: str


class TestRequest(BaseModel):
    block_yaml: str
    run_py: str
    config: dict | None = None
    inputs: dict | None = None


# ── Endpoints ──


@router.post("/generate")
def generate_block_endpoint(body: GenerateRequest):
    """Generate a block from a natural language description using a local LLM."""
    if not body.description.strip():
        raise HTTPException(status_code=400, detail="Description is required")

    result = _generate_block(
        description=body.description,
        category=body.category,
        name=body.name,
    )

    if "error" in result and "block_yaml" not in result:
        raise HTTPException(status_code=503, detail=result["error"])

    return result


@router.post("/generate/install")
def install_generated_block(body: InstallRequest):
    """Install a generated block to the blocks/ directory."""
    block_type = body.block_type.strip()
    category = body.category.strip()

    if not SAFE_TYPE_ID.match(block_type):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid block type: '{block_type}'. Must be lowercase alphanumeric with underscores.",
        )

    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category: '{category}'")

    # Target directory
    block_dir = BUILTIN_BLOCKS_DIR / category / block_type
    if block_dir.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Block '{block_type}' already exists in {category}/",
        )

    # Validate YAML before installing
    try:
        parsed_yaml = yaml.safe_load(body.block_yaml)
        if not isinstance(parsed_yaml, dict):
            raise ValueError("YAML must be a mapping")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")

    # Validate Python syntax
    try:
        ast.parse(body.run_py)
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Python syntax error: {e}")

    # Write files
    try:
        block_dir.mkdir(parents=True, exist_ok=True)
        (block_dir / "block.yaml").write_text(body.block_yaml, encoding="utf-8")
        (block_dir / "run.py").write_text(body.run_py, encoding="utf-8")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to write block files: {e}")

    # Reset block registry cache so the new block is discovered
    reset_global_registry()

    # Regenerate frontend block registry (best-effort)
    _regenerate_frontend_registry()

    return {
        "installed": True,
        "block_type": block_type,
        "category": category,
        "path": str(block_dir),
    }


@router.post("/generate/test")
def test_generated_block(body: TestRequest):
    """Test a generated block without installing it.

    Writes code to a temp directory and executes in a subprocess.
    """
    # Write to temp dir
    tmp_dir = tempfile.mkdtemp(prefix="blueprint_block_test_")
    try:
        block_dir = Path(tmp_dir) / "test_block"
        block_dir.mkdir()
        (block_dir / "block.yaml").write_text(body.block_yaml, encoding="utf-8")
        (block_dir / "run.py").write_text(body.run_py, encoding="utf-8")

        # Build test script (same pattern as custom_blocks.py)
        project_root = str(Path(__file__).parent.parent.parent)
        test_script = """\
import sys, os, json
sys.path.insert(0, os.environ["_BLUEPRINT_ROOT"])
from backend.block_sdk.context import BlockContext
import importlib.util

spec = importlib.util.spec_from_file_location("test_block", os.environ["_BLUEPRINT_RUN_PY"])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

payload = json.loads(sys.stdin.read()) if not sys.stdin.isatty() else {}
config = payload.get('config', {})
inputs = payload.get('inputs', {})

run_dir = os.path.join(os.environ["_BLUEPRINT_BLOCK_DIR"], "_test_output")
os.makedirs(run_dir, exist_ok=True)

ctx = BlockContext(
    run_dir=run_dir,
    block_dir=os.environ["_BLUEPRINT_BLOCK_DIR"],
    config=config,
    inputs=inputs,
)
mod.run(ctx)
print(json.dumps({"outputs": ctx.get_outputs(), "success": True}))
"""
        env = {
            **os.environ,
            "_BLUEPRINT_ROOT": project_root,
            "_BLUEPRINT_RUN_PY": str(block_dir / "run.py"),
            "_BLUEPRINT_BLOCK_DIR": str(block_dir),
        }
        stdin_data = json.dumps({
            "config": body.config or {},
            "inputs": body.inputs or {},
        })

        result = subprocess.run(
            [sys.executable, "-c", test_script],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        if result.returncode == 0:
            try:
                output = json.loads(result.stdout.strip().split("\n")[-1])
                return output
            except (ValueError, IndexError):
                return {
                    "success": True,
                    "outputs": {},
                    "stdout": result.stdout,
                }
        else:
            return {
                "success": False,
                "error": result.stderr or "Block execution failed",
                "stdout": result.stdout,
            }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Test timed out after 30 seconds"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _regenerate_frontend_registry():
    """Run the block registry generation script (best-effort)."""
    script = Path(__file__).parent.parent.parent / "scripts" / "generate_block_registry.py"
    if not script.exists():
        logger.debug("Registry generation script not found at %s", script)
        return
    try:
        subprocess.Popen(
            [sys.executable, str(script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        logger.warning("Failed to regenerate frontend registry: %s", e)
