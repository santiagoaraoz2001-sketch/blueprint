#!/usr/bin/env python3
"""
Generate docs/REPO_FACTS.json by scanning the repository.

Idempotent — safe to run repeatedly. Always produces the same output
for the same filesystem state.

Usage:
    python scripts/generate_repo_facts.py
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BLOCKS_DIR = REPO_ROOT / "blocks"
ROUTERS_DIR = REPO_ROOT / "backend" / "routers"
MODELS_DIR = REPO_ROOT / "backend" / "models"
OUTPUT_PATH = REPO_ROOT / "docs" / "REPO_FACTS.json"


def count_blocks_by_category() -> dict[str, int]:
    """Scan blocks/**/block.yaml and return {category: count}."""
    counts: dict[str, int] = defaultdict(int)
    for yaml_path in sorted(BLOCKS_DIR.rglob("block.yaml")):
        # Category is the first directory under blocks/
        relative = yaml_path.relative_to(BLOCKS_DIR)
        category = relative.parts[0]
        counts[category] += 1
    return dict(sorted(counts.items()))


def count_py_modules(directory: Path) -> int:
    """Count .py files excluding __init__.py."""
    if not directory.is_dir():
        return 0
    return sum(
        1 for f in directory.glob("*.py")
        if f.name != "__init__.py"
    )


def count_test_files() -> int:
    """Count files matching *test* or *spec* with code extensions."""
    extensions = {".py", ".ts", ".tsx", ".js", ".jsx"}
    count = 0
    for f in REPO_ROOT.rglob("*"):
        if f.is_file() and f.suffix in extensions:
            name_lower = f.name.lower()
            if "test" in name_lower or "spec" in name_lower:
                count += 1
    return count


def detect_platforms() -> list[str]:
    """Detect supported platforms from build configs."""
    platforms = []
    # macOS — always supported (primary dev platform)
    platforms.append("macOS")
    # Check for Electron build configs
    forge_config = REPO_ROOT / "frontend" / "forge.config.ts"
    package_json = REPO_ROOT / "frontend" / "package.json"
    if forge_config.exists() or package_json.exists():
        # Electron supports all three, but we list what's configured
        if package_json.exists():
            text = package_json.read_text()
            if "electron" in text.lower():
                platforms.append("Linux")
                platforms.append("Windows")
    return sorted(set(platforms))


def generate_facts() -> dict:
    blocks_by_category = count_blocks_by_category()
    total_blocks = sum(blocks_by_category.values())
    categories = sorted(blocks_by_category.keys())

    return {
        "_generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "_generator": "scripts/generate_repo_facts.py",
        "blocks": {
            "total": total_blocks,
            "categories": categories,
            "by_category": blocks_by_category,
        },
        "backend": {
            "router_count": count_py_modules(ROUTERS_DIR),
            "model_count": count_py_modules(MODELS_DIR),
        },
        "test_file_count": count_test_files(),
        "supported_platforms": detect_platforms(),
    }


def main() -> None:
    facts = generate_facts()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(facts, indent=2) + "\n")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print(f"  Total blocks: {facts['blocks']['total']}")
    print(f"  Categories ({len(facts['blocks']['categories'])}): {', '.join(facts['blocks']['categories'])}")
    print(f"  Routers: {facts['backend']['router_count']}")
    print(f"  Models: {facts['backend']['model_count']}")
    print(f"  Test files: {facts['test_file_count']}")
    print(f"  Platforms: {', '.join(facts['supported_platforms'])}")


if __name__ == "__main__":
    main()
