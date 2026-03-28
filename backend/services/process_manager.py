"""ProcessManager — tracks background processes spawned by the API.

Provides lifecycle management (start, status, stop) and integrates with
the server shutdown sequence to ensure no orphaned processes survive.

Architecture mirrors ``backend/routers/inference.py``'s ``_spawned_processes``
pattern but is centralised so that any endpoint (start-service, future
extensions) can spawn tracked processes.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("blueprint.processes")

# How long to wait for SIGTERM before escalating to SIGKILL.
_TERM_TIMEOUT_S = 5


@dataclass
class TrackedProcess:
    """Metadata for a process we launched and need to clean up."""
    name: str
    proc: subprocess.Popen
    command: list[str]
    started_at: float = field(default_factory=time.time)

    @property
    def alive(self) -> bool:
        return self.proc.poll() is None

    @property
    def pid(self) -> int:
        return self.proc.pid

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "pid": self.pid,
            "alive": self.alive,
            "command": " ".join(self.command),
            "uptime_s": round(time.time() - self.started_at, 1) if self.alive else 0,
            "returncode": self.proc.returncode,
        }


class ProcessManager:
    """Thread-safe registry of spawned child processes.

    One instance is created at startup and stored on ``app.state.process_manager``.
    ``shutdown()`` is called during the server shutdown sequence to kill all
    tracked processes with a SIGTERM → SIGKILL escalation.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processes: dict[str, TrackedProcess] = {}

    # ── Spawn / register ──────────────────────────────────────────

    def start(
        self,
        name: str,
        command: list[str],
        *,
        stdout: int | None = subprocess.DEVNULL,
        stderr: int | None = subprocess.DEVNULL,
    ) -> TrackedProcess:
        """Launch *command* and register under *name*.

        If a process with *name* is already alive, returns the existing one.
        If it is dead, replaces it with a new launch.
        """
        with self._lock:
            existing = self._processes.get(name)
            if existing and existing.alive:
                logger.info("Process %r already running (PID %d)", name, existing.pid)
                return existing

            logger.info("Starting process %r: %s", name, " ".join(command))
            proc = subprocess.Popen(command, stdout=stdout, stderr=stderr)
            tracked = TrackedProcess(name=name, proc=proc, command=command)
            self._processes[name] = tracked
            logger.info("Process %r started (PID %d)", name, proc.pid)
            return tracked

    # ── Query ─────────────────────────────────────────────────────

    def get(self, name: str) -> TrackedProcess | None:
        with self._lock:
            return self._processes.get(name)

    def list_all(self) -> list[TrackedProcess]:
        with self._lock:
            return list(self._processes.values())

    def is_alive(self, name: str) -> bool:
        with self._lock:
            tp = self._processes.get(name)
            return tp is not None and tp.alive

    # ── Stop individual ───────────────────────────────────────────

    def stop(self, name: str, *, timeout: float = _TERM_TIMEOUT_S) -> bool:
        """Stop a single tracked process by name.

        Uses SIGTERM → wait → SIGKILL escalation.
        Returns True if the process was found and stopped.
        """
        with self._lock:
            tp = self._processes.get(name)
            if tp is None:
                return False

        if not tp.alive:
            return True

        self._terminate(tp, timeout=timeout)
        return True

    # ── Shutdown all (called during server exit) ──────────────────

    def shutdown(self) -> None:
        """Kill all tracked processes.  Idempotent.

        Called from ``_full_shutdown()`` in ``main.py``.
        """
        with self._lock:
            live = [(n, tp) for n, tp in self._processes.items() if tp.alive]
            if not live:
                return
            logger.info("Shutting down %d tracked process(es)...", len(live))

        for name, tp in live:
            self._terminate(tp, timeout=_TERM_TIMEOUT_S)

        with self._lock:
            self._processes.clear()

        logger.info("All tracked processes stopped.")

    # ── Internal ──────────────────────────────────────────────────

    @staticmethod
    def _terminate(tp: TrackedProcess, *, timeout: float = _TERM_TIMEOUT_S) -> None:
        """SIGTERM → wait → SIGKILL a single process."""
        if not tp.alive:
            return
        try:
            logger.info("Stopping %r (PID %d) with SIGTERM...", tp.name, tp.pid)
            tp.proc.terminate()
            try:
                tp.proc.wait(timeout=timeout)
                logger.info("%r (PID %d) stopped gracefully.", tp.name, tp.pid)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "%r (PID %d) did not stop after %.1fs, sending SIGKILL...",
                    tp.name, tp.pid, timeout,
                )
                tp.proc.kill()
                tp.proc.wait(timeout=2)
                logger.info("%r (PID %d) killed.", tp.name, tp.pid)
        except Exception as exc:
            logger.warning("Failed to stop %r (PID %d): %s", tp.name, tp.pid, exc)


# ── Module-level singleton ────────────────────────────────────────────

_instance: ProcessManager | None = None


def get_process_manager() -> ProcessManager:
    """Return the module-level singleton, creating on first access."""
    global _instance
    if _instance is None:
        _instance = ProcessManager()
    return _instance


def set_process_manager(mgr: ProcessManager) -> None:
    """Install the app-level singleton.  Called once by ``main.py``."""
    global _instance
    _instance = mgr
