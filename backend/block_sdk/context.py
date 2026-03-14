"""
BlockContext — The SDK interface for block authors.

Every block's run.py receives a BlockContext instance:

    def run(ctx: BlockContext):
        data = ctx.load_input("dataset")
        ctx.report_progress(50, 100)
        ctx.log_metric("accuracy", 0.95)
        ctx.save_output("result", output_path)
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from ..utils.data_fingerprint import fingerprint_dataset


class BlockContext:
    def __init__(
        self,
        run_dir: str,
        block_dir: str,
        config: dict,
        inputs: dict[str, str],
        project_name: str = "",
        experiment_name: str = "",
        progress_callback=None,
        message_callback=None,
        metric_callback=None,
    ):
        self.run_dir = run_dir
        self.block_dir = block_dir
        self.config = config
        self._inputs = inputs
        # Public alias so blocks can use either ctx.inputs.get() or ctx.load_input()
        self.inputs = inputs
        self.project_name = project_name
        self.experiment_name = experiment_name
        self._progress_callback = progress_callback
        self._message_callback = message_callback
        self._metric_callback = metric_callback
        self._outputs: dict[str, Any] = {}
        self._metrics: dict[str, Any] = {}
        self._data_fingerprints: dict[str, dict] = {}

        os.makedirs(run_dir, exist_ok=True)

    def load_input(self, name: str) -> Any:
        """Load an input by name. Auto-fingerprints dataset inputs."""
        if name not in self._inputs:
            raise ValueError(f"Input '{name}' not connected")
        value = self._inputs[name]
        if value is not None:
            try:
                self._data_fingerprints[name] = fingerprint_dataset(value)
            except Exception:
                # Fingerprinting is best-effort — never crash block execution
                pass
        return value

    def report_progress(self, current: int, total: int):
        """Report execution progress (updates progress bar and ETA)."""
        if self._progress_callback:
            self._progress_callback(current, total)

    def log_message(self, msg: str):
        """Log a message that appears in the block's live log panel."""
        if self._message_callback:
            self._message_callback(msg)
        print(msg)

    def log_metric(self, name: str, value: float, step: Optional[int] = None):
        """Log a metric (forwarded to MLflow)."""
        self._metrics[name] = value
        if self._metric_callback:
            self._metric_callback(name, value, step)

    def save_output(self, name: str, data_or_path: Any):
        """Save a block output for downstream blocks."""
        self._outputs[name] = data_or_path

    def save_checkpoint(self, epoch: int, path: str, metrics: dict = None):
        """Save a training checkpoint with associated metrics.

        The manifest is written to the run-level directory (parent of run_dir)
        so that the /runs/{run_id}/checkpoints API can find it regardless of
        which node produced the checkpoint.
        """
        # run_dir is artifacts/{run_id}/{node_id} — write manifest one level up
        run_level_dir = os.path.dirname(self.run_dir)
        checkpoint_dir = os.path.join(run_level_dir, "checkpoints")
        os.makedirs(checkpoint_dir, exist_ok=True)

        checkpoint_meta = {
            "epoch": epoch,
            "path": path,
            "metrics": metrics or {},
            "timestamp": time.time(),
        }

        # Append to checkpoint manifest
        manifest_path = os.path.join(checkpoint_dir, "manifest.json")
        manifest = []
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
                if not isinstance(manifest, list):
                    manifest = []
            except (json.JSONDecodeError, OSError):
                manifest = []
        # Replace existing entry for the same epoch (idempotent)
        manifest = [c for c in manifest if c.get("epoch") != epoch]
        manifest.append(checkpoint_meta)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        if self._metric_callback:
            self._metric_callback(f"checkpoint_epoch_{epoch}", metrics.get("loss", 0) if metrics else 0, epoch)

        self.log_message(f"Checkpoint saved: epoch {epoch}")

    def save_artifact(self, name: str, file_path: str):
        """Save a file as a run artifact."""
        # Copy to run_dir artifacts
        import shutil
        dest = os.path.join(self.run_dir, "artifacts", name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.isfile(file_path):
            shutil.copy2(file_path, dest)

    def get_outputs(self) -> dict[str, Any]:
        return self._outputs

    def get_metrics(self) -> dict[str, Any]:
        return self._metrics

    def get_data_fingerprints(self) -> dict[str, dict]:
        return self._data_fingerprints
