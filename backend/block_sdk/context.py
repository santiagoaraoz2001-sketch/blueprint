"""
BlockContext — The SDK interface for block authors.

Every block's run.py receives a BlockContext instance:

    def run(ctx: BlockContext):
        data = ctx.load_input("dataset")
        ctx.report_progress(50, 100)
        ctx.log_metric("accuracy", 0.95)
        ctx.save_output("result", output_path)

Composite blocks receive a CompositeBlockContext, which adds methods
for defining sub-pipelines:

    def run(ctx: CompositeBlockContext):
        ctx.add_sub_block("step1", "llm_inference", {"prompt": "..."})
        ctx.add_sub_block("step2", "llm_inference", {"prompt": "..."})
        ctx.add_sub_edge("step1", "step2", "response", "context")
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


class CompositeBlockContext(BlockContext):
    """Extended context for composite blocks with sub-pipeline support.

    Block authors call add_sub_block() and add_sub_edge() in their run()
    function to define a sub-pipeline.  After run() returns, the executor
    detects the sub-pipeline via has_sub_pipeline() and executes it
    automatically using the same engine logic (topological sort, validation,
    metrics).

    Example::

        def run(ctx):
            ctx.add_sub_block("retriever", "retrieval_agent", {
                "query": ctx.config["query"],
            })
            ctx.add_sub_block("generator", "llm_inference", {
                "system_prompt": "Answer using the retrieved context.",
            })
            ctx.add_sub_edge("retriever", "generator", "documents", "context")
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sub_blocks: list[dict] = []
        self._sub_edges: list[dict] = []
        self._sub_block_ids: set[str] = set()

    def add_sub_block(self, block_id: str, block_type: str, config: dict):
        """Register a child block in the sub-pipeline.

        Args:
            block_id: Unique identifier within this sub-pipeline.
            block_type: The block type to execute (e.g. "llm_inference").
            config: Configuration dict passed to the child block.

        Raises:
            ValueError: If block_id is already registered.
        """
        if block_id in self._sub_block_ids:
            raise ValueError(
                f"Duplicate sub-block ID '{block_id}'. "
                "Each child block must have a unique ID within the composite."
            )
        self._sub_block_ids.add(block_id)
        self._sub_blocks.append({
            "id": block_id,
            "type": "custom",
            "data": {
                "type": block_type,
                "config": config,
                "category": "composite_child",
                "inputs": [],
                "outputs": [],
            }
        })

    def add_sub_edge(self, source_id: str, target_id: str,
                     source_handle: str = "output", target_handle: str = "input"):
        """Connect two child blocks.

        Args:
            source_id: The upstream child block ID.
            target_id: The downstream child block ID.
            source_handle: Output handle name on the source block.
            target_handle: Input handle name on the target block.

        Raises:
            ValueError: If source_id or target_id reference unknown blocks.
        """
        if source_id not in self._sub_block_ids:
            raise ValueError(
                f"Sub-edge source '{source_id}' not found. "
                f"Known sub-block IDs: {sorted(self._sub_block_ids)}"
            )
        if target_id not in self._sub_block_ids:
            raise ValueError(
                f"Sub-edge target '{target_id}' not found. "
                f"Known sub-block IDs: {sorted(self._sub_block_ids)}"
            )
        self._sub_edges.append({
            "source": source_id,
            "target": target_id,
            "sourceHandle": source_handle,
            "targetHandle": target_handle,
        })

    def get_sub_pipeline(self) -> dict:
        """Return the sub-pipeline definition (nodes + edges)."""
        return {"nodes": list(self._sub_blocks), "edges": list(self._sub_edges)}

    def has_sub_pipeline(self) -> bool:
        """Return True if any sub-blocks have been registered."""
        return len(self._sub_blocks) > 0

    @property
    def sub_block_count(self) -> int:
        """Number of registered sub-blocks."""
        return len(self._sub_blocks)
