"""Background file watcher for the workspace inbox directory.

Monitors the inbox folder for new files and auto-categorizes them into
the appropriate workspace subdirectory with proper naming convention.

Uses the same poll-based pattern as utils/model_watcher.py — no external
dependencies, fully cross-platform.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from pathlib import Path

from .workspace_manager import WorkspaceManager

logger = logging.getLogger(__name__)

# ── Module-level watcher state ──

_watcher_thread: threading.Thread | None = None
_stop_event = threading.Event()
_watcher_status: dict = {"running": False, "error": None, "last_poll": None, "files_processed": 0}

POLL_INTERVAL = 3.0  # seconds
DEBOUNCE_SECONDS = 2.0  # wait for file to be fully written


def _poll_inbox(manager: WorkspaceManager) -> None:
    """Main poll loop. Runs in a daemon thread."""
    global _watcher_status

    inbox_dir = manager.root / "inbox"
    # Track file sizes for debounce (path -> (size, first_seen_time))
    pending: dict[str, tuple[int, float]] = {}

    logger.info("Inbox watcher started: %s", inbox_dir)
    _watcher_status["running"] = True
    _watcher_status["error"] = None

    while not _stop_event.is_set():
        try:
            if not inbox_dir.is_dir():
                _stop_event.wait(POLL_INTERVAL)
                continue

            now = time.time()
            current_files: set[str] = set()

            for entry in inbox_dir.iterdir():
                if not entry.is_file():
                    continue
                # Skip hidden files and partial downloads
                if entry.name.startswith(".") or entry.name.endswith(".part") or entry.name.endswith(".crdownload"):
                    continue

                fpath = str(entry)
                current_files.add(fpath)

                try:
                    size = entry.stat().st_size
                except OSError:
                    continue  # File disappeared

                if size == 0:
                    continue  # Skip empty files

                # Debounce: track file size stability
                if fpath in pending:
                    prev_size, first_seen = pending[fpath]
                    if size != prev_size:
                        # Size changed — still being written, reset timer
                        pending[fpath] = (size, now)
                        continue
                    if now - first_seen < DEBOUNCE_SECONDS:
                        # Not enough time has passed
                        continue
                    # File is stable — process it
                else:
                    # First time seeing this file
                    pending[fpath] = (size, now)
                    continue

                # Determine destination
                subfolder = manager.get_extension_subfolder(entry.name)
                if not subfolder:
                    logger.debug("Inbox: unknown extension for %s, leaving in inbox", entry.name)
                    del pending[fpath]
                    continue

                # Rename and move
                try:
                    new_name = manager.rename_for_workspace(entry.name, subfolder)
                    target_dir = manager.root / subfolder
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target_path = manager.deduplicate_path(target_dir, new_name)

                    shutil.move(str(entry), str(target_path))
                    logger.info("Inbox: %s → %s/%s", entry.name, subfolder, target_path.name)
                    _watcher_status["files_processed"] += 1
                except PermissionError:
                    logger.warning("Inbox: permission denied moving %s, will retry", entry.name)
                except OSError as e:
                    logger.error("Inbox: OS error moving %s: %s", entry.name, e)
                    _watcher_status["error"] = str(e)

                # Remove from pending regardless
                pending.pop(fpath, None)

            # Clean up pending entries for files that no longer exist
            stale = [p for p in pending if p not in current_files]
            for p in stale:
                del pending[p]

            _watcher_status["last_poll"] = now

        except Exception as e:
            logger.error("Inbox watcher error: %s", e)
            _watcher_status["error"] = str(e)

        _stop_event.wait(POLL_INTERVAL)

    _watcher_status["running"] = False
    logger.info("Inbox watcher stopped")


def start_watcher(root_path: str) -> None:
    """Start the inbox watcher daemon thread."""
    global _watcher_thread

    if _watcher_thread and _watcher_thread.is_alive():
        logger.warning("Inbox watcher already running")
        return

    manager = WorkspaceManager(root_path)
    inbox_dir = manager.root / "inbox"
    if not inbox_dir.is_dir():
        manager.ensure_structure()

    _stop_event.clear()
    _watcher_thread = threading.Thread(
        target=_poll_inbox,
        args=(manager,),
        daemon=True,
        name="inbox-watcher",
    )
    _watcher_thread.start()


def stop_watcher() -> None:
    """Stop the inbox watcher."""
    global _watcher_thread
    _stop_event.set()
    if _watcher_thread and _watcher_thread.is_alive():
        _watcher_thread.join(timeout=5.0)
    _watcher_thread = None
    _watcher_status["running"] = False


def get_watcher_status() -> dict:
    """Return the current watcher status."""
    return dict(_watcher_status)


def is_watcher_running() -> bool:
    """Check if the watcher is currently running."""
    return _watcher_status.get("running", False)
