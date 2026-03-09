import os
import re
import yaml
from pathlib import Path
from fastapi import APIRouter, HTTPException

from ..config import BUILTIN_BLOCKS_DIR, BLOCKS_DIR

SAFE_BLOCK_NAME = re.compile(r'^[a-zA-Z0-9_]+$')

router = APIRouter(prefix="/api/blocks", tags=["blocks"])


def _scan_blocks(directory: Path, source: str = "builtin") -> list[dict]:
    """Scan a directory for blocks (dirs containing block.yaml)."""
    blocks = []
    if not directory.exists():
        return blocks
    for category_dir in sorted(directory.iterdir()):
        if not category_dir.is_dir():
            continue
        for block_dir in sorted(category_dir.iterdir()):
            yaml_path = block_dir / "block.yaml"
            if yaml_path.exists():
                with open(yaml_path) as f:
                    meta = yaml.safe_load(f)
                meta["source"] = source
                meta["path"] = str(block_dir)
                blocks.append(meta)
    return blocks


@router.get("/library")
def list_blocks():
    """List all available blocks (built-in + custom)."""
    builtin = _scan_blocks(BUILTIN_BLOCKS_DIR, "builtin")
    custom = _scan_blocks(BLOCKS_DIR, "custom")
    return builtin + custom


@router.get("/marketplace")
def marketplace():
    """Browse available blocks for installation."""
    # For now, return built-in blocks as the marketplace catalog
    return _scan_blocks(BUILTIN_BLOCKS_DIR, "builtin")


@router.get("/{block_name}")
def get_block(block_name: str):
    """Get block detail by name."""
    if not SAFE_BLOCK_NAME.match(block_name):
        raise HTTPException(400, "Invalid block name")
    for directory in [BUILTIN_BLOCKS_DIR, BLOCKS_DIR]:
        if not directory.exists():
            continue
        for category_dir in directory.iterdir():
            if not category_dir.is_dir():
                continue
            block_dir = category_dir / block_name
            yaml_path = block_dir / "block.yaml"
            if yaml_path.exists():
                with open(yaml_path) as f:
                    meta = yaml.safe_load(f)
                meta["path"] = str(block_dir)
                # Try to read README
                readme_path = block_dir / "README.md"
                if readme_path.exists():
                    meta["readme"] = readme_path.read_text()
                return meta
    return {"error": "Block not found"}


@router.get("/{block_name}/source")
def get_block_source(block_name: str):
    """Get the run.py source code for a block."""
    if not SAFE_BLOCK_NAME.match(block_name):
        raise HTTPException(400, "Invalid block name")
    for directory in [BUILTIN_BLOCKS_DIR, BLOCKS_DIR]:
        if not directory.exists():
            continue
        for category_dir in directory.iterdir():
            if not category_dir.is_dir():
                continue
            run_py = category_dir / block_name / "run.py"
            if run_py.exists():
                return {"block": block_name, "source": run_py.read_text()}
    raise HTTPException(404, f"Source not found for block '{block_name}'")
