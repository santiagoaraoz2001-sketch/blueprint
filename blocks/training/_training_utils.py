"""Shared training utilities — multi-framework training dispatcher.

Provides:
- detect_training_framework(): Detect best available training framework
- prepare_dataset(): Convert Blueprint dataset format to framework-specific format
- call_training(): Unified entry point for all training operations
- TrainingConfig: Standardized training configuration
- prepare_mlx_data(): Convenience wrapper for MLX data preparation
"""

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional, Callable


# ── Training Configuration ─────────────────────────────────────────────

@dataclass
class TrainingConfig:
    """Framework-agnostic training configuration."""
    model_name: str = ""
    output_dir: str = ""

    # Training parameters
    epochs: int = 3
    batch_size: int = 4
    learning_rate: float = 1e-4
    max_seq_length: int = 512
    warmup_steps: int = 0
    weight_decay: float = 0.01
    gradient_accumulation_steps: int = 1

    # LoRA parameters
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: list = field(default_factory=lambda: ["q_proj", "v_proj"])
    lora_layers: int = 16  # Number of transformer layers to apply LoRA to (MLX)

    # Training type
    training_type: str = "lora"  # lora, qlora, full, dora

    # Dataset
    data_path: str = ""
    text_column: str = "text"
    training_format: str = ""  # Prompt template
    eval_split: float = 0.0

    # Output
    save_merged: bool = False
    checkpoint_interval: int = 0

    # Framework-specific
    framework: str = "auto"  # auto, pytorch, mlx

    # Callbacks
    log_fn: Optional[Callable] = None
    progress_fn: Optional[Callable] = None
    metric_fn: Optional[Callable] = None


# ── Framework Detection ────────────────────────────────────────────────

def detect_training_framework(model_name: str = "", prefer: str = "auto") -> str:
    """Detect the best training framework for the current environment.

    Priority (when prefer="auto"):
    1. MLX on Apple Silicon (faster for local training, unified memory)
    2. PyTorch with CUDA (GPU training)
    3. PyTorch CPU (fallback)
    4. None (simulation mode)

    Args:
        model_name: Optional model name (MLX models prefer MLX framework)
        prefer: One of "auto", "mlx", "pytorch". Forces a specific framework
            when set to something other than "auto".

    Returns:
        "mlx", "pytorch", or "none"
    """
    # Explicit framework preference
    if prefer == "pytorch":
        try:
            import torch  # noqa: F401
            return "pytorch"
        except ImportError:
            return "none"
    if prefer == "mlx":
        try:
            import mlx  # noqa: F401
            from mlx_lm import lora  # noqa: F401
            return "mlx"
        except ImportError:
            return "none"

    # Auto-detection below

    # Check if model name suggests MLX
    if model_name and ("mlx-community" in model_name or "mlx" in model_name.lower()):
        try:
            import mlx  # noqa: F401
            return "mlx"
        except ImportError:
            pass

    # Check MLX availability (Apple Silicon)
    try:
        import mlx  # noqa: F401
        import mlx.core as mx  # noqa: F401
        # Verify MLX-LM is available for training
        try:
            from mlx_lm import lora  # noqa: F401
            return "mlx"
        except ImportError:
            # MLX available but mlx_lm not installed
            pass
    except ImportError:
        pass

    # Check PyTorch
    try:
        import torch  # noqa: F401
        from transformers import AutoModelForCausalLM  # noqa: F401
        return "pytorch"
    except ImportError:
        pass

    return "none"


# ── Dataset Preparation ────────────────────────────────────────────────

def prepare_dataset(
    data_path: str,
    output_dir: str,
    framework: str,
    text_column: str = "text",
    training_format: str = "",
    eval_split: float = 0.0,
) -> dict:
    """Convert Blueprint dataset to framework-specific training format.

    Blueprint stores datasets as directories containing data.json (JSON array
    of dicts).
    - PyTorch/Transformers: Expects HuggingFace Dataset or JSON/JSONL files
    - MLX: Expects train.jsonl, valid.jsonl in a directory

    Args:
        data_path: Path to Blueprint dataset (directory with data.json or
            direct file)
        output_dir: Where to write the converted dataset
        framework: "pytorch" or "mlx"
        text_column: Column name containing training text
        training_format: Optional prompt template
            (e.g., "### Instruction: {text}")
        eval_split: Fraction to use for evaluation (0.0 = no eval split)

    Returns:
        dict with keys:
            train_path: Path to training data (file or directory)
            eval_path: Optional path to eval data
            num_train: Number of training samples
            num_eval: Number of eval samples
    """
    # Load Blueprint dataset
    data_file = data_path
    if os.path.isdir(data_path):
        data_file = os.path.join(data_path, "data.json")

    with open(data_file, "r") as f:
        if data_file.endswith(".jsonl"):
            raw_data = [json.loads(line) for line in f if line.strip()]
        else:
            raw_data = json.load(f)

    if not isinstance(raw_data, list) or len(raw_data) == 0:
        raise ValueError("Dataset must be a non-empty JSON array")

    # Apply training format template if provided
    if training_format:
        formatted = []
        for row in raw_data:
            try:
                text = training_format.format(**row)
            except (KeyError, IndexError):
                text = row.get(text_column, str(row))
            formatted.append({"text": text})
        raw_data = formatted
    else:
        # Ensure each row has a 'text' field
        for i, row in enumerate(raw_data):
            if "text" not in row:
                # Try common alternatives
                for alt in [text_column, "content", "input", "prompt",
                            "question"]:
                    if alt in row:
                        raw_data[i] = {"text": row[alt]}
                        break
                else:
                    raw_data[i] = {"text": json.dumps(row)}

    # Split into train/eval
    if eval_split > 0 and len(raw_data) > 10:
        split_idx = max(1, int(len(raw_data) * (1 - eval_split)))
        train_data = raw_data[:split_idx]
        eval_data = raw_data[split_idx:]
    else:
        train_data = raw_data
        eval_data = []

    # Write framework-specific format
    os.makedirs(output_dir, exist_ok=True)

    if framework == "mlx":
        # MLX expects train.jsonl and valid.jsonl
        train_path = os.path.join(output_dir, "train.jsonl")
        with open(train_path, "w") as f:
            for row in train_data:
                f.write(json.dumps(row) + "\n")

        eval_path = None
        if eval_data:
            eval_path = os.path.join(output_dir, "valid.jsonl")
            with open(eval_path, "w") as f:
                for row in eval_data:
                    f.write(json.dumps(row) + "\n")

        return {
            "train_path": output_dir,  # MLX reads the directory
            "eval_path": output_dir if eval_data else None,
            "num_train": len(train_data),
            "num_eval": len(eval_data),
        }

    elif framework == "pytorch":
        # PyTorch/Transformers: write as JSON for Dataset.from_json
        train_path = os.path.join(output_dir, "train.json")
        with open(train_path, "w") as f:
            json.dump(train_data, f)

        eval_path = None
        if eval_data:
            eval_path = os.path.join(output_dir, "eval.json")
            with open(eval_path, "w") as f:
                json.dump(eval_data, f)

        return {
            "train_path": train_path,
            "eval_path": eval_path,
            "num_train": len(train_data),
            "num_eval": len(eval_data),
        }

    else:
        # Unknown framework — return raw data path
        return {
            "train_path": data_file,
            "eval_path": None,
            "num_train": len(raw_data),
            "num_eval": 0,
        }


def prepare_mlx_data(
    blueprint_data_path: str,
    output_dir: str,
    text_column: str = "text",
    training_format: str = "",
    eval_split: float = 0.1,
) -> str:
    """Convenience wrapper: convert Blueprint dataset to MLX training directory.

    Returns path to the directory containing train.jsonl and valid.jsonl.
    """
    result = prepare_dataset(
        blueprint_data_path, output_dir, "mlx",
        text_column=text_column,
        training_format=training_format,
        eval_split=eval_split,
    )
    return result["train_path"]


# ── Training Dispatcher ────────────────────────────────────────────────

def call_training(config: TrainingConfig) -> dict:
    """Unified training entry point. Dispatches to MLX or PyTorch.

    Args:
        config: TrainingConfig with all parameters

    Returns:
        dict with keys:
            model_path: Path to trained model output
            metrics: Training metrics dict
            framework: Which framework was used
    """
    framework = config.framework
    if framework == "auto":
        framework = detect_training_framework(config.model_name)

    if framework == "none":
        return _run_simulation(config)
    elif framework == "mlx":
        return _run_mlx_training(config)
    elif framework == "pytorch":
        return _run_pytorch_training(config)
    else:
        raise ValueError(f"Unknown training framework: {framework}")


def _run_simulation(config: TrainingConfig) -> dict:
    """Generate a training plan when no framework is available."""
    if config.log_fn:
        config.log_fn(
            "No training framework available. Generating training plan."
        )

    # Estimate training parameters
    estimated_steps = config.epochs * (100 // config.batch_size)

    plan = {
        "status": "plan_only",
        "model": config.model_name,
        "framework": "none",
        "training_type": config.training_type,
        "estimated_steps": estimated_steps,
        "config": {
            "epochs": config.epochs,
            "batch_size": config.batch_size,
            "learning_rate": config.learning_rate,
            "lora_r": (
                config.lora_r
                if config.training_type in ("lora", "qlora")
                else None
            ),
        },
        "install_hint": (
            "pip install mlx-lm  # For Apple Silicon\n"
            "pip install torch transformers peft  # For PyTorch"
        ),
    }

    # Save plan
    plan_path = os.path.join(config.output_dir, "training_plan.json")
    os.makedirs(config.output_dir, exist_ok=True)
    with open(plan_path, "w") as f:
        json.dump(plan, f, indent=2)

    return {
        "model_path": config.output_dir,
        "metrics": {"status": "plan_only", "framework": "none"},
        "framework": "none",
    }


# ── Iteration Estimation ──────────────────────────────────────────────

def _estimate_iters(config: TrainingConfig) -> int:
    """Estimate total training iterations from epochs and dataset size.

    MLX-LM uses iterations, not epochs. We need to estimate:
    iters = epochs * (num_samples / batch_size)

    Since we may not know num_samples at this point, use a reasonable default.
    """
    # Default: 1000 iterations if we can't estimate
    default_samples = 1000
    return max(100, config.epochs * (default_samples // config.batch_size))


# ── MLX Training Backend ──────────────────────────────────────────────

def _run_mlx_training(config: TrainingConfig) -> dict:
    """Run LoRA/QLoRA/full training via MLX-LM.

    Uses mlx_lm.lora module for training. Supports:
    - LoRA: Standard low-rank adaptation
    - QLoRA: LoRA on quantized models (4-bit)
    - DoRA: Decomposed weight LoRA
    - Full: Full parameter fine-tuning

    MLX-LM is invoked as a subprocess to avoid import conflicts
    and to capture its stdout/stderr for real-time progress logging.
    """
    try:
        import mlx  # noqa: F401
    except ImportError:
        raise RuntimeError("MLX not installed. Run: pip install mlx mlx-lm")

    if config.log_fn:
        config.log_fn(
            f"MLX Training: {config.training_type} on {config.model_name}"
        )

    # Prepare dataset in MLX format (train.jsonl, valid.jsonl)
    data_dir = os.path.join(config.output_dir, "mlx_data")
    prepare_dataset(
        config.data_path or config.model_name,
        data_dir,
        "mlx",
        text_column=config.text_column,
        training_format=config.training_format,
        eval_split=config.eval_split,
    )

    adapter_path = os.path.join(config.output_dir, "adapters")
    os.makedirs(adapter_path, exist_ok=True)

    total_iters = _estimate_iters(config)

    # Build mlx_lm.lora CLI command
    cmd = [
        "python", "-m", "mlx_lm.lora",
        "--model", config.model_name,
        "--train",
        "--data", data_dir,
        "--adapter-path", adapter_path,
        "--batch-size", str(config.batch_size),
        "--learning-rate", str(config.learning_rate),
        "--iters", str(total_iters),
    ]

    # LoRA-specific arguments
    if config.training_type in ("lora", "qlora", "dora"):
        cmd.extend([
            "--lora-layers", str(config.lora_layers),
        ])

        if config.training_type == "dora":
            cmd.extend(["--fine-tune-type", "dora"])
    elif config.training_type == "full":
        cmd.extend(["--fine-tune-type", "full"])
    # Default is "lora" — qlora is automatic when model is quantized

    # Max sequence length
    if config.max_seq_length:
        cmd.extend(["--max-seq-length", str(config.max_seq_length)])

    # Checkpoint saving
    save_every = config.checkpoint_interval or max(
        100, total_iters // 10
    )
    cmd.extend(["--save-every", str(save_every)])

    if config.log_fn:
        config.log_fn(f"Command: {' '.join(cmd)}")

    # Run training as subprocess for real-time output capture
    start_time = time.time()
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # Line buffered
    )

    # Parse MLX-LM training output for progress and metrics
    metrics = {}
    last_loss = 0.0
    last_iter = 0

    for line in iter(process.stdout.readline, ''):
        line = line.strip()
        if not line:
            continue

        if config.log_fn:
            config.log_fn(line)

        # Parse MLX-LM output format:
        # "Iter 10: Train loss 5.889, Learning Rate 1.000e-05, ..."
        # "Iter 1: Val loss 5.617, Val took 10.292s"
        iter_match = re.search(r'Iter\s+(\d+):', line)
        if iter_match:
            last_iter = int(iter_match.group(1))
            if config.progress_fn:
                config.progress_fn(last_iter, total_iters)

        loss_match = re.search(r'Train loss\s+([\d.]+)', line)
        if loss_match:
            last_loss = float(loss_match.group(1))
            metrics["train/loss"] = last_loss
            if config.metric_fn:
                config.metric_fn("train/loss", last_loss, last_iter)

        val_loss_match = re.search(r'Val loss\s+([\d.]+)', line)
        if val_loss_match:
            val_loss = float(val_loss_match.group(1))
            metrics["eval/loss"] = val_loss
            if config.metric_fn:
                config.metric_fn("eval/loss", val_loss, last_iter)

        lr_match = re.search(r'Learning Rate\s+([\d.e+-]+)', line)
        if lr_match:
            lr = float(lr_match.group(1))
            if config.metric_fn:
                config.metric_fn("learning_rate", lr, last_iter)

        tps_match = re.search(r'Tokens/sec\s+([\d.]+)', line)
        if tps_match:
            tps = float(tps_match.group(1))
            metrics["tokens_per_second"] = tps
            if config.metric_fn:
                config.metric_fn("tokens_per_second", tps, last_iter)

        peak_mem_match = re.search(r'Peak mem\s+([\d.]+)\s*GB', line)
        if peak_mem_match:
            peak_mem = float(peak_mem_match.group(1))
            metrics["peak_memory_gb"] = peak_mem

    process.wait(timeout=7200)
    elapsed = time.time() - start_time

    if process.returncode != 0:
        raise RuntimeError(
            f"MLX training failed with exit code {process.returncode}"
        )

    # Fuse adapters if requested
    fused_path = config.output_dir
    if config.save_merged and config.training_type in (
        "lora", "qlora", "dora"
    ):
        if config.log_fn:
            config.log_fn("Fusing LoRA adapters into base model...")

        fused_path = os.path.join(config.output_dir, "fused_model")
        fuse_cmd = [
            "python", "-m", "mlx_lm.fuse",
            "--model", config.model_name,
            "--adapter-path", adapter_path,
            "--save-path", fused_path,
        ]
        fuse_result = subprocess.run(
            fuse_cmd, capture_output=True, text=True, timeout=600
        )
        if fuse_result.returncode != 0:
            if config.log_fn:
                config.log_fn(f"Fuse failed: {fuse_result.stderr}")
            fused_path = adapter_path  # Fallback to adapters
        else:
            if config.log_fn:
                config.log_fn(f"Fused model saved to {fused_path}")

    metrics.update({
        "framework": "mlx",
        "training_type": config.training_type,
        "total_iters": last_iter,
        "final_loss": last_loss,
        "elapsed_seconds": round(elapsed, 1),
    })

    return {
        "model_path": fused_path if config.save_merged else adapter_path,
        "adapter_path": adapter_path,
        "metrics": metrics,
        "framework": "mlx",
    }


# ── PyTorch Training Backend ─────────────────────────────────────────

def _run_pytorch_training(config: TrainingConfig) -> dict:
    """Run training with PyTorch/Transformers/PEFT.

    This is the EXISTING PyTorch training logic, extracted into a common
    interface. Individual training blocks will be migrated to use this in
    FW-7/FW-8.

    For now, this raises NotImplementedError to signal blocks should use
    their existing implementation until migration is complete.
    """
    try:
        import torch  # noqa: F401
        from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: F401, E501
    except ImportError:
        raise RuntimeError(
            "PyTorch/Transformers not installed. "
            "Run: pip install torch transformers"
        )

    if config.training_type in ("lora", "qlora"):
        try:
            from peft import LoraConfig, get_peft_model  # noqa: F401
        except ImportError:
            raise RuntimeError(
                "PEFT not installed for LoRA training. Run: pip install peft"
            )

    # Signal that migration is not yet complete for this block
    raise NotImplementedError(
        "PyTorch training dispatch not yet migrated for this training type. "
        "The block will use its existing PyTorch implementation as fallback."
    )


# ── Lightweight helpers for FW-8 training blocks ─────────────────────


def prepare_texts(raw_data, text_column="", training_format=""):
    """Extract a flat list of training texts from raw dataset rows.

    Handles dicts with *text_column* / *training_format*, or plain strings.
    Used by FW-8 blocks that load data before calling MLX training.
    """
    if not raw_data:
        return []
    if isinstance(raw_data[0], dict):
        if training_format:
            return [training_format.format(**row) for row in raw_data]
        key = (
            text_column
            if text_column and text_column in raw_data[0]
            else ("text" if "text" in raw_data[0] else list(raw_data[0].keys())[0])
        )
        return [str(row.get(key, "")) for row in raw_data]
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


def call_mlx_subprocess(
    model_name, data_dir, output_dir, *,
    epochs=3, learning_rate=1e-4, batch_size=4, max_seq_length=512,
    fine_tune_type="lora", lora_layers=None, lora_rank=16,
    extra_args=None, ctx=None,
):
    """Run MLX training via the ``mlx_lm.lora`` CLI.

    Returns a dict with ``success`` (bool), ``output_dir``, and optionally
    ``error`` or ``adapter_config``.
    """
    train_jsonl = os.path.join(data_dir, "train.jsonl")
    if os.path.isfile(train_jsonl):
        with open(train_jsonl) as f:
            n_samples = sum(1 for _ in f)
        steps_per_epoch = max(1, n_samples // batch_size)
        iters = steps_per_epoch * epochs
    else:
        iters = 100 * epochs

    os.makedirs(output_dir, exist_ok=True)

    cmd = [
        "python", "-m", "mlx_lm.lora",
        "--model", model_name,
        "--data", data_dir,
        "--adapter-path", output_dir,
        "--iters", str(iters),
        "--learning-rate", str(learning_rate),
        "--batch-size", str(batch_size),
        "--max-seq-length", str(max_seq_length),
    ]

    if fine_tune_type == "full":
        cmd.extend(["--fine-tune-type", "full"])
    if lora_layers is not None:
        cmd.extend(["--lora-layers", str(lora_layers)])
    if lora_rank and fine_tune_type != "full":
        cmd.extend(["--lora-rank", str(lora_rank)])
    if extra_args:
        cmd.extend(extra_args)

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
        out = {"success": True, "output_dir": output_dir, "framework": "mlx"}
        adapter_cfg = os.path.join(output_dir, "adapter_config.json")
        if os.path.isfile(adapter_cfg):
            with open(adapter_cfg) as f:
                out["adapter_config"] = json.load(f)
        return out
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
