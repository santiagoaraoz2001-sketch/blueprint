#!/usr/bin/env python3
"""Validate all blocks using the BlockRegistryService.

Instantiates the registry, runs discovery, and prints a health report.
Exits with code 1 if any blocks are broken.

Usage:
    python scripts/validate_blocks.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path so `backend.*` imports work
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import BLOCKS_DIR, BUILTIN_BLOCKS_DIR, CUSTOM_BLOCKS_DIR
from backend.services.registry import BlockRegistryService


def main() -> int:
    registry = BlockRegistryService()
    registry.discover_all([BUILTIN_BLOCKS_DIR, BLOCKS_DIR, CUSTOM_BLOCKS_DIR])

    health = registry.get_health()
    print(f"Block Registry Health Report")
    print(f"{'=' * 40}")
    print(f"  Total blocks:  {health['total']}")
    print(f"  Valid blocks:  {health['valid']}")
    print(f"  Broken blocks: {health['broken']}")
    print(f"  Version:       {health['version']}")

    if health["broken_blocks"]:
        print(f"\nBroken blocks:")
        for bt in health["broken_blocks"]:
            block = registry.get(bt)
            print(f"  - {bt} ({block.source_path if block else 'unknown'})")
        print(f"\nFAILED: {health['broken']} broken block(s) found.")
        return 1

    print(f"\nAll {health['total']} blocks are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
