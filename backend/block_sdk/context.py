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
