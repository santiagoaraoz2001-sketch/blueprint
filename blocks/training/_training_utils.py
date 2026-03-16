"""Shared training utilities — multi-framework training dispatcher.

Provides:
- detect_training_framework(): Detect best available training framework
- prepare_dataset(): Convert Blueprint dataset format to framework-specific format
- call_training(): Unified entry point for all training operations
- TrainingConfig: Standardized training configuration
"""

import json
import os
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

    # Training type
    training_type: str = "lora"  # lora, qlora, full, dora

    # Dataset
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

def detect_training_framework(model_name: str = "") -> str:
    """Detect the best training framework for the current environment.

    Priority:
    1. MLX on Apple Silicon (faster for local training, unified memory)
    2. PyTorch with CUDA (GPU training)
    3. PyTorch CPU (fallback)
    4. None (simulation mode)

    Args:
        model_name: Optional model name (MLX models prefer MLX framework)

    Returns:
        "mlx", "pytorch", or "none"
    """
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


def _run_pytorch_training(config: TrainingConfig) -> dict:
    """Run training with PyTorch/Transformers/PEFT.

    This is a DISPATCHER that the individual training blocks will call.
    The actual PyTorch training logic remains in each block's run.py
    (since each training type — LoRA, DPO, RLHF — has unique logic).

    For FW-5, this function establishes the interface. The full implementation
    is completed in FW-7 when training blocks are migrated.
    """
    raise NotImplementedError(
        "PyTorch training dispatch not yet migrated. "
        "Use the block's existing PyTorch implementation."
    )


def _run_mlx_training(config: TrainingConfig) -> dict:
    """Run training with MLX-LM.

    Placeholder — full implementation in FW-6.
    """
    raise NotImplementedError(
        "MLX training backend not yet implemented. "
        "Will be added in FW-6."
    )
