"""Worker process tracking for subprocess-based block execution.

Tracks child PIDs per run so they can be terminated on shutdown or crash.
Provides stale-run recovery on startup: runs left in 'running' or 'pending'
status when Blueprint crashed are reclassified as 'crashed'.
"""

import atexit
import json
import logging
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_logger = logging.getLogger("blueprint.worker_tracker")

# Module-level dict: run_id -> list[Popen]
_tracked_workers: dict[str, list[subprocess.Popen]] = {}
_tracker_lock = threading.Lock()


def track_worker(run_id: str, proc: subprocess.Popen) -> None:
    """Register a worker subprocess for a given run."""
    with _tracker_lock:
        if run_id not in _tracked_workers:
            _tracked_workers[run_id] = []
        _tracked_workers[run_id].append(proc)


def untrack_worker(run_id: str, proc: subprocess.Popen) -> None:
    """Remove a worker subprocess from tracking (e.g. after it exits)."""
    with _tracker_lock:
        workers = _tracked_workers.get(run_id, [])
        try:
            workers.remove(proc)
        except ValueError:
            pass
        if not workers:
            _tracked_workers.pop(run_id, None)


def untrack_run(run_id: str) -> None:
    """Remove all tracked workers for a run."""
    with _tracker_lock:
        _tracked_workers.pop(run_id, None)


def get_tracked_pids() -> dict[str, list[int]]:
    """Return a snapshot of tracked run_id -> list[PID]."""
    with _tracker_lock:
        return {
            run_id: [p.pid for p in procs if p.poll() is None]
            for run_id, procs in _tracked_workers.items()
        }


def terminate_all_workers() -> int:
    """Terminate all tracked worker processes. Returns count terminated.

    Called during application shutdown to ensure no orphaned workers survive.
    Uses SIGTERM first, then SIGKILL after 5 seconds.
    """
    count = 0
    with _tracker_lock:
        all_procs = [
            (run_id, proc)
            for run_id, procs in _tracked_workers.items()
            for proc in procs
        ]

    for run_id, proc in all_procs:
        if proc.poll() is not None:
            continue  # Already exited
        try:
            proc.terminate()
            count += 1
            _logger.info("Terminated worker PID %d for run %s", proc.pid, run_id)
        except OSError:
            pass

    # Wait up to 5s for graceful termination, then force-kill
    import time
    deadline = time.time() + 5.0
    for run_id, proc in all_procs:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        try:
            proc.wait(timeout=max(0.1, remaining))
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
                _logger.warning("Force-killed worker PID %d for run %s", proc.pid, run_id)
            except OSError:
                pass

    with _tracker_lock:
        _tracked_workers.clear()

    return count


def write_pid_manifest(data_dir: Path) -> None:
    """Write a PID manifest file for orphan detection after hard kills.

    The manifest records the main process PID and all tracked worker PIDs,
    so external tooling (or the next startup) can detect orphans.
    """
    manifest = {
        "main_pid": os.getpid(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workers": get_tracked_pids(),
    }
    manifest_path = data_dir / "worker_manifest.json"
    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
    except Exception as exc:
        _logger.warning("Failed to write PID manifest: %s", exc)


def recover_stale_runs_on_startup(session_factory) -> list[str]:
    """Recover runs stuck in 'running' or 'pending' status after a crash.

    Called during application startup. Finds all runs with status='running'
    or status='pending' and reclassifies them as 'crashed'.

    Args:
        session_factory: Callable that returns a new DB session.

    Returns:
        List of recovered run IDs.
    """
    from ..models.run import Run, LiveRun

    session = session_factory()
    recovered_ids = []

    try:
        stale_runs = session.query(Run).filter(
            Run.status.in_(["running", "pending"])
        ).all()

        for run in stale_runs:
            original_status = run.status
            run.status = "crashed"
            run.error_message = (
                "Blueprint was restarted while this run was in progress. "
                "Run data up to the crash point is preserved."
            )
            run.finished_at = datetime.now(timezone.utc)

            # Update corresponding LiveRun
            live = session.query(LiveRun).filter(
                LiveRun.run_id == run.id
            ).first()
            if live:
                live.status = "crashed"

            recovered_ids.append(run.id)
            _logger.info(
                "Recovered stale run %s (was '%s' -> 'crashed')",
                run.id, original_status,
            )

        if recovered_ids:
            session.commit()
            _logger.info("Recovered %d stale run(s) on startup", len(recovered_ids))
    except Exception as exc:
        try:
            session.rollback()
        except Exception:
            pass
        _logger.warning("Stale run recovery on startup failed: %s", exc)
    finally:
        session.close()

    return recovered_ids
