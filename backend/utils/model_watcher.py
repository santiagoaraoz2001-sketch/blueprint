"""Filesystem watcher for local model directories.

Monitors model directories for changes using stdlib-only polling and
triggers re-scans via the :mod:`model_scanner` when modifications are
detected.  No external dependencies — only ``os``, ``hashlib``,
``threading``, and ``time``.

Usage::

    from utils.model_watcher import start_watcher, stop_watcher

    def handle_models(models):
        print(f"Found {len(models)} local models")

    watcher = start_watcher(on_change=handle_models)
    # ... later ...
    stop_watcher()
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .model_scanner import DEFAULT_SCAN_PATHS, LocalModelInfo, scan_directories

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Directory fingerprinting
# ---------------------------------------------------------------------------


def _fingerprint_directory(directory: str) -> str:
    """Compute a lightweight fingerprint for a directory tree.

    The fingerprint is a SHA-256 hex-digest derived from the sorted list of
    ``(relative_path, size_bytes, mtime_ns)`` tuples for every file under
    *directory*.  Any change to filenames, file sizes, or modification times
    will produce a different digest.

    Directories that do not exist or cannot be read produce a stable sentinel
    value (``"missing"``), so the caller never has to handle exceptions.
    """
    root = Path(os.path.expanduser(directory))
    if not root.exists() or not root.is_dir():
        return "missing"

    entries: list[str] = []
    try:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
                relative = path.relative_to(root)
                entries.append(f"{relative}|{stat.st_size}|{stat.st_mtime_ns}")
            except OSError:
                # Individual file stat failures are non-fatal.
                continue
    except OSError as exc:
        logger.debug("Could not walk %s for fingerprinting: %s", directory, exc)
        return "error"

    if not entries:
        return "empty"

    digest = hashlib.sha256("\n".join(entries).encode()).hexdigest()
    return digest


# ---------------------------------------------------------------------------
# ModelDirectoryWatcher
# ---------------------------------------------------------------------------


class ModelDirectoryWatcher:
    """Poll-based filesystem watcher for model directories.

    Parameters
    ----------
    paths:
        Directories to monitor.  ``None`` uses the scanner defaults
        (``~/.specific-labs/models/``, ``~/.ollama/models/``,
        ``~/.cache/huggingface/hub/``).
    poll_interval:
        Seconds between filesystem polls.  Lower values are more responsive
        but consume more I/O.
    debounce_seconds:
        After a change is detected, wait this many additional seconds for the
        filesystem to stabilise before running a full scan.  Prevents partial
        reads while large files are being written.
    on_change:
        Callback invoked with the updated ``list[LocalModelInfo]`` whenever a
        change is detected and re-scanned.  Called on the watcher thread — if
        the consumer needs to update UI or async state, it must dispatch
        accordingly.
    """

    def __init__(
        self,
        paths: list[str] | None = None,
        poll_interval: float = 30.0,
        debounce_seconds: float = 2.0,
        on_change: Callable[[list[LocalModelInfo]], None] | None = None,
    ) -> None:
        self._paths: list[str] = paths if paths is not None else list(DEFAULT_SCAN_PATHS)
        self._poll_interval: float = max(poll_interval, 1.0)
        self._debounce_seconds: float = max(debounce_seconds, 0.0)
        self._on_change: Callable[[list[LocalModelInfo]], None] | None = on_change

        # Fingerprints keyed by directory path.
        self._fingerprints: dict[str, str] = {}

        # Threading primitives.
        self._stop_event: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock: threading.Lock = threading.Lock()

        # Observable state.
        self._last_scan_time: float | None = None

    # -- Properties ---------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Return ``True`` if the watcher thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def last_scan_time(self) -> float | None:
        """Epoch timestamp of the most recent successful scan, or ``None``."""
        return self._last_scan_time

    # -- Lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Start the background polling thread.

        If the watcher is already running this is a no-op (with a warning).
        """
        if self.is_running:
            logger.warning("ModelDirectoryWatcher is already running — ignoring start()")
            return

        logger.info(
            "Starting model directory watcher (poll every %.1fs, debounce %.1fs) on paths: %s",
            self._poll_interval,
            self._debounce_seconds,
            self._paths,
        )

        self._stop_event.clear()

        # Take an initial fingerprint snapshot so the first poll only fires if
        # something truly changed after startup.
        self._fingerprints = self._snapshot_fingerprints()

        self._thread = threading.Thread(
            target=self._run,
            name="model-directory-watcher",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the watcher thread to stop and wait for it to finish.

        Safe to call even if the watcher is not running.
        """
        if not self.is_running:
            logger.debug("ModelDirectoryWatcher.stop() called but watcher is not running")
            return

        logger.info("Stopping model directory watcher …")
        self._stop_event.set()

        thread = self._thread
        if thread is not None:
            thread.join(timeout=self._poll_interval + 5.0)
            if thread.is_alive():
                logger.warning("Watcher thread did not exit within the expected timeout")

        self._thread = None
        logger.info("Model directory watcher stopped")

    # -- Internal -----------------------------------------------------------

    def _snapshot_fingerprints(self) -> dict[str, str]:
        """Return a ``{path: fingerprint}`` mapping for all watched dirs."""
        result: dict[str, str] = {}
        for path in self._paths:
            result[path] = _fingerprint_directory(path)
        return result

    def _has_changes(self, new_fingerprints: dict[str, str]) -> bool:
        """Compare *new_fingerprints* against the stored baseline."""
        if set(new_fingerprints.keys()) != set(self._fingerprints.keys()):
            return True
        for path, fp in new_fingerprints.items():
            if fp != self._fingerprints.get(path):
                return True
        return False

    def _run(self) -> None:
        """Main loop executed on the daemon thread."""
        logger.debug("Watcher thread started")

        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception:
                # Absolutely never let an unhandled exception kill the thread.
                logger.exception("Unexpected error during watcher poll — continuing")

            # Use Event.wait() instead of time.sleep() so that stop() can
            # interrupt the sleep immediately.
            if self._stop_event.wait(timeout=self._poll_interval):
                break  # stop() was called during the wait

        logger.debug("Watcher thread exiting")

    def _poll_once(self) -> None:
        """Perform a single poll cycle: fingerprint, debounce, scan."""
        new_fingerprints = self._snapshot_fingerprints()

        if not self._has_changes(new_fingerprints):
            return

        logger.info("Filesystem change detected in model directories")

        # -- Debounce: wait for the filesystem to settle --
        if self._debounce_seconds > 0:
            logger.debug("Debouncing for %.1fs …", self._debounce_seconds)

            # Wait in small increments so we can bail out quickly on stop().
            deadline = time.monotonic() + self._debounce_seconds
            while time.monotonic() < deadline:
                if self._stop_event.is_set():
                    return
                remaining = deadline - time.monotonic()
                self._stop_event.wait(timeout=min(remaining, 0.25))

            # Re-fingerprint after the debounce window — the filesystem may
            # have continued to change.  We use the *latest* snapshot as the
            # new baseline regardless.
            new_fingerprints = self._snapshot_fingerprints()

        # -- Scan --
        logger.info("Running model re-scan …")
        try:
            models = scan_directories(self._paths)
            self._last_scan_time = time.time()
            logger.info("Re-scan complete: %d model(s) found", len(models))
        except Exception:
            logger.exception("Model re-scan failed")
            # Update fingerprints anyway so we don't re-trigger on every poll
            # for a permanently broken directory.
            with self._lock:
                self._fingerprints = new_fingerprints
            return

        # Update stored fingerprints *before* invoking the callback so that a
        # slow callback doesn't cause duplicate scans.
        with self._lock:
            self._fingerprints = new_fingerprints

        # -- Notify --
        if self._on_change is not None:
            try:
                self._on_change(models)
            except Exception:
                logger.exception("on_change callback raised an exception")


# ---------------------------------------------------------------------------
# Module-level convenience API
# ---------------------------------------------------------------------------

_global_watcher: ModelDirectoryWatcher | None = None
_global_lock: threading.Lock = threading.Lock()


def start_watcher(
    on_change: Callable[[list[LocalModelInfo]], None] | None = None,
    paths: list[str] | None = None,
    poll_interval: float = 30.0,
    debounce_seconds: float = 2.0,
) -> ModelDirectoryWatcher:
    """Create (or return the existing) global :class:`ModelDirectoryWatcher`.

    If a watcher is already running it will be stopped first so that the new
    configuration takes effect.

    Parameters
    ----------
    on_change:
        Callback invoked with the updated model list on every change.
    paths:
        Directories to monitor (``None`` → scanner defaults).
    poll_interval:
        Seconds between polls.
    debounce_seconds:
        Post-change stabilisation delay before scanning.

    Returns
    -------
    ModelDirectoryWatcher
        The running watcher instance.
    """
    global _global_watcher

    with _global_lock:
        if _global_watcher is not None and _global_watcher.is_running:
            logger.info("Replacing existing global model watcher")
            _global_watcher.stop()

        _global_watcher = ModelDirectoryWatcher(
            paths=paths,
            poll_interval=poll_interval,
            debounce_seconds=debounce_seconds,
            on_change=on_change,
        )
        _global_watcher.start()
        return _global_watcher


def stop_watcher() -> None:
    """Stop the global :class:`ModelDirectoryWatcher`, if one is running."""
    global _global_watcher

    with _global_lock:
        if _global_watcher is not None:
            _global_watcher.stop()
            _global_watcher = None
        else:
            logger.debug("stop_watcher() called but no global watcher exists")
