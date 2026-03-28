"""Auto-register models produced by training and merge blocks after a pipeline run completes."""

import glob as glob_mod
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..models.model_record import ModelRecord

logger = logging.getLogger("blueprint.model_registry")

# ── Block types that produce models ──────────────────────────────────
TRAINING_BLOCK_TYPES = {
    "lora_finetuning",
    "qlora_finetuning",
    "full_finetuning",
    "dpo_alignment",
    "rlhf_ppo",
    "reward_model_trainer",
    "distillation",
    "continued_pretraining",
    "curriculum_training",
    "ballast_training",
    "checkpoint_selector",
    "hyperparameter_sweep",
}

MERGE_BLOCK_TYPES = {
    "slerp_merge",
    "ties_merge",
    "dare_merge",
    "frankenmerge",
    "mergekit_merge",
}

MODEL_PRODUCING_TYPES = TRAINING_BLOCK_TYPES | MERGE_BLOCK_TYPES

# ── Format detection ─────────────────────────────────────────────────
# Known sharded model file glob patterns
_SHARD_PATTERNS = [
    "model-*-of-*.safetensors",
    "pytorch_model-*-of-*.bin",
    "model.safetensors.index.json",
    "pytorch_model.bin.index.json",
    "consolidated.*.pth",  # Meta/Llama format
]

# File extensions that indicate model format
_FORMAT_EXTENSIONS: dict[str, str] = {
    ".gguf": "gguf",
    ".safetensors": "safetensors",
    ".onnx": "onnx",
    ".bin": "pytorch",
    ".pt": "pytorch",
    ".pth": "pytorch",
}


def _detect_model_format(output: Any) -> str:
    """Detect model format from the output data, path, or directory contents.

    Handles:
    - Single model files (.gguf, .safetensors, .onnx, .bin, .pt)
    - Sharded model directories (model-00001-of-00012.safetensors, etc.)
    - HuggingFace Hub cache directories with index files
    - Explicit format field in output dict
    """
    # Check explicit format in output metadata
    if isinstance(output, dict):
        explicit = output.get("format") or output.get("model_format")
        if explicit and isinstance(explicit, str):
            normalized = explicit.lower().strip()
            if normalized in ("gguf", "safetensors", "onnx", "pytorch"):
                return normalized
        path = output.get("model_path", "") or output.get("path", "") or ""
    elif isinstance(output, str):
        path = output
    else:
        return "pytorch"

    path_str = str(path)
    p = Path(path_str)

    # Single file — check extension
    if p.is_file():
        for ext, fmt in _FORMAT_EXTENSIONS.items():
            if path_str.lower().endswith(ext):
                return fmt
        return "pytorch"

    # Directory — inspect contents for sharded models or index files
    if p.is_dir():
        children = list(p.iterdir())
        child_names = {c.name.lower() for c in children if c.is_file()}

        # Safetensors index → sharded safetensors
        if "model.safetensors.index.json" in child_names:
            return "safetensors"
        # Any .safetensors files
        if any(name.endswith(".safetensors") for name in child_names):
            return "safetensors"
        # GGUF files
        if any(name.endswith(".gguf") for name in child_names):
            return "gguf"
        # ONNX files
        if any(name.endswith(".onnx") for name in child_names):
            return "onnx"
        # PyTorch bin index → sharded pytorch
        if "pytorch_model.bin.index.json" in child_names:
            return "pytorch"
        # Any .bin or .pt files
        if any(name.endswith((".bin", ".pt", ".pth")) for name in child_names):
            return "pytorch"

    # Path string heuristic (for non-existent or remote paths)
    path_lower = path_str.lower()
    for ext, fmt in _FORMAT_EXTENSIONS.items():
        if ext in path_lower:
            return fmt

    return "pytorch"


def _get_model_size(output: Any) -> int | None:
    """Compute total model size in bytes.

    Handles:
    - Explicit size_bytes / file_size in output metadata
    - Single model files on disk
    - Sharded model directories (recursively sums all model-related files)
    - HuggingFace safetensors index files (reads shard sizes from metadata)
    - Graceful None return for remote/unavailable paths
    """
    # 1. Explicit size from output metadata
    if isinstance(output, dict):
        for key in ("size_bytes", "file_size", "total_size", "model_size"):
            val = output.get(key)
            if val is not None:
                try:
                    return int(val)
                except (ValueError, TypeError):
                    pass
        path = output.get("model_path") or output.get("path")
    elif isinstance(output, str):
        path = output
    else:
        return None

    if not path:
        return None

    try:
        p = Path(str(path))

        # 2. Single file
        if p.is_file():
            return p.stat().st_size

        # 3. Directory — try reading HF safetensors index for accurate size
        if p.is_dir():
            total = _get_size_from_index(p)
            if total is not None:
                return total
            # Fallback: recursively sum all model-related files
            return _get_directory_model_size(p)

    except Exception as exc:
        logger.debug("Could not determine model size for %s: %s", path, exc)

    return None


def _get_size_from_index(directory: Path) -> int | None:
    """Read the HuggingFace safetensors/pytorch index file to compute total size.

    Index files (model.safetensors.index.json) contain a weight_map that
    lists each shard file. We sum the sizes of all referenced shard files.
    """
    for index_name in ("model.safetensors.index.json", "pytorch_model.bin.index.json"):
        index_path = directory / index_name
        if not index_path.is_file():
            continue
        try:
            with open(index_path) as f:
                index = json.load(f)
            # The weight_map maps tensor names → shard filenames.
            # Deduplicate shard filenames and sum their sizes.
            weight_map = index.get("weight_map", {})
            shard_files = set(weight_map.values())
            total = 0
            for shard_name in shard_files:
                shard_path = directory / shard_name
                if shard_path.is_file():
                    total += shard_path.stat().st_size
            if total > 0:
                return total
        except Exception:
            continue
    return None


def _get_directory_model_size(directory: Path) -> int:
    """Sum the sizes of all model-related files in a directory (recursive).

    Only counts files with known model extensions to avoid inflating the
    size with tokenizer files, configs, etc.
    """
    model_extensions = {".safetensors", ".bin", ".pt", ".pth", ".gguf", ".onnx"}
    total = 0
    for f in directory.rglob("*"):
        if f.is_file() and f.suffix.lower() in model_extensions:
            try:
                total += f.stat().st_size
            except OSError:
                pass
    # If no model files found, fall back to total directory size
    if total == 0:
        for f in directory.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    return total if total > 0 else 0


def _extract_model_name(node: dict, output: Any) -> str:
    """Generate a human-readable model name from the output or node config."""
    config = node.get("data", {}).get("config", {})
    block_type = node.get("data", {}).get("type", "unknown")

    # Prefer output metadata (runtime-determined name)
    if isinstance(output, dict):
        name = output.get("model_name") or output.get("name")
        if name:
            return str(name)

    # Fall back to config
    name = config.get("output_model_name") or config.get("model_name") or config.get("name")
    if name:
        return str(name)

    # Fallback: use block type + node label
    label = node.get("data", {}).get("label", block_type)
    return f"{label}-output"


def auto_register_models(
    run_id: str,
    nodes: list[dict],
    outputs: dict[str, Any],
    all_metrics: dict[str, Any],
    db: Session,
) -> list[str]:
    """Scan completed nodes for training/merge blocks and register their output models.

    Returns a list of created ModelRecord IDs.
    """
    registered_ids = []

    for node in nodes:
        node_id = node.get("id", "")
        block_type = node.get("data", {}).get("type", "")

        if block_type not in MODEL_PRODUCING_TYPES:
            continue

        # Get the output from this node
        node_output = outputs.get(node_id)
        if node_output is None:
            continue

        model_name = _extract_model_name(node, node_output)
        model_format = _detect_model_format(node_output)
        model_size = _get_model_size(node_output)

        # Extract model path
        model_path = None
        if isinstance(node_output, dict):
            model_path = node_output.get("model_path") or node_output.get("path")
        elif isinstance(node_output, str):
            model_path = node_output

        # Extract training config from node data
        config = node.get("data", {}).get("config", {})

        # Extract source data info from upstream connections
        source_data = config.get("dataset") or config.get("data_path") or None

        # Collect node-specific metrics
        node_metrics = {}
        for key, value in all_metrics.items():
            if key.startswith(f"{node_id}.") or key.startswith(f"{node_id}/"):
                short_key = key.split(".", 1)[-1] if "." in key else key.split("/", 1)[-1]
                node_metrics[short_key] = value

        record = ModelRecord(
            id=str(uuid.uuid4()),
            name=model_name,
            version="1.0.0",
            format=model_format,
            size_bytes=model_size,
            source_run_id=run_id,
            source_node_id=node_id,
            metrics=node_metrics,
            tags=f"{block_type},{model_format}",
            training_config=config,
            source_data=str(source_data) if source_data else None,
            model_path=str(model_path) if model_path else None,
            created_at=datetime.now(timezone.utc),
        )
        db.add(record)
        registered_ids.append(record.id)
        logger.info(
            "Auto-registered model '%s' (format=%s, node=%s, run=%s)",
            model_name, model_format, node_id, run_id,
        )

    if registered_ids:
        db.commit()

    return registered_ids
