"""Block Registry — discovers all available blocks by scanning the blocks/ directory."""

import os
from pathlib import Path
from typing import Optional

# Root blocks directory
BLOCKS_DIR = Path(__file__).parent.parent.parent / "blocks"

# Cache of discovered block types
_registry: dict[str, dict] = {}
_scanned = False


def scan_blocks() -> dict[str, dict]:
    """Scan the blocks/ directory and build a registry of available block types."""
    global _registry, _scanned
    if _scanned:
        return _registry

    _registry = {}
    if not BLOCKS_DIR.exists():
        _scanned = True
        return _registry

    for category_dir in sorted(BLOCKS_DIR.iterdir()):
        if not category_dir.is_dir() or category_dir.name.startswith(('.', '_')):
            continue
        category = category_dir.name
        for block_dir in sorted(category_dir.iterdir()):
            if not block_dir.is_dir() or block_dir.name.startswith(('.', '_')):
                continue
            run_file = block_dir / "run.py"
            if run_file.exists():
                block_type = block_dir.name
                _registry[block_type] = {
                    "type": block_type,
                    "category": category,
                    "path": str(block_dir),
                    "has_run": True,
                }

    _scanned = True
    return _registry


def get_block_types() -> set[str]:
    """Return all known block type identifiers."""
    return set(scan_blocks().keys())


def is_known_block(block_type: str) -> bool:
    """Check if a block type exists in the registry."""
    return block_type in scan_blocks()


def get_block_info(block_type: str) -> Optional[dict]:
    """Get info about a specific block type."""
    return scan_blocks().get(block_type)


def get_category(block_type: str) -> str:
    """Get the category of a block type."""
    info = get_block_info(block_type)
    return info["category"] if info else "unknown"
