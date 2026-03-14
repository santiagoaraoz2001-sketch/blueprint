"""QLoRA Fine-Tuning — LoRA with 4-bit quantization for memory-efficient training."""

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
    r = int(ctx.config.get("r", 16))
    alpha = int(ctx.config.get("alpha", 32))
    lr = float(ctx.config.get("lr", 2e-4))
    epochs = int(ctx.config.get("epochs", 3))
    batch_size = int(ctx.config.get("batch_size", 4))
    bits = int(ctx.config.get("bits", 4))
    double_quant = ctx.config.get("double_quant", True)
    max_seq_length = int(ctx.config.get("max_seq_length", 512))
    lora_dropout = float(ctx.config.get("lora_dropout", 0.05))
    target_modules_str = ctx.config.get("target_modules", "q_proj,v_proj")
    text_column = ctx.config.get("text_column") or _dataset_meta.get("text_column", "")
    training_format = ctx.config.get("training_format", ctx.config.get("prompt_template", ""))
    eval_split = float(ctx.config.get("eval_split", 0.0))
    save_merged = ctx.config.get("save_merged", False)
    if isinstance(save_merged, str):
        save_merged = save_merged.lower() in ("true", "1", "yes")
    checkpoint_interval = int(ctx.config.get("checkpoint_interval", 0))

    # Normalize double_quant to bool
    if isinstance(double_quant, str):
        double_quant = double_quant.lower() in ("true", "1", "yes")

    # Parse target modules
    target_modules = [m.strip() for m in target_modules_str.split(",") if m.strip()]
    if not target_modules:
        target_modules = ["q_proj", "v_proj"]

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
        raise BlockConfigError("model_name", "Model name is required — set it in config or connect a model to the input port")

    # Load dataset
    dataset_path = ctx.resolve_as_file_path("dataset")

    # Import required libraries
    try:
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            TrainingArguments,
            Trainer,
            TrainerCallback,
            DataCollatorForLanguageModeling,
        )
        from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
        from datasets import Dataset
        import bitsandbytes  # noqa: F401
    except ImportError as e:
        from backend.block_sdk.exceptions import BlockDependencyError
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install datasets peft torch transformers",
        )

    ctx.log_message(f"QLoRA fine-tuning: {model_name}")
    ctx.log_message(f"LoRA r={r}, alpha={alpha}, bits={bits}, double_quant={double_quant}")
    ctx.log_message(f"LR={lr}, epochs={epochs}, batch_size={batch_size}")
    ctx.log_message(f"Target modules: {target_modules}, dropout={lora_dropout}")

    # Load tokenizer
    ctx.log_message("Loading tokenizer and quantized model...")
    ctx.report_progress(0, 3)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Configure quantization
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=(bits == 4),
        load_in_8bit=(bits == 8),
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=double_quant,
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.float16,
    )

    model = prepare_model_for_kbit_training(model)

    # Apply LoRA
    lora_config = LoraConfig(
        r=r,
        lora_alpha=alpha,
        target_modules=target_modules,
        lora_dropout=lora_dropout,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    ctx.log_message(f"Trainable params: {trainable:,} / {total_params:,} ({100 * trainable / total_params:.2f}%)")

    # Load and tokenize dataset
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
        ctx.log_message(f"Dataset: {len(train_dataset)} train / {len(eval_dataset)} eval samples")
    else:
        train_dataset = tokenized
        eval_dataset = None
        ctx.log_message(f"Dataset: {len(tokenized)} samples")

    # Training
    ctx.log_message("Starting QLoRA training...")
    ctx.report_progress(2, 3)
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
        fp16=True,
        gradient_checkpointing=True,
        optim="paged_adamw_8bit",
    )

    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    class CtxCallback(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kwargs):
            if logs and "loss" in logs:
                ctx.log_metric("train/loss", round(logs["loss"], 4), state.global_step)
                ctx.log_message(f"  Step {state.global_step} — loss: {logs['loss']:.4f}")
            if logs and "eval_loss" in logs:
                ctx.log_metric("eval/loss", round(logs["eval_loss"], 4), state.global_step)
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

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=data_collator,
        callbacks=[CtxCallback()],
    )

    result = trainer.train()

    # Save
    if save_merged:
        ctx.log_message("Merging QLoRA adapters into base model (fp16)...")
        merged_model = model.merge_and_unload()
        merged_model.save_pretrained(output_dir, safe_serialization=True)
        ctx.log_message("Saved merged model (standalone, no adapter/quantization dependency)")
    else:
        model.save_pretrained(output_dir)
        ctx.log_message("Saved QLoRA adapters (requires base model + bitsandbytes to load)")
    tokenizer.save_pretrained(output_dir)

    final_loss = round(result.training_loss, 4)

    # Save training metadata
    with open(os.path.join(output_dir, "training_config.json"), "w") as f:
        json.dump({
            "base_model": model_name,
            "method": "qlora_finetuning",
            "lora_rank": r,
            "lora_alpha": alpha,
            "lora_dropout": lora_dropout,
            "target_modules": target_modules,
            "bits": bits,
            "double_quant": double_quant,
            "learning_rate": lr,
            "epochs": epochs,
            "batch_size": batch_size,
            "max_seq_length": max_seq_length,
            "save_merged": save_merged,
            "final_loss": final_loss,
            "trainable_params": trainable,
            "total_params": total_params,
        }, f, indent=2)

    ctx.log_metric("final_loss", final_loss)
    ctx.log_metric("epochs_completed", epochs)
    ctx.log_metric("trainable_params", trainable)
    ctx.save_output("model", output_dir)
    ctx.save_output("metrics", {
        "final_loss": final_loss,
        "total_steps": result.global_step,
        "epochs_completed": epochs,
        "bits": bits,
        "double_quant": double_quant,
        "trainable_params": trainable,
        "total_params": total_params,
        "lora_rank": r,
        "lora_alpha": alpha,
        "save_merged": save_merged,
    })
    ctx.log_message(f"QLoRA training complete. Final loss: {final_loss}")
    ctx.report_progress(1, 1)
