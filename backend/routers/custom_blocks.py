"""
Custom Blocks CRUD API.

Manages user-created blocks stored in ~/.specific-labs/custom_blocks/{type_id}/.
Each custom block has a block.yaml and run.py file.
"""

import os
import re
import yaml
import shutil
import subprocess
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import BASE_DIR

CUSTOM_BLOCKS_DIR = BASE_DIR / "custom_blocks"
SAFE_TYPE_ID = re.compile(r'^[a-z][a-z0-9_]{0,63}$')

router = APIRouter(prefix="/api/custom-blocks", tags=["custom-blocks"])


class PortModel(BaseModel):
    id: str
    label: str
    dataType: str = "data"
    required: bool = True


class ConfigFieldModel(BaseModel):
    name: str
    label: str
    type: str = "text"
    default: str | int | float | bool | None = None


class CustomBlockCreate(BaseModel):
    type: str
    name: str
    description: str = ""
    category: str = "source"
    icon: str = "Box"
    inputs: list[PortModel] = []
    outputs: list[PortModel] = []
    configFields: list[ConfigFieldModel] = []
    defaultConfig: dict = {}
    code: str = ""


class CustomBlockUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    icon: str | None = None
    inputs: list[PortModel] | None = None
    outputs: list[PortModel] | None = None
    configFields: list[ConfigFieldModel] | None = None
    defaultConfig: dict | None = None
    code: str | None = None


def _ensure_dir():
    CUSTOM_BLOCKS_DIR.mkdir(parents=True, exist_ok=True)


def _block_dir(type_id: str) -> Path:
    return CUSTOM_BLOCKS_DIR / type_id


def _read_block(type_id: str) -> dict | None:
    block_dir = _block_dir(type_id)
    yaml_path = block_dir / "block.yaml"
    if not yaml_path.exists():
        return None
    with open(yaml_path) as f:
        meta = yaml.safe_load(f) or {}
    meta["type"] = type_id
    meta["source"] = "custom"
    # Read code
    run_py = block_dir / "run.py"
    if run_py.exists():
        meta["code"] = run_py.read_text()
    return meta


def _write_block(type_id: str, data: dict, code: str):
    block_dir = _block_dir(type_id)
    block_dir.mkdir(parents=True, exist_ok=True)

    # Write block.yaml (exclude code field)
    yaml_data = {k: v for k, v in data.items() if k not in ("code", "type", "source")}
    with open(block_dir / "block.yaml", "w") as f:
        yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False)

    # Write run.py
    with open(block_dir / "run.py", "w") as f:
        f.write(code)


@router.get("")
def list_custom_blocks():
    """List all custom blocks."""
    _ensure_dir()
    blocks = []
    for item in sorted(CUSTOM_BLOCKS_DIR.iterdir()):
        if item.is_dir():
            block = _read_block(item.name)
            if block:
                blocks.append(block)
    return blocks


@router.post("")
def create_custom_block(block: CustomBlockCreate):
    """Create a new custom block."""
    _ensure_dir()
    type_id = block.type
    if not SAFE_TYPE_ID.match(type_id):
        raise HTTPException(400, f"Invalid block type id: '{type_id}'. Must be lowercase alphanumeric with underscores.")
    if _block_dir(type_id).exists():
        raise HTTPException(409, f"Block '{type_id}' already exists.")

    data = block.model_dump()
    code = data.pop("code", "")
    if not code.strip():
        code = _default_run_py(block.name)

    _write_block(type_id, data, code)
    return _read_block(type_id)


class CodeValidateRequest(BaseModel):
    code: str
    name: str = "block"


@router.post("/validate-code")
def validate_code(req: CodeValidateRequest):
    """Validate custom block Python code without executing it.

    Checks syntax, run() function presence and signature.
    Returns {valid, errors, warnings}.
    """
    import ast as _ast

    errors: list[str] = []
    warnings: list[str] = []

    # 1. Syntax check
    try:
        tree = _ast.parse(req.code)
    except SyntaxError as e:
        return {
            "valid": False,
            "errors": [f"Syntax error at line {e.lineno}: {e.msg}"],
            "warnings": [],
        }
    except Exception as e:
        return {"valid": False, "errors": [f"Parse error: {e}"], "warnings": []}

    # 2. Locate run() function
    run_func = next(
        (node for node in _ast.walk(tree) if isinstance(node, _ast.FunctionDef) and node.name == "run"),
        None,
    )

    if run_func is None:
        errors.append(
            "Missing required `run()` function. Define it as:\n"
            "  def run(ctx):  ...  (single BlockContext arg)\n"
            "  def run(inputs, config):  ...  (two-arg legacy style)"
        )
    else:
        args = run_func.args
        total_args = len(args.posonlyargs) + len(args.args)
        if total_args == 0:
            errors.append("`run()` must accept at least one argument: `ctx` (BlockContext) or `inputs, config`.")
        elif total_args > 2:
            warnings.append(f"`run()` has {total_args} positional args — expected 1 (ctx) or 2 (inputs, config).")

    # 3. Check for risky imports
    risky = {"subprocess", "ctypes", "pty", "atexit"}
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for alias in node.names:
                if alias.name in risky:
                    warnings.append(f"Import `{alias.name}` detected — use with caution inside a block.")
        elif isinstance(node, _ast.ImportFrom):
            if node.module in risky:
                warnings.append(f"Import from `{node.module}` detected — use with caution inside a block.")

    # 4. Check for top-level code outside functions/classes (not imports/docstrings)
    top_level_stmts = [
        n for n in tree.body
        if not isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef,
                               _ast.Import, _ast.ImportFrom, _ast.Expr))
    ]
    if top_level_stmts:
        warnings.append(
            f"{len(top_level_stmts)} top-level statement(s) outside functions detected — "
            "these will run on import, not on block execution."
        )

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


@router.get("/{type_id}")
def get_custom_block(type_id: str):
    """Get a single custom block by type ID."""
    if not SAFE_TYPE_ID.match(type_id):
        raise HTTPException(400, "Invalid block type id")
    block = _read_block(type_id)
    if not block:
        raise HTTPException(404, f"Custom block '{type_id}' not found")
    return block


@router.put("/{type_id}")
def update_custom_block(type_id: str, updates: CustomBlockUpdate):
    """Update an existing custom block."""
    if not SAFE_TYPE_ID.match(type_id):
        raise HTTPException(400, "Invalid block type id")
    existing = _read_block(type_id)
    if not existing:
        raise HTTPException(404, f"Custom block '{type_id}' not found")

    update_data = updates.model_dump(exclude_none=True)
    code = update_data.pop("code", existing.get("code", ""))
    merged = {**existing, **update_data}

    _write_block(type_id, merged, code)
    return _read_block(type_id)


@router.delete("/{type_id}")
def delete_custom_block(type_id: str):
    """Delete a custom block."""
    if not SAFE_TYPE_ID.match(type_id):
        raise HTTPException(400, "Invalid block type id")
    block_dir = _block_dir(type_id)
    if not block_dir.exists():
        raise HTTPException(404, f"Custom block '{type_id}' not found")
    shutil.rmtree(block_dir)
    return {"deleted": type_id}


@router.post("/{type_id}/test")
def test_custom_block(type_id: str, payload: dict | None = None):
    """Test-execute a custom block with sample data."""
    if not SAFE_TYPE_ID.match(type_id):
        raise HTTPException(400, "Invalid block type id")
    block_dir = _block_dir(type_id)
    run_py = block_dir / "run.py"
    if not run_py.exists():
        raise HTTPException(404, f"Custom block '{type_id}' not found or has no run.py")

    # Run in a subprocess with a timeout for safety
    # Pass paths and payload via environment/stdin to avoid injection
    import json as _json
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

ctx = BlockContext(
    run_dir="/tmp/blueprint_test",
    block_dir=os.environ["_BLUEPRINT_BLOCK_DIR"],
    config=config,
    inputs=inputs,
)
mod.run(ctx)
print(json.dumps({"outputs": ctx.get_outputs(), "success": True}))
"""
    env = {
        **os.environ,
        "_BLUEPRINT_ROOT": str(block_dir.parent.parent),
        "_BLUEPRINT_RUN_PY": str(run_py),
        "_BLUEPRINT_BLOCK_DIR": str(block_dir),
    }
    stdin_data = _json.dumps(payload or {})
    try:
        result = subprocess.run(
            [sys.executable, "-c", test_script],
            input=stdin_data,
            capture_output=True, text=True, timeout=30, env=env,
        )
        if result.returncode == 0:
            try:
                return _json.loads(result.stdout.strip().split("\n")[-1])
            except (ValueError, IndexError):
                return {"success": False, "error": "Block produced invalid output"}
        else:
            return {"success": False, "error": result.stderr or "Block execution failed"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Test timed out after 30 seconds"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _default_run_py(name: str) -> str:
    return f'''"""
{name} — Custom Block

Auto-generated scaffold. Edit to implement your block logic.
"""


def run(ctx):
    """Main block entry point.

    Args:
        ctx: BlockContext with .config, .inputs, .set_output(), .log(), .progress()
    """
    ctx.log("Running {name}...")

    # Access config values
    # value = ctx.config.get("my_param", "default")

    # Access input data
    # input_data = ctx.inputs.get("input", None)

    # Set output
    ctx.set_output("output", {{"status": "ok"}})
    ctx.log("{name} complete.")
'''
