#!/usr/bin/env python3
"""Watch block.yaml files and regenerate TypeScript registry on changes.

Usage:
    python3 scripts/watch_block_registry.py

Polls blocks/**/block.yaml for mtime changes every 2 seconds.
On change, re-runs generate_block_registry.main().
"""

import signal
import sys
import time
from pathlib import Path

# Ensure sibling imports work regardless of cwd
sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_block_registry import main as generate  # noqa: E402
from generate_port_compat import main as generate_port_compat  # noqa: E402

BLOCKS_DIR = Path(__file__).resolve().parent.parent / "blocks"
PORT_COMPAT_PATH = Path(__file__).resolve().parent.parent / "docs" / "PORT_COMPATIBILITY.yaml"


def get_mtimes() -> dict[str, float]:
    """Get modification times for all block.yaml files and PORT_COMPATIBILITY.yaml.

    Handles race conditions where a file may be deleted between
    discovery and stat.
    """
    mtimes: dict[str, float] = {}
    for p in BLOCKS_DIR.rglob("block.yaml"):
        try:
            mtimes[str(p)] = p.stat().st_mtime
        except OSError:
            # File was deleted/moved between rglob and stat — skip it
            continue
    # Also watch PORT_COMPATIBILITY.yaml
    try:
        mtimes[str(PORT_COMPAT_PATH)] = PORT_COMPAT_PATH.stat().st_mtime
    except OSError:
        pass
    return mtimes


def watch() -> None:
    """Poll for block.yaml changes and regenerate the registry."""
    last_mtimes = get_mtimes()
    print(
        f"Watching {len(last_mtimes)} block.yaml files for changes...",
        flush=True,
    )

    while True:
        time.sleep(2)
        current = get_mtimes()
        if current != last_mtimes:
            changed = set(current.keys()) ^ set(last_mtimes.keys())
            modified = {
                k for k in current.keys() & last_mtimes.keys()
                if current[k] != last_mtimes[k]
            }
            all_changed = changed | modified
            print(
                f"Block schema changed ({len(all_changed)} file(s)), "
                "regenerating registry...",
                flush=True,
            )
            try:
                generate()
                generate_port_compat()
            except SystemExit:
                # generate() calls sys.exit(1) on zero blocks — don't let
                # that kill the watcher; log and continue polling
                print(
                    "WARNING: Codegen exited with error, will retry on "
                    "next change",
                    file=sys.stderr,
                    flush=True,
                )
            except Exception as e:
                print(
                    f"ERROR: Codegen failed: {e}",
                    file=sys.stderr,
                    flush=True,
                )
            last_mtimes = current


def _handle_shutdown(signum: int, _frame: object) -> None:
    """Handle SIGINT/SIGTERM for clean shutdown."""
    sig_name = signal.Signals(signum).name
    print(f"\n{sig_name} received, stopping watcher.", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)
    watch()
