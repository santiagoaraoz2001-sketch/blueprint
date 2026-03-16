"""DPO Alignment — Direct Preference Optimization training with preference pairs."""

import json
import os
import sys

# Import shared training utilities
_TRAINING_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TRAINING_PKG_DIR not in sys.path:
    sys.path.insert(0, _TRAINING_PKG_DIR)
try:
    from _training_utils import detect_training_framework
except ImportError:
    detect_training_framework = None

try:
    from backend.block_sdk.exceptions import (
        BlockConfigError, BlockInputError, BlockDataError,
        BlockDependencyError, BlockExecutionError,
    )
except ImportError:
    class BlockConfigError(ValueError):
        def __init__(self, field, message, **kw): super().__init__(message)
    class BlockInputError(ValueError):
        def __init__(self, message, **kw): super().__init__(message)
    class BlockDataError(ValueError):
        pass
    class BlockDependencyError(ImportError):
        def __init__(self, dep, message="", **kw): super().__init__(message or dep)
    class BlockExecutionError(RuntimeError):
        def __init__(self, message, **kw): super().__init__(message)


def run(ctx):
    # Config
    model_name = ctx.config.get("model_name", "")
    lr = float(ctx.config.get("lr", 5e-7))
    epochs = int(ctx.config.get("epochs", 1))
    batch_size = int(ctx.config.get("batch_size", 4))
    beta = float(ctx.config.get("beta", 0.1))
    max_length = int(ctx.config.get("max_length", 512))
    max_prompt_length = int(ctx.config.get("max_prompt_length", 256))
    prompt_column = ctx.config.get("prompt_column", "prompt")
    chosen_column = ctx.config.get("chosen_column", "chosen")
    rejected_column = ctx.config.get("rejected_column", "rejected")
    eval_split = float(ctx.config.get("eval_split", 0.0))

    # Try to get model from input
    try:
        model_info = ctx.load_input("model")
        if isinstance(model_info, dict):
            model_name = model_name or model_info.get("model_name", model_info.get("model_id", ""))
        elif isinstance(model_info, str):
            model_name = model_name or model_info
    except (ValueError, Exception):
        pass

    if not model_name:
        raise BlockConfigError("model_name", "Model name is required")

    # Load dataset
    dataset_path = ctx.resolve_as_file_path("dataset")

    # ── Framework detection ──────────────────────────────────────────────
    prefer = ctx.config.get("prefer_framework", "auto")
    framework = detect_training_framework(model_name, prefer) if detect_training_framework else "pytorch"

    if framework == "mlx":
        try:
            import mlx_lm_lora  # noqa: F401
            ctx.log_message("Using mlx_lm_lora for DPO training on MLX")
            # mlx_lm_lora DPO: python -m mlx_lm_lora.train --train-mode dpo ...
            import subprocess
            output_dir = os.path.join(ctx.run_dir, "model")
            os.makedirs(output_dir, exist_ok=True)
            # Load data for mlx_lm_lora format
            data_file = os.path.join(dataset_path, "data.json") if os.path.isdir(dataset_path) else dataset_path
            cmd = [
                "python", "-m", "mlx_lm_lora.train",
                "--train-mode", "dpo",
                "--model", model_name,
                "--data", data_file,
                "--adapter-path", output_dir,
                "--iters", str(100 * epochs),
                "--learning-rate", str(lr),
                "--batch-size", str(batch_size),
            ]
            ctx.log_message(f"MLX DPO: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
            if result.returncode == 0:
                ctx.log_message("DPO training complete (MLX via mlx_lm_lora)")
                ctx.save_output("model", output_dir)
                ctx.save_output("metrics", {"framework": "mlx", "epochs": epochs})
                ctx.report_progress(1, 1)
                return
            ctx.log_message(f"mlx_lm_lora DPO failed: {result.stderr.strip() or result.stdout.strip()}. Falling back to PyTorch.")
        except ImportError:
            ctx.log_message(
                "⚠️ DPO on MLX requires mlx_lm_lora package. "
                "Install: pip install mlx-lm-lora\n"
                "Falling back to PyTorch."
            )
        framework = "pytorch"

    # Import required libraries — raise on failure
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainerCallback
        from datasets import Dataset
        from trl import DPOTrainer, DPOConfig
    except ImportError as e:
        from backend.block_sdk.exceptions import BlockDependencyError
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install datasets torch transformers trl",
        )

    ctx.log_message(f"DPO Alignment: {model_name}")
    ctx.log_message(f"Beta={beta}, LR={lr}, epochs={epochs}, batch_size={batch_size}")

    # Load tokenizer and model
    ctx.log_message("Loading tokenizer and model...")
    ctx.report_progress(0, 3)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto" if torch.cuda.is_available() else None,
    )

    # Load dataset
    ctx.log_message("Loading preference dataset...")
    ctx.report_progress(1, 3)
    data_file = os.path.join(dataset_path, "data.json") if os.path.isdir(dataset_path) else dataset_path
    if os.path.isfile(data_file):
        with open(data_file, "r") as f:
            raw_data = json.load(f)
    else:
        raise BlockInputError(f"Dataset not found: {data_file}", details="Check that the upstream block produced output", recoverable=False)

    if not isinstance(raw_data, list) or len(raw_data) == 0:
        raise BlockDataError("Dataset must be a non-empty JSON list", details="Received empty or invalid dataset from upstream block")

    # Validate DPO data format (expects chosen/rejected pairs)
    sample = raw_data[0]
    if not isinstance(sample, dict):
        raise BlockDataError("DPO dataset entries must be dicts with 'chosen' and 'rejected' keys", details="Each entry must be a dict containing preference pairs")

    if chosen_column not in sample or rejected_column not in sample:
        raise BlockDataError(
            f"DPO dataset must have '{chosen_column}' and '{rejected_column}' columns. "
            f"Set chosen_column/rejected_column config if your columns have different names.",
            details=f"Missing required columns: '{chosen_column}' and/or '{rejected_column}'"
        )

    # Build dataset dict — map user column names to DPO-expected keys
    ds_dict = {
        "chosen": [row[chosen_column] for row in raw_data],
        "rejected": [row[rejected_column] for row in raw_data],
    }
    if prompt_column in sample:
        ds_dict["prompt"] = [row[prompt_column] for row in raw_data]

    dataset = Dataset.from_dict(ds_dict)

    if eval_split > 0:
        split = dataset.train_test_split(test_size=eval_split, seed=42)
        train_dataset = split["train"]
        eval_dataset = split["test"]
        ctx.log_message(f"Preference pairs: {len(train_dataset)} train / {len(eval_dataset)} eval")
    else:
        train_dataset = dataset
        eval_dataset = None
        ctx.log_message(f"Preference pairs: {len(dataset)}")

    # Training
    ctx.log_message("Starting DPO training...")
    ctx.report_progress(2, 3)
    output_dir = os.path.join(ctx.run_dir, "model")
    os.makedirs(output_dir, exist_ok=True)

    dpo_config = DPOConfig(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        learning_rate=lr,
        beta=beta,
        max_length=max_length,
        max_prompt_length=max_prompt_length,
        logging_steps=max(1, len(train_dataset) // (batch_size * 10)),
        save_strategy="epoch",
        eval_strategy="epoch" if eval_dataset else "no",
        report_to="none",
        fp16=torch.cuda.is_available(),
        remove_unused_columns=False,
    )

    class CtxCallback(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kwargs):
            if logs:
                if "loss" in logs:
                    ctx.log_metric("train/loss", round(logs["loss"], 4), state.global_step)
                    ctx.log_message(f"  Step {state.global_step} — loss: {logs['loss']:.4f}")
                if "eval_loss" in logs:
                    ctx.log_metric("eval/loss", round(logs["eval_loss"], 4), state.global_step)
                    ctx.log_message(f"  Eval loss: {logs['eval_loss']:.4f}")
                reward_margin_keys = [
                    ("rewards/chosen", "rewards/rejected"),
                    ("rewards_chosen", "rewards_rejected"),
                ]
                for chosen_key, rejected_key in reward_margin_keys:
                    if chosen_key in logs and rejected_key in logs:
                        margin = logs[chosen_key] - logs[rejected_key]
                        ctx.log_metric("reward_margin", round(margin, 4), state.global_step)
                        ctx.log_message(
                            f"  Step {state.global_step} — reward_chosen: {logs[chosen_key]:.3f}, "
                            f"reward_rejected: {logs[rejected_key]:.3f}"
                        )
                        break
            if state.max_steps > 0:
                ctx.report_progress(state.global_step, state.max_steps)

    trainer = DPOTrainer(
        model=model,
        args=dpo_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
        callbacks=[CtxCallback()],
    )

    result = trainer.train()

    # Save
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    final_loss = round(result.training_loss, 4)

    # Save training metadata
    with open(os.path.join(output_dir, "training_config.json"), "w") as f:
        json.dump({
            "base_model": model_name,
            "method": "dpo_alignment",
            "beta": beta,
            "learning_rate": lr,
            "epochs": epochs,
            "batch_size": batch_size,
            "max_length": max_length,
            "max_prompt_length": max_prompt_length,
            "final_loss": final_loss,
            "preference_pairs": len(dataset),
        }, f, indent=2)

    final_metrics = {
        "final_loss": final_loss,
        "total_steps": result.global_step,
        "epochs_completed": epochs,
        "preference_pairs": len(dataset),
    }

    ctx.save_output("model", output_dir)
    ctx.save_output("metrics", final_metrics)
    ctx.log_metric("final_loss", final_loss)
    ctx.log_message(f"DPO training complete. Final loss: {final_loss}")
    ctx.report_progress(1, 1)
