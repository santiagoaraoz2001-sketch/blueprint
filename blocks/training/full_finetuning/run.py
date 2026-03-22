"""Full Fine-Tuning — full parameter fine-tuning without LoRA adapters."""

import json
import os

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

try:
    from blocks.training._validation import _validate_model_for_training
except ImportError:
    def _validate_model_for_training(model_name, model_info, ctx, field_name="model_name"):
        return model_name


def _has_gpu():
    """Check for GPU: CUDA or Apple MPS."""
    import torch
    return torch.cuda.is_available() or (hasattr(torch.backends, "mps") and torch.backends.mps.is_available())


def run(ctx):
    # Read upstream dataset metadata
    _dataset_meta = {}
    try:
        _meta_input = ctx.load_input("dataset_meta")
        if isinstance(_meta_input, dict):
            _dataset_meta = _meta_input
    except (ValueError, KeyError):
        pass

    # Config
    model_name = ctx.config.get("model_name", "")
    lr = float(ctx.config.get("lr", 2e-5))
    epochs = int(ctx.config.get("epochs", 3))
    batch_size = int(ctx.config.get("batch_size", 4))
    warmup_steps = int(ctx.config.get("warmup_steps", 100))
    weight_decay = float(ctx.config.get("weight_decay", 0.01))
    max_seq_length = int(ctx.config.get("max_seq_length", 512))
    gradient_checkpointing = ctx.config.get("gradient_checkpointing", True)
    text_column = ctx.config.get("text_column") or _dataset_meta.get("text_column", "")
    training_format = ctx.config.get("training_format", ctx.config.get("prompt_template", ""))
    eval_split = float(ctx.config.get("eval_split", 0.0))
    checkpoint_interval = int(ctx.config.get("checkpoint_interval", 0))

    if isinstance(gradient_checkpointing, str):
        gradient_checkpointing = gradient_checkpointing.lower() in ("true", "1", "yes")

    # Try to get model from input
    model_info = {}
    try:
        model_info = ctx.load_input("model")
        if isinstance(model_info, dict):
            model_name = model_name or model_info.get("model_name", model_info.get("model_id", ""))
        elif isinstance(model_info, str):
            model_name = model_name or model_info
    except (ValueError, Exception):
        pass

    if not model_name:
        raise BlockConfigError("model_name", "Model name is required — set it in config or connect a model to the input port")

    # ── Validate model for training ──
    model_name = _validate_model_for_training(model_name, model_info, ctx)

    dataset_path = ctx.resolve_as_file_path("dataset")

    # ── Framework detection (NEW) ──────────────────────────────────────
    from blocks.training._training_utils import (
        detect_training_framework, TrainingConfig, call_training,
    )

    preferred = ctx.config.get("prefer_framework", "auto")
    if preferred != "auto":
        framework = preferred
    else:
        framework = detect_training_framework(model_name)
    ctx.log_message(f"Detected training framework: {framework}")

    mlx_lora_layers = int(ctx.config.get("mlx_lora_layers", 16))

    # ── Framework dispatch ─────────────────────────────────────────────
    if framework == "mlx":
        # Memory warning for full fine-tuning
        model_lower = model_name.lower()
        if any(size in model_lower for size in ["7b", "8b", "13b", "70b", "34b", "40b"]):
            ctx.log_message(
                "WARNING: Full fine-tuning requires significantly more memory than LoRA. "
                "For large models, consider using LoRA/QLoRA instead."
            )
        _run_mlx_path(
            ctx, model_name, dataset_path, lr, epochs, batch_size,
            max_seq_length, warmup_steps, weight_decay, text_column,
            training_format, eval_split, checkpoint_interval, mlx_lora_layers,
        )
        return

    if framework == "pytorch":
        _run_pytorch_path(
            ctx, model_name, dataset_path, lr, epochs, batch_size,
            warmup_steps, weight_decay, max_seq_length, gradient_checkpointing,
            text_column, training_format, eval_split, checkpoint_interval,
        )
    else:
        # No framework available — simulation/plan-only mode
        _run_fallback(
            ctx, model_name, dataset_path, lr, epochs, batch_size,
            max_seq_length, warmup_steps, weight_decay,
        )


# ── MLX training path (NEW) ───────────────────────────────────────────

def _run_mlx_path(
    ctx, model_name, dataset_path, lr, epochs, batch_size,
    max_seq_length, warmup_steps, weight_decay, text_column,
    training_format, eval_split, checkpoint_interval, mlx_lora_layers,
):
    """MLX full fine-tuning path using _training_utils."""
    from blocks.training._training_utils import TrainingConfig, call_training

    output_dir = os.path.join(ctx.run_dir, "model")
    os.makedirs(output_dir, exist_ok=True)

    config = TrainingConfig(
        model_name=model_name,
        output_dir=output_dir,
        data_path=dataset_path,
        training_type="full",
        framework="mlx",
        epochs=epochs,
        batch_size=batch_size,
        learning_rate=lr,
        max_seq_length=max_seq_length,
        warmup_steps=warmup_steps,
        weight_decay=weight_decay,
        lora_layers=mlx_lora_layers,
        save_merged=False,  # Full fine-tuning saves the whole model directly
        text_column=text_column,
        training_format=training_format,
        eval_split=eval_split,
        checkpoint_interval=checkpoint_interval,
        log_fn=ctx.log_message,
        progress_fn=ctx.report_progress,
        metric_fn=lambda name, val, step: ctx.log_metric(name, val, step),
    )

    result = call_training(config)

    ctx.save_output("trained_model", result["model_path"])
    ctx.save_output("metrics", result["metrics"])
    final_loss = result["metrics"].get("final_loss", "N/A")
    ctx.log_message(f"Full fine-tuning complete (MLX). Final loss: {final_loss}")
    ctx.report_progress(1, 1)


# ── PyTorch training path (EXISTING — UNCHANGED) ──────────────────────

def _run_pytorch_path(
    ctx, model_name, dataset_path, lr, epochs, batch_size,
    warmup_steps, weight_decay, max_seq_length, gradient_checkpointing,
    text_column, training_format, eval_split, checkpoint_interval,
):
    """Full fine-tuning using PyTorch / HuggingFace Transformers."""
    try:
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            TrainingArguments,
            Trainer,
            TrainerCallback,
            DataCollatorForLanguageModeling,
        )
        from datasets import Dataset
    except ImportError as e:
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install datasets torch transformers",
        )

    ctx.log_message(f"Full fine-tuning: {model_name}")
    ctx.log_message(f"LR={lr}, epochs={epochs}, batch_size={batch_size}, max_seq={max_seq_length}")
    ctx.log_message(f"Warmup steps={warmup_steps}, weight_decay={weight_decay}, grad_ckpt={gradient_checkpointing}")

    ctx.log_message("Loading tokenizer and model...")
    ctx.report_progress(0, 3)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16 if _has_gpu() else torch.float32,
        device_map="auto" if _has_gpu() else None,
    )

    if gradient_checkpointing:
        model.gradient_checkpointing_enable()

    total_params = sum(p.numel() for p in model.parameters())
    ctx.log_message(f"Total parameters: {total_params:,} (all trainable)")

    ctx.log_message("Loading dataset...")
    ctx.report_progress(1, 3)
    data_file = os.path.join(dataset_path, "data.json") if os.path.isdir(dataset_path) else dataset_path
    if os.path.isfile(data_file):
        with open(data_file, "r") as f:
            raw_data = json.load(f)
    else:
        raise BlockInputError(f"Dataset not found: {data_file}", details="Check that the upstream block produced output", recoverable=False)

    if isinstance(raw_data, list) and len(raw_data) > 0:
        if isinstance(raw_data[0], dict):
            if training_format:
                texts = []
                for row in raw_data:
                    try:
                        texts.append(training_format.format(**row))
                    except KeyError as e:
                        raise BlockDataError(
                            f"training_format references missing column {e}. "
                            f"Available columns: {list(row.keys())}",
                            details=f"Column {e} not found in dataset row"
                        )
            else:
                text_key = text_column if text_column and text_column in raw_data[0] else (
                    "text" if "text" in raw_data[0] else list(raw_data[0].keys())[0]
                )
                texts = [str(row.get(text_key, "")) for row in raw_data]
        else:
            texts = [str(item) for item in raw_data]
    else:
        raise BlockDataError("Dataset must be a non-empty JSON list", details="Received empty or invalid dataset from upstream block")

    def tokenize_fn(examples):
        return tokenizer(examples["text"], truncation=True, max_length=max_seq_length, padding="max_length")

    dataset = Dataset.from_dict({"text": texts})
    tokenized = dataset.map(tokenize_fn, batched=True, remove_columns=["text"])

    if eval_split > 0:
        split = tokenized.train_test_split(test_size=eval_split, seed=42)
        train_dataset = split["train"]
        eval_dataset = split["test"]
        ctx.log_message(f"Training: {len(train_dataset)} train / {len(eval_dataset)} eval samples")
    else:
        train_dataset = tokenized
        eval_dataset = None
        ctx.log_message(f"Training samples: {len(tokenized)}")

    ctx.log_message("Starting full fine-tuning...")
    ctx.report_progress(2, 3)
    output_dir = os.path.join(ctx.run_dir, "model")
    os.makedirs(output_dir, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        learning_rate=lr,
        warmup_steps=warmup_steps,
        weight_decay=weight_decay,
        logging_steps=max(1, len(train_dataset) // (batch_size * 10)),
        save_strategy="epoch",
        eval_strategy="epoch" if eval_dataset else "no",
        report_to="none",
        fp16=_has_gpu(),
        gradient_checkpointing=gradient_checkpointing,
    )

    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    class CtxCallback(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kwargs):
            if logs:
                if "loss" in logs:
                    ctx.log_metric("train/loss", round(logs["loss"], 4), state.global_step)
                    ctx.log_message(f"  Step {state.global_step} — loss: {logs['loss']:.4f}")
                if "eval_loss" in logs:
                    ctx.log_metric("eval/loss", round(logs["eval_loss"], 4), state.global_step)
                    ctx.log_message(f"  Eval loss: {logs['eval_loss']:.4f}")
                if "learning_rate" in logs:
                    ctx.log_metric("learning_rate", round(logs["learning_rate"], 8), state.global_step)
            if state.max_steps > 0:
                ctx.report_progress(state.global_step, state.max_steps)

        def on_epoch_end(self, args, state, control, **kwargs):
            current_epoch = int(state.epoch)
            if checkpoint_interval > 0 and current_epoch % checkpoint_interval == 0:
                ckpt_path = os.path.join(output_dir, f"checkpoint-epoch-{current_epoch}")
                os.makedirs(ckpt_path, exist_ok=True)
                kwargs.get("model", model).save_pretrained(ckpt_path)
                tokenizer.save_pretrained(ckpt_path)
                # Search backward for most recent training loss (last entry may be eval)
                ckpt_metrics = {}
                for entry in reversed(state.log_history):
                    if "loss" in entry and "loss" not in ckpt_metrics:
                        ckpt_metrics["loss"] = entry["loss"]
                    if "eval_loss" in entry and "eval_loss" not in ckpt_metrics:
                        ckpt_metrics["eval_loss"] = entry["eval_loss"]
                    if "loss" in ckpt_metrics and "eval_loss" in ckpt_metrics:
                        break
                ctx.save_checkpoint(current_epoch, ckpt_path, ckpt_metrics)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=data_collator,
        callbacks=[CtxCallback()],
    )

    result = trainer.train()

    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    final_loss = round(result.training_loss, 4)

    # Save training metadata
    with open(os.path.join(output_dir, "training_config.json"), "w") as f:
        json.dump({
            "base_model": model_name,
            "method": "full_finetuning",
            "learning_rate": lr,
            "epochs": epochs,
            "batch_size": batch_size,
            "max_seq_length": max_seq_length,
            "warmup_steps": warmup_steps,
            "weight_decay": weight_decay,
            "gradient_checkpointing": gradient_checkpointing,
            "final_loss": final_loss,
            "total_params": total_params,
        }, f, indent=2)

    ctx.log_metric("final_loss", final_loss)
    ctx.log_metric("epochs_completed", epochs)
    ctx.save_output("trained_model", output_dir)
    ctx.save_output("metrics", {
        "final_loss": final_loss,
        "total_steps": result.global_step,
        "epochs_completed": epochs,
        "training_samples": len(train_dataset),
        "total_params": total_params,
    })
    ctx.log_message(f"Training complete. Final loss: {final_loss}")
    ctx.report_progress(1, 1)


# ── Fallback / simulation path (NEW) ──────────────────────────────────

def _run_fallback(
    ctx, model_name, dataset_path, lr, epochs, batch_size,
    max_seq_length, warmup_steps, weight_decay,
):
    """Config-only fallback when no training framework is installed."""
    ctx.log_message("Running in config-only mode: generating full fine-tuning plan")

    # Count samples
    data_file = os.path.join(dataset_path, "data.json") if os.path.isdir(dataset_path) else dataset_path
    num_samples = 0
    if os.path.isfile(data_file):
        with open(data_file, "r") as f:
            raw_data = json.load(f)
        if isinstance(raw_data, list):
            num_samples = len(raw_data)

    estimated_steps = (num_samples // batch_size) * epochs if num_samples else 0

    output_dir = os.path.join(ctx.run_dir, "model")
    os.makedirs(output_dir, exist_ok=True)

    training_plan = {
        "base_model": model_name,
        "method": "full_finetuning",
        "status": "plan_only",
        "message": (
            "Full fine-tuning could not run because required libraries are not installed. "
            "Install them with: pip install torch transformers datasets"
        ),
        "training_config": {
            "learning_rate": lr, "epochs": epochs, "batch_size": batch_size,
            "max_seq_length": max_seq_length, "warmup_steps": warmup_steps,
            "weight_decay": weight_decay,
        },
        "dataset_info": {"num_samples": num_samples},
        "estimates": {"estimated_steps": estimated_steps},
        "requirements": [
            "pip install torch transformers datasets",
            "pip install mlx-lm  # For Apple Silicon",
            f"Model: {model_name}",
            "WARNING: Full fine-tuning requires much more memory than LoRA",
        ],
    }

    plan_path = os.path.join(output_dir, "full_training_plan.json")
    with open(plan_path, "w") as f:
        json.dump(training_plan, f, indent=2)

    ctx.save_artifact("training_plan", plan_path)
    ctx.log_message(f"Dataset: {num_samples} samples, {epochs} epochs")
    ctx.log_message(f"Training plan saved to {plan_path}")
    ctx.log_message("Install torch + transformers (or mlx-lm on Apple Silicon) to execute actual training")

    ctx.save_output("trained_model", output_dir)
    ctx.save_output("metrics", {
        "status": "plan_only",
        "estimated_steps": estimated_steps,
    })
    ctx.report_progress(1, 1)
