"""BALLAST Training — balanced layer-wise training approach.

Freezes a portion of model layers (controlled by layer_depth) and trains only
the unfrozen layers with per-group learning-rate scaling (balance_factor).
"""

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


def run(ctx):
    dataset_path = ctx.resolve_as_file_path("dataset")

    # Read upstream dataset metadata
    _dataset_meta = {}
    try:
        _meta_input = ctx.load_input("dataset_meta")
        if isinstance(_meta_input, dict):
            _dataset_meta = _meta_input
    except (ValueError, KeyError):
        pass

    model_name = ctx.config.get("model_name", "")
    layer_depth = float(ctx.config.get("layer_depth", 0.5))
    balance_factor = float(ctx.config.get("balance_factor", 1.0))
    epochs = int(ctx.config.get("epochs", 5))
    lr = float(ctx.config.get("lr", 2e-5))
    batch_size = int(ctx.config.get("batch_size", 4))
    max_seq_length = int(ctx.config.get("max_seq_length", 512))
    text_column = ctx.config.get("text_column") or _dataset_meta.get("text_column", "")
    training_format = ctx.config.get("training_format", ctx.config.get("prompt_template", ""))
    eval_split = float(ctx.config.get("eval_split", 0.0))
    checkpoint_interval = int(ctx.config.get("checkpoint_interval", 0))

    # Try to get model from input port
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
        raise BlockConfigError("model_name", "Model name is required (via config or model input port)")

    # ── Validate model for training ──
    model_name = _validate_model_for_training(model_name, model_info, ctx)

    ctx.log_message(f"BALLAST training: {model_name}")
    ctx.log_message(f"layer_depth={layer_depth}, balance_factor={balance_factor}, epochs={epochs}")

    # ── Load dataset ────────────────────────────────────────────────────
    data_file = os.path.join(dataset_path, "data.json") if os.path.isdir(dataset_path) else dataset_path
    if not os.path.isfile(data_file):
        raise BlockInputError(f"Dataset not found: {data_file}", details="Check that the upstream block produced output", recoverable=False)

    with open(data_file, "r") as f:
        raw_data = json.load(f)

    if not isinstance(raw_data, list) or len(raw_data) == 0:
        raise BlockDataError("Dataset must be a non-empty JSON list", details="Received empty or invalid dataset from upstream block")

    ctx.log_message(f"Dataset: {len(raw_data)} samples")

    # ── Guard heavy imports ──────────────────────────────────────────────
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
        from backend.block_sdk.exceptions import BlockDependencyError
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install datasets torch transformers",
        )

    _run_real_training(
        ctx, model_name, raw_data, layer_depth, balance_factor,
        epochs, lr, batch_size, max_seq_length, checkpoint_interval,
        torch, AutoModelForCausalLM, AutoTokenizer,
        TrainingArguments, Trainer, TrainerCallback,
        DataCollatorForLanguageModeling, Dataset,
    )


# ── Real training path ─────────────────────────────────────────────────────


def _run_real_training(
    ctx, model_name, raw_data, layer_depth, balance_factor,
    epochs, lr, batch_size, max_seq_length, checkpoint_interval,
    torch, AutoModelForCausalLM, AutoTokenizer,
    TrainingArguments, Trainer, TrainerCallback,
    DataCollatorForLanguageModeling, Dataset,
):
    """Full BALLAST training using HuggingFace transformers."""

    # ── Load tokenizer and model ────────────────────────────────────────
    ctx.log_message("Loading tokenizer and model...")
    ctx.report_progress(0, 4)

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto" if torch.cuda.is_available() else None,
    )

    # ── Identify transformer layers ─────────────────────────────────────
    ctx.report_progress(1, 4)
    layer_groups = _identify_layer_groups(model)
    total_layers = len(layer_groups)

    if total_layers == 0:
        ctx.log_message("Could not identify distinct layer groups; training all parameters")
        freeze_count = 0
    else:
        freeze_count = int(total_layers * (1.0 - layer_depth))
        freeze_count = max(0, min(freeze_count, total_layers - 1))  # keep at least 1 trainable

    ctx.log_message(f"Model has {total_layers} layer groups; freezing {freeze_count}, training {total_layers - freeze_count}")

    # ── Freeze layers ───────────────────────────────────────────────────
    # First freeze everything
    for param in model.parameters():
        param.requires_grad = False

    # Unfreeze layers beyond the freeze boundary
    unfrozen_group_names = set()
    for idx, (group_name, params) in enumerate(layer_groups):
        if idx >= freeze_count:
            for p in params:
                p.requires_grad = True
            unfrozen_group_names.add(group_name)

    # Always unfreeze the LM head / output projection
    _unfreeze_head(model)

    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    ctx.log_message(f"Trainable params: {trainable_params:,} / {total_params:,} "
                    f"({100 * trainable_params / max(total_params, 1):.2f}%)")
    ctx.log_metric("trainable_params", float(trainable_params))
    ctx.log_metric("total_params", float(total_params))

    # ── Build per-layer-group optimiser param groups ────────────────────
    # balance_factor scales the LR: deeper (later) layers get higher LR
    optimizer_groups = _build_optimizer_groups(
        model, layer_groups, freeze_count, lr, balance_factor
    )

    # ── Prepare dataset ─────────────────────────────────────────────────
    ctx.log_message("Tokenizing dataset...")
    ctx.report_progress(2, 4)

    text_column = ctx.config.get("text_column", "")
    training_format = ctx.config.get("training_format", ctx.config.get("prompt_template", ""))
    eval_split = float(ctx.config.get("eval_split", 0.0))

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

    def tokenize_fn(examples):
        return tokenizer(
            examples["text"], truncation=True,
            max_length=max_seq_length, padding="max_length",
        )

    dataset = Dataset.from_dict({"text": texts})
    tokenized = dataset.map(tokenize_fn, batched=True, remove_columns=["text"])

    if eval_split > 0:
        split = tokenized.train_test_split(test_size=eval_split, seed=42)
        train_dataset = split["train"]
        eval_dataset = split["test"]
        ctx.log_message(f"Tokenized {len(train_dataset)} train / {len(eval_dataset)} eval samples (max_seq_length={max_seq_length})")
    else:
        train_dataset = tokenized
        eval_dataset = None
        ctx.log_message(f"Tokenized {len(tokenized)} samples (max_seq_length={max_seq_length})")

    # ── Training ────────────────────────────────────────────────────────
    ctx.log_message("Starting BALLAST training...")
    ctx.report_progress(3, 4)

    output_dir = os.path.join(ctx.run_dir, "model")
    os.makedirs(output_dir, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        learning_rate=lr,
        logging_steps=max(1, len(train_dataset) // (batch_size * 10)),
        save_strategy="epoch",
        eval_strategy="epoch" if eval_dataset else "no",
        report_to="none",
        fp16=torch.cuda.is_available(),
    )

    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    class BallastCallback(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kwargs):
            if logs and "loss" in logs:
                ctx.log_metric("train/loss", round(float(logs["loss"]), 4), state.global_step)
                ctx.log_message(f"  Step {state.global_step} -- loss: {logs['loss']:.4f}")
            if logs and "eval_loss" in logs:
                ctx.log_metric("eval/loss", round(float(logs["eval_loss"]), 4), state.global_step)
                ctx.log_message(f"  Eval loss: {logs['eval_loss']:.4f}")
            if state.max_steps > 0:
                ctx.report_progress(state.global_step, state.max_steps)

        def on_epoch_end(self, args, state, control, **kwargs):
            current_epoch = int(state.epoch)
            if checkpoint_interval > 0 and current_epoch % checkpoint_interval == 0:
                ckpt_path = os.path.join(output_dir, f"checkpoint-epoch-{current_epoch}")
                os.makedirs(ckpt_path, exist_ok=True)
                kwargs.get("model", model).save_pretrained(ckpt_path)
                tokenizer.save_pretrained(ckpt_path)
                # Search backward for most recent training loss and eval loss
                ckpt_metrics = {}
                for entry in reversed(state.log_history):
                    if "loss" in entry and "loss" not in ckpt_metrics:
                        ckpt_metrics["loss"] = entry["loss"]
                    if "eval_loss" in entry and "eval_loss" not in ckpt_metrics:
                        ckpt_metrics["eval_loss"] = entry["eval_loss"]
                    if "loss" in ckpt_metrics and "eval_loss" in ckpt_metrics:
                        break
                ctx.save_checkpoint(current_epoch, ckpt_path, ckpt_metrics)

    # Build custom optimizer with per-group LRs
    optimizer = torch.optim.AdamW(optimizer_groups, weight_decay=0.01)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=data_collator,
        callbacks=[BallastCallback()],
        optimizers=(optimizer, None),  # custom optimizer, default scheduler
    )

    result = trainer.train()

    # ── Save ────────────────────────────────────────────────────────────
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Also save BALLAST metadata
    ballast_meta = {
        "base_model": model_name,
        "method": "ballast",
        "layer_depth": layer_depth,
        "balance_factor": balance_factor,
        "frozen_layers": freeze_count,
        "total_layers": total_layers,
        "trainable_params": trainable_params,
        "total_params": total_params,
    }
    with open(os.path.join(output_dir, "ballast_config.json"), "w") as f:
        json.dump(ballast_meta, f, indent=2)

    final_loss = round(float(result.training_loss), 4)
    ctx.log_metric("train/loss", final_loss)
    ctx.log_metric("train/epochs_completed", float(epochs))
    ctx.log_message(f"BALLAST training complete. Final loss: {final_loss}")

    # Branch: real training succeeded
    ctx.save_output("trained_model", output_dir)
    # Branch: real training succeeded
    ctx.save_output("metrics", {
        "final_loss": final_loss,
        "epochs": epochs,
        "total_steps": result.global_step,
        "trainable_params": trainable_params,
        "frozen_layers": freeze_count,
    })
    ctx.report_progress(1, 1)


# ── Fallback path ──────────────────────────────────────────────────────────


def _run_fallback(ctx, model_name, raw_data, layer_depth, balance_factor, epochs, lr, batch_size):
    """Config-only fallback when transformers is not installed.

    Generates the full training configuration and reports what would happen,
    without simulating fake losses.
    """
    ctx.log_message("Running in config-only mode: generating training plan")

    # Estimate layer structure from known model architectures
    layer_estimate = _estimate_layers(model_name)
    total_layers = layer_estimate["num_layers"]
    freeze_count = int(total_layers * (1.0 - layer_depth))
    freeze_count = max(0, min(freeze_count, total_layers - 1))
    train_layers = total_layers - freeze_count

    ctx.log_message(f"Estimated {total_layers} layers for {model_name}")
    ctx.log_message(f"Would freeze {freeze_count} layers, train {train_layers} layers")
    ctx.log_message(f"Dataset: {len(raw_data)} samples, {epochs} epochs, batch_size={batch_size}")

    # Build per-layer LR schedule description
    lr_schedule = []
    for i in range(train_layers):
        depth_ratio = (i + 1) / train_layers
        group_lr = lr * (1.0 + (balance_factor - 1.0) * depth_ratio)
        lr_schedule.append({
            "layer_group": freeze_count + i,
            "learning_rate": round(group_lr, 8),
            "depth_ratio": round(depth_ratio, 4),
        })

    # Save training plan
    output_dir = os.path.join(ctx.run_dir, "model")
    os.makedirs(output_dir, exist_ok=True)

    training_plan = {
        "base_model": model_name,
        "method": "ballast",
        "status": "plan_only",
        "layer_depth": layer_depth,
        "balance_factor": balance_factor,
        "estimated_total_layers": total_layers,
        "frozen_layers": freeze_count,
        "trainable_layers": train_layers,
        "epochs": epochs,
        "batch_size": batch_size,
        "base_lr": lr,
        "lr_schedule": lr_schedule,
        "dataset_size": len(raw_data),
        "estimated_steps": (len(raw_data) // batch_size) * epochs,
        "architecture": layer_estimate,
        "requirements": [
            "pip install torch transformers datasets",
            f"Model: {model_name}",
            f"GPU recommended for models with >{layer_estimate.get('est_params', '?')} parameters",
        ],
    }

    plan_path = os.path.join(output_dir, "ballast_training_plan.json")
    with open(plan_path, "w") as f:
        json.dump(training_plan, f, indent=2)

    config_path = os.path.join(output_dir, "config.json")
    with open(config_path, "w") as f:
        json.dump({
            "base_model": model_name,
            "method": "ballast",
            "layer_depth": layer_depth,
            "balance_factor": balance_factor,
            "status": "plan_only",
        }, f, indent=2)

    ctx.save_artifact("training_plan", plan_path)

    ctx.log_metric("frozen_layers", float(freeze_count))
    ctx.log_metric("trainable_layers", float(train_layers))
    ctx.log_metric("estimated_steps", float((len(raw_data) // batch_size) * epochs))

    ctx.log_message(f"Training plan saved to {plan_path}")
    ctx.log_message("Install torch + transformers to execute actual training")

    # Branch: fallback/plan-only mode (dead code — _run_fallback is never called)
    ctx.save_output("trained_model", output_dir)
    # Branch: fallback/plan-only mode (dead code — _run_fallback is never called)
    ctx.save_output("metrics", {
        "status": "plan_only",
        "frozen_layers": freeze_count,
        "trainable_layers": train_layers,
        "estimated_steps": (len(raw_data) // batch_size) * epochs,
    })
    ctx.report_progress(1, 1)


# ── Layer identification helpers ───────────────────────────────────────────


def _identify_layer_groups(model):
    """Identify repeated transformer layer groups in a model.

    Returns a list of (group_name, [parameters]) tuples ordered from
    shallowest to deepest.
    """
    layer_groups = []
    seen_prefixes = set()

    for name, module in model.named_modules():
        # Match common transformer layer patterns:
        #   model.layers.0, model.transformer.h.0, model.gpt_neox.layers.0, etc.
        parts = name.split(".")
        for i, part in enumerate(parts):
            if part.isdigit() and i > 0:
                prefix = ".".join(parts[:i + 1])
                if prefix not in seen_prefixes:
                    seen_prefixes.add(prefix)
                    params = list(module.parameters())
                    if params:
                        layer_groups.append((prefix, params))
                break

    # Sort by the numeric layer index (last numeric component)
    def _layer_index(group_name):
        parts = group_name.split(".")
        for p in reversed(parts):
            if p.isdigit():
                return int(p)
        return 0

    layer_groups.sort(key=lambda x: _layer_index(x[0]))
    return layer_groups


def _unfreeze_head(model):
    """Unfreeze the output/LM head of the model."""
    head_names = ["lm_head", "score", "classifier", "output"]
    for name, param in model.named_parameters():
        for head in head_names:
            if head in name:
                param.requires_grad = True
                break


def _build_optimizer_groups(model, layer_groups, freeze_count, base_lr, balance_factor):
    """Build optimizer parameter groups with BALLAST LR scaling.

    Deeper (later) unfrozen layers get progressively higher learning rates,
    controlled by balance_factor.  When balance_factor=1.0 all groups get
    the same LR.  When balance_factor>1.0, the deepest layer gets
    base_lr * balance_factor and shallower layers are linearly interpolated.
    """
    unfrozen_groups = layer_groups[freeze_count:]
    n_groups = len(unfrozen_groups)

    param_groups = []
    assigned_ids = set()

    for idx, (group_name, params) in enumerate(unfrozen_groups):
        trainable = [p for p in params if p.requires_grad]
        if not trainable:
            continue

        depth_ratio = (idx + 1) / max(n_groups, 1)
        group_lr = base_lr * (1.0 + (balance_factor - 1.0) * depth_ratio)

        for p in trainable:
            assigned_ids.add(id(p))

        param_groups.append({
            "params": trainable,
            "lr": group_lr,
            "name": group_name,
        })

    # Collect any remaining trainable params (e.g. LM head) not in layer groups
    remaining = [p for p in model.parameters() if p.requires_grad and id(p) not in assigned_ids]
    if remaining:
        param_groups.append({
            "params": remaining,
            "lr": base_lr * balance_factor,  # head gets highest LR
            "name": "head_and_other",
        })

    return param_groups


def _estimate_layers(model_name):
    """Rough layer-count estimates for common model families (fallback mode)."""
    name = model_name.lower()

    estimates = {
        "llama-3": {"num_layers": 32, "est_params": "8B"},
        "llama-2-7b": {"num_layers": 32, "est_params": "7B"},
        "llama-2-13b": {"num_layers": 40, "est_params": "13B"},
        "llama-2-70b": {"num_layers": 80, "est_params": "70B"},
        "mistral-7b": {"num_layers": 32, "est_params": "7B"},
        "mixtral": {"num_layers": 32, "est_params": "8x7B"},
        "phi-2": {"num_layers": 32, "est_params": "2.7B"},
        "phi-3": {"num_layers": 32, "est_params": "3.8B"},
        "gemma-2b": {"num_layers": 18, "est_params": "2B"},
        "gemma-7b": {"num_layers": 28, "est_params": "7B"},
        "gpt2": {"num_layers": 12, "est_params": "117M"},
        "gpt2-medium": {"num_layers": 24, "est_params": "345M"},
        "gpt2-large": {"num_layers": 36, "est_params": "774M"},
        "gpt2-xl": {"num_layers": 48, "est_params": "1.5B"},
        "tinyllama": {"num_layers": 22, "est_params": "1.1B"},
        "qwen": {"num_layers": 32, "est_params": "7B"},
        "falcon-7b": {"num_layers": 32, "est_params": "7B"},
    }

    for key, info in estimates.items():
        if key in name:
            return info

    # Default guess for unknown models
    return {"num_layers": 32, "est_params": "unknown"}
