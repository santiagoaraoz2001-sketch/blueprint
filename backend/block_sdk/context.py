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

    # ── resolve_* helpers ─────────────────────────────────────────────
    # Normalize upstream outputs into the format the downstream block
    # expects, regardless of how the upstream block saved the data.

    # Well-known filenames tried (in order) when a directory is given.
    _DIR_DATA_CANDIDATES = (
        "data.json", "data.jsonl", "dataset.json",
        "output.json", "results.json",
    )
    # Extensions considered data files when scanning a directory.
    _DIR_SCAN_EXTENSIONS = (".json", ".jsonl", ".csv", ".txt")

    def _resolve_dir_to_file(self, dir_path: str, name: str) -> str:
        """Find the best data file inside *dir_path*.

        Tries well-known names first, then falls back to the first file
        whose extension looks like data.  Raises FileNotFoundError if
        the directory contains nothing usable.
        """
        for candidate in self._DIR_DATA_CANDIDATES:
            p = os.path.join(dir_path, candidate)
            if os.path.isfile(p):
                return p
        try:
            entries = sorted(os.listdir(dir_path))
        except OSError as exc:
            raise FileNotFoundError(
                f"Input '{name}' directory ({dir_path}) is not readable: {exc}"
            ) from exc
        for entry in entries:
            if entry.endswith(self._DIR_SCAN_EXTENSIONS):
                return os.path.join(dir_path, entry)
        raise FileNotFoundError(
            f"Input '{name}' is a directory ({dir_path}) but contains no data files"
        )

    @staticmethod
    def _safe_filename(name: str) -> str:
        """Sanitize a port name for use in a temp filename."""
        # Strip path components and restrict to safe characters
        base = os.path.basename(name)
        return "".join(c if (c.isalnum() or c in "_-") else "_" for c in base) or "input"

    def _load_file_as_data(self, path: str) -> list:
        """Load a single file into a list of records."""
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            if path.endswith(".jsonl"):
                rows = []
                for lineno, line in enumerate(f, 1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        rows.append(json.loads(stripped))
                    except json.JSONDecodeError:
                        # Skip malformed lines rather than crashing the
                        # entire pipeline — log if possible.
                        rows.append({"_raw": stripped, "_parse_error": f"line {lineno}"})
                return rows
            elif path.endswith(".json"):
                data = json.load(f)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return [data]
                return [{"value": data}]
            elif path.endswith(".csv"):
                import csv
                return list(csv.DictReader(f))
            else:
                # Plain text — one record per non-empty line
                lines = f.read().strip().splitlines()
                return [{"text": line} for line in lines if line.strip()]

    def resolve_as_file_path(self, name: str) -> str:
        """Resolve an input to a file path, regardless of upstream format.

        - File path string → return as-is
        - Directory path → return path to first data file inside it
        - Dict/list → serialize to a temp JSON file and return path
        - Raw string → write to a temp .txt file and return path
        """
        value = self.load_input(name)

        if value is None:
            raise ValueError(f"Input '{name}' is None")

        safe = self._safe_filename(name)

        if isinstance(value, str):
            if os.path.isfile(value):
                return value
            if os.path.isdir(value):
                return self._resolve_dir_to_file(value, name)
            # Raw string — write to temp file
            tmp_path = os.path.join(self.run_dir, f"_resolved_{safe}.txt")
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(value)
            return tmp_path

        if isinstance(value, (dict, list)):
            tmp_path = os.path.join(self.run_dir, f"_resolved_{safe}.json")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(value, f, indent=2, default=str)
            return tmp_path

        # Fallback: convert to string and write
        tmp_path = os.path.join(self.run_dir, f"_resolved_{safe}.txt")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(str(value))
        return tmp_path

    def resolve_as_data(self, name: str) -> list[dict] | list:
        """Resolve an input to in-memory data (list of dicts), regardless of format.

        - File path to JSON/JSONL/CSV → load and return
        - Directory → find best data file inside and load it
        - List → return as-is
        - Dict → return [dict]
        - Raw string → return [{"text": string}]
        """
        value = self.load_input(name)

        if value is None:
            return []

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            return [value]

        if isinstance(value, str):
            # Resolve directory to its best data file
            path = value
            if os.path.isdir(path):
                try:
                    path = self._resolve_dir_to_file(path, name)
                except FileNotFoundError:
                    return [{"text": value}]

            if os.path.isfile(path):
                return self._load_file_as_data(path)

            # Not a file path — treat as raw text
            return [{"text": value}]

        return [{"value": str(value)}]

    def resolve_as_text(self, name: str) -> str:
        """Resolve an input to a plain text string, regardless of format.

        - File path → read file contents
        - Directory → find best data file inside and read it
        - Dict/list → JSON serialize
        - Raw string → return as-is
        """
        value = self.load_input(name)

        if value is None:
            return ""

        if isinstance(value, str):
            if os.path.isfile(value):
                with open(value, "r", encoding="utf-8", errors="replace") as f:
                    return f.read()
            if os.path.isdir(value):
                try:
                    resolved = self._resolve_dir_to_file(value, name)
                    with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                        return f.read()
                except FileNotFoundError:
                    pass
            return value

        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2, default=str)

        return str(value)

    def resolve_as_dict(self, name: str) -> dict:
        """Resolve an input to a dict, regardless of format.

        - Dict → return as-is
        - File path to JSON → load and return
        - Directory → find best data file inside and load it
        - String → try JSON parse, else return {"value": string}
        - List → return {"items": list}
        """
        value = self.load_input(name)

        if value is None:
            return {}

        if isinstance(value, dict):
            return value

        if isinstance(value, str):
            # Resolve directory to its best data file
            path = value
            if os.path.isdir(path):
                try:
                    path = self._resolve_dir_to_file(path, name)
                except FileNotFoundError:
                    return {"value": value}
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {"data": data}
            # Not a file — try JSON parse
            try:
                data = json.loads(value)
                return data if isinstance(data, dict) else {"data": data}
            except (json.JSONDecodeError, ValueError):
                return {"value": value}

        if isinstance(value, list):
            return {"items": value}

        return {"value": str(value)}

    def resolve_model_info(self, name: str = "model") -> dict:
        """Resolve a model input to a standardized model info dict.

        Returns a dict with normalized keys: model_name, model_id, source,
        backend, and any extra keys from the upstream output.

        Handles dicts, model-name strings, HuggingFace IDs, local directory
        paths, and file paths to JSON model-info files.
        """
        value = self.load_input(name)

        if value is None:
            return {}

        # If it's a file path pointing to a JSON model-info file, load it
        if isinstance(value, str) and os.path.isfile(value) and value.endswith(".json"):
            try:
                with open(value, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    value = loaded
                # If the JSON isn't a dict, fall through to string handling
            except (json.JSONDecodeError, OSError):
                pass  # Fall through to string handling

        if isinstance(value, dict):
            result = dict(value)
            if "model_name" not in result:
                result["model_name"] = result.get("model_id", result.get("name", ""))
            if "model_id" not in result:
                result["model_id"] = result.get("model_name", "")
            if "source" not in result:
                result["source"] = result.get("backend", result.get("provider", "auto"))
            if "backend" not in result:
                result["backend"] = result.get("source", "auto")
            return result

        if isinstance(value, str):
            if os.path.isdir(value):
                return {
                    "model_name": os.path.basename(value.rstrip("/")),
                    "model_id": value,
                    "source": "local_path",
                    "backend": "local_path",
                    "path": value,
                }
            # Infer source from string format
            source = "ollama"  # default for plain model names
            if "/" in value and not value.startswith("/"):
                source = "huggingface"
            return {
                "model_name": value,
                "model_id": value,
                "source": source,
                "backend": source,
            }

        return {}


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
