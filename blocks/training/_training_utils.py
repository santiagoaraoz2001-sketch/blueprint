"""Shared training utilities for MLX / PyTorch framework dispatch.

Provides framework detection, dataset preparation, and MLX training dispatch
used across all training blocks.
"""

import json
import os
import platform
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def detect_training_framework(model_name: str, prefer: str = "auto") -> str:
    """Detect the best available training framework.

    Args:
        model_name: Model identifier (for logging context).
        prefer: One of ``"auto"``, ``"mlx"``, ``"pytorch"``.

    Returns:
        ``"mlx"``, ``"pytorch"``, or ``"none"``.
    """
    if prefer == "pytorch":
        try:
            import torch  # noqa: F401
            return "pytorch"
        except ImportError:
            return "none"

    if prefer == "mlx":
        try:
            import mlx  # noqa: F401
            import mlx_lm  # noqa: F401
            return "mlx"
        except ImportError:
            return "none"

    # auto: prefer MLX on Apple Silicon, fall back to PyTorch elsewhere
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        try:
            import mlx  # noqa: F401
            import mlx_lm  # noqa: F401
            return "mlx"
        except ImportError:
            pass

    try:
        import torch  # noqa: F401
        return "pytorch"
    except ImportError:
        pass

    return "none"


def prepare_dataset(raw_data, text_column="", training_format=""):
    """Extract a flat list of training texts from raw dataset rows.

    Handles dicts with *text_column* / *training_format*, or plain strings.
    """
    if not raw_data:
        return []

    if isinstance(raw_data[0], dict):
        if training_format:
            return [training_format.format(**row) for row in raw_data]
        text_key = (
            text_column
            if text_column and text_column in raw_data[0]
            else ("text" if "text" in raw_data[0] else list(raw_data[0].keys())[0])
        )
        return [str(row.get(text_key, "")) for row in raw_data]

    return [str(item) for item in raw_data]


def write_training_data(texts, output_dir, eval_split=0.0):
    """Write training texts to JSONL files expected by ``mlx_lm``.

    Creates ``train.jsonl`` and ``valid.jsonl`` in *output_dir*.
    Returns *output_dir*.
    """
    os.makedirs(output_dir, exist_ok=True)

    if eval_split > 0:
        split_idx = max(1, int(len(texts) * (1.0 - eval_split)))
        train_texts = texts[:split_idx]
        valid_texts = texts[split_idx:]
    else:
        train_texts = texts
        # mlx_lm requires valid.jsonl — use a small slice of training data
        valid_texts = texts[: max(1, len(texts) // 10)]

    with open(os.path.join(output_dir, "train.jsonl"), "w") as f:
        for t in train_texts:
            json.dump({"text": t}, f)
            f.write("\n")

    with open(os.path.join(output_dir, "valid.jsonl"), "w") as f:
        for t in valid_texts:
            json.dump({"text": t}, f)
            f.write("\n")

    return output_dir


@dataclass
class TrainingConfig:
    """Configuration for an MLX training run via ``mlx_lm.lora``."""

    model_name: str
    output_dir: str
    data_dir: str
    epochs: int = 3
    learning_rate: float = 1e-4
    batch_size: int = 4
    max_seq_length: int = 512
    fine_tune_type: str = "lora"  # "lora" or "full"
    lora_rank: int = 16
    lora_layers: Optional[int] = None
    iters: Optional[int] = None  # explicit iteration count override
    extra_args: List[str] = field(default_factory=list)


def call_training(config: TrainingConfig, ctx=None):
    """Run MLX training via the ``mlx_lm.lora`` CLI.

    Returns a dict with ``success`` (bool), ``output_dir``, and optionally
    ``error`` or ``adapter_config``.
    """
    # Calculate iterations from epochs + dataset size
    train_jsonl = os.path.join(config.data_dir, "train.jsonl")
    if config.iters is not None:
        iters = config.iters
    elif os.path.isfile(train_jsonl):
        with open(train_jsonl) as f:
            n_samples = sum(1 for _ in f)
        steps_per_epoch = max(1, n_samples // config.batch_size)
        iters = steps_per_epoch * config.epochs
    else:
        iters = 100 * config.epochs

    cmd = [
        "python", "-m", "mlx_lm.lora",
        "--model", config.model_name,
        "--data", config.data_dir,
        "--adapter-path", config.output_dir,
        "--iters", str(iters),
        "--learning-rate", str(config.learning_rate),
        "--batch-size", str(config.batch_size),
        "--max-seq-length", str(config.max_seq_length),
    ]

    if config.fine_tune_type == "full":
        cmd.extend(["--fine-tune-type", "full"])

    if config.lora_layers is not None:
        cmd.extend(["--lora-layers", str(config.lora_layers)])

    if config.lora_rank and config.fine_tune_type != "full":
        cmd.extend(["--lora-rank", str(config.lora_rank)])

    cmd.extend(config.extra_args)

    if ctx:
        ctx.log_message(f"MLX training: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown error"
            if ctx:
                ctx.log_message(f"MLX training failed: {error_msg}")
            return {"success": False, "error": error_msg}

        if ctx:
            ctx.log_message("MLX training completed successfully")

        results = {"success": True, "output_dir": config.output_dir, "framework": "mlx"}

        # Read adapter config if present
        adapter_path = os.path.join(config.output_dir, "adapter_config.json")
        if os.path.isfile(adapter_path):
            with open(adapter_path) as f:
                results["adapter_config"] = json.load(f)

        return results

    except subprocess.TimeoutExpired:
        if ctx:
            ctx.log_message("MLX training timed out after 2 hours")
        return {"success": False, "error": "Training timed out"}
    except FileNotFoundError:
        if ctx:
            ctx.log_message("mlx_lm CLI not found. Is mlx-lm installed?")
        return {"success": False, "error": "mlx_lm not found"}
    except Exception as e:
        if ctx:
            ctx.log_message(f"MLX training error: {e}")
        return {"success": False, "error": str(e)}
