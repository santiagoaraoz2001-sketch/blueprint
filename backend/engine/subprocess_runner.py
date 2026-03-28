"""Subprocess-based block execution runner.

Provides SubprocessBlockRunner which launches block_worker.py as a child
process, making timeout and cancel truly enforceable via proc.kill().
Unlike the daemon-thread approach in executor.py, this guarantees process
termination even for blocks that ignore cancellation signals.
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

from ..block_sdk.exceptions import BlockTimeoutError, BlockExecutionError
from .error_classifier import classify_error
from .data_serializer import serialize_inputs, deserialize_outputs

_logger = logging.getLogger("blueprint.subprocess_runner")

# Path to the block_worker.py entry point
_WORKER_SCRIPT = str(Path(__file__).parent / "block_worker.py")


class SubprocessBlockRunner:
    """Runs blocks in isolated subprocesses with real timeout/cancel support.

    Usage:
        runner = SubprocessBlockRunner()
        outputs, fingerprints = runner.run_block("llm_inference", config, inputs)

    The subprocess writes progress to a JSON-lines file which this runner
    polls and forwards to the provided SSE callback.
    """

    def run_block(
        self,
        block_type: str,
        config: dict,
        inputs: dict[str, Any],
        timeout_seconds: int = 3600,
        progress_callback: Callable[[float, str], None] | None = None,
        run_id: str | None = None,
        node_id: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, dict]]:
        """Execute a block in a subprocess.

        Args:
            block_type: The block type identifier.
            config: Block configuration dict.
            inputs: Input data dict (supports numpy arrays, torch tensors,
                    pandas DataFrames, and any picklable object).
            timeout_seconds: Maximum execution time (default 1 hour).
            progress_callback: Optional callback(percent, message) for progress.
            run_id: Optional run ID for tracking.
            node_id: Optional node ID for tracking.

        Returns:
            Tuple of (outputs_dict, data_fingerprints_dict).

        Raises:
            BlockTimeoutError: If the block exceeds timeout_seconds.
            BlockExecutionError: If the block exits with an error.
        """
        # Create temp directories for I/O
        work_dir = tempfile.mkdtemp(prefix="blueprint_worker_")
        input_dir = os.path.join(work_dir, "inputs")
        output_dir = os.path.join(work_dir, "outputs")
        progress_file = os.path.join(work_dir, "progress.jsonl")

        # Create empty progress file
        with open(progress_file, "w") as f:
            pass

        try:
            # Serialize inputs (handles numpy, torch, pandas, pickle fallback)
            serialize_inputs(inputs, input_dir)

            # Build command
            cmd = [
                sys.executable,
                _WORKER_SCRIPT,
                "--block-type", block_type,
                "--config", json.dumps(config),
                "--input-dir", input_dir,
                "--output-dir", output_dir,
                "--progress-file", progress_file,
            ]

            # Launch subprocess
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Store proc for external cancellation
            self._current_proc = proc
            self._current_run_id = run_id

            # Poll progress file in a background thread
            stop_polling = threading.Event()
            last_line_count = [0]

            def poll_progress():
                while not stop_polling.is_set():
                    stop_polling.wait(2.0)
                    if stop_polling.is_set():
                        break
                    try:
                        with open(progress_file, "r") as f:
                            lines = f.readlines()
                        new_lines = lines[last_line_count[0]:]
                        last_line_count[0] = len(lines)
                        for line in new_lines:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                entry = json.loads(line)
                                if progress_callback and entry.get("percent", -1) >= 0:
                                    progress_callback(
                                        entry["percent"],
                                        entry.get("message", ""),
                                    )
                            except (json.JSONDecodeError, KeyError):
                                pass
                    except FileNotFoundError:
                        pass

            poll_thread = threading.Thread(target=poll_progress, daemon=True)
            poll_thread.start()

            try:
                stdout, stderr = proc.communicate(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                # Kill the process — this actually works (unlike threads)
                proc.kill()
                try:
                    proc.communicate(timeout=5)
                except Exception:
                    pass
                raise BlockTimeoutError(
                    timeout_seconds,
                    f"Block '{block_type}' exceeded {timeout_seconds}s timeout "
                    f"(subprocess killed)",
                )
            finally:
                stop_polling.set()
                self._current_proc = None

            # Check exit code
            if proc.returncode != 0:
                # Parse structured error from stderr
                error_msg = stderr.strip() if stderr else f"Block {block_type} failed"

                # Check for BLOCK_ERROR structured format
                for line in (stderr or "").splitlines():
                    if line.startswith("BLOCK_ERROR:"):
                        parts = line.split(":", 2)
                        if len(parts) >= 3:
                            error_type = parts[1]
                            error_detail = parts[2]
                            error_msg = f"[{error_type}] {error_detail}"
                            break

                # Classify error
                exc = RuntimeError(error_msg)
                classified = classify_error(exc, block_type=block_type)

                raise BlockExecutionError(
                    f"[{classified.title}] {classified.message}",
                    details=error_msg[:2000],
                )

            # Deserialize outputs (handles numpy, torch, pandas, pickle)
            outputs = deserialize_outputs(output_dir)

            # Read data fingerprints (written by block_worker.py)
            fingerprints = self._read_fingerprints(output_dir)

            return outputs, fingerprints

        finally:
            # Clean up temp directory (best-effort)
            try:
                import shutil
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass

    def cancel(self, proc: subprocess.Popen | None = None) -> None:
        """Cancel a running subprocess block.

        Args:
            proc: The Popen object to cancel. If None, cancels the
                  current running block (if any).
        """
        target = proc or getattr(self, "_current_proc", None)
        if target is None:
            return

        try:
            target.terminate()
        except OSError:
            return

        # Wait up to 5 seconds for graceful termination
        try:
            target.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Force kill
            try:
                target.kill()
                target.wait(timeout=5)
            except Exception:
                pass

    @staticmethod
    def _read_fingerprints(output_dir: str) -> dict[str, dict]:
        """Read data fingerprints written by the subprocess worker.

        The worker writes fingerprints.json to the output directory after
        successful block execution.
        """
        fp_path = os.path.join(output_dir, "fingerprints.json")
        if not os.path.exists(fp_path):
            return {}
        try:
            with open(fp_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            _logger.warning("Failed to read subprocess fingerprints: %s", exc)
            return {}

    _current_proc: subprocess.Popen | None = None
    _current_run_id: str | None = None
