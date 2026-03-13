"""LoRA Fine-Tuning — fine-tunes a model with LoRA adapters."""

import json
import os


def run(ctx):
    # Config
    model_name = ctx.config.get("model_name", "")
    r = int(ctx.config.get("r", 16))
    alpha = int(ctx.config.get("alpha", 32))
    lora_dropout = float(ctx.config.get("lora_dropout", 0.05))
    target_modules_str = ctx.config.get("target_modules", "q_proj,v_proj")
    lr = float(ctx.config.get("lr", 1e-4))
    epochs = int(ctx.config.get("epochs", 3))
    batch_size = int(ctx.config.get("batch_size", 4))
    max_seq_length = int(ctx.config.get("max_seq_length", 512))
    text_column = ctx.config.get("text_column", "")
    prompt_template = ctx.config.get("prompt_template", "")
    eval_split = float(ctx.config.get("eval_split", 0.0))
    save_merged = ctx.config.get("save_merged", False)
    if isinstance(save_merged, str):
        save_merged = save_merged.lower() in ("true", "1", "yes")

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
        raise ValueError("model_name is required — set it in config or connect a model to the input port")

    # Load dataset
    dataset_path = ctx.load_input("dataset")

    # Load dataset
    data_file = os.path.join(dataset_path, "data.json") if os.path.isdir(dataset_path) else dataset_path
    if os.path.isfile(data_file):
        with open(data_file, "r") as f:
            raw_data = json.load(f)
    else:
        raise FileNotFoundError(f"Dataset not found: {data_file}")

    if not isinstance(raw_data, list) or len(raw_data) == 0:
        raise ValueError("Dataset must be a non-empty JSON list")

    # Import required libraries — fallback if unavailable
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
        from peft import LoraConfig, get_peft_model, TaskType
        from datasets import Dataset

        _run_real_training(
            ctx, model_name, raw_data, r, alpha, lora_dropout, target_modules,
            lr, epochs, batch_size, max_seq_length, text_column, prompt_template,
            eval_split, save_merged,
            torch, AutoModelForCausalLM, AutoTokenizer, TrainingArguments,
            Trainer, TrainerCallback, DataCollatorForLanguageModeling,
            LoraConfig, get_peft_model, TaskType, Dataset,
        )
    except ImportError as e:
        ctx.log_message(f"Required libraries not available ({e}); running in config-only fallback mode")
        _run_fallback(
            ctx, model_name, raw_data, r, alpha, lora_dropout, target_modules,
            lr, epochs, batch_size, max_seq_length, save_merged,
        )


def _run_real_training(
    ctx, model_name, raw_data, r, alpha, lora_dropout, target_modules,
    lr, epochs, batch_size, max_seq_length, text_column, prompt_template,
    eval_split, save_merged,
    torch, AutoModelForCausalLM, AutoTokenizer, TrainingArguments,
    Trainer, TrainerCallback, DataCollatorForLanguageModeling,
    LoraConfig, get_peft_model, TaskType, Dataset,
):
    """Full LoRA training using HuggingFace transformers + PEFT."""

    ctx.log_message(f"LoRA fine-tuning: {model_name} (r={r}, alpha={alpha})")
    ctx.log_message(f"LR={lr}, epochs={epochs}, batch_size={batch_size}")
    ctx.log_message(f"Target modules: {target_modules}, dropout={lora_dropout}")

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

    # Determine text field
    if isinstance(raw_data[0], dict):
        if prompt_template:
            texts = []
            for row in raw_data:
                try:
                    texts.append(prompt_template.format(**row))
                except KeyError as e:
                    raise ValueError(
                        f"prompt_template references missing column {e}. "
                        f"Available columns: {list(row.keys())}"
                    )
        else:
            text_key = text_column if text_column and text_column in raw_data[0] else (
                "text" if "text" in raw_data[0] else list(raw_data[0].keys())[0]
            )
            texts = [str(row.get(text_key, "")) for row in raw_data]
    else:
        texts = [str(item) for item in raw_data]

    def tokenize_fn(examples):
        return tokenizer(examples["text"], truncation=True, max_length=max_seq_length, padding="max_length")

    ctx.log_message("Loading dataset...")
    ctx.report_progress(1, 3)

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
    ctx.log_message("Starting training...")
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
        fp16=torch.cuda.is_available(),
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
        ctx.log_message("Merging LoRA adapters into base model...")
        merged_model = model.merge_and_unload()
        merged_model.save_pretrained(output_dir)
        ctx.log_message("Saved merged model (standalone, no adapter dependency)")
    else:
        model.save_pretrained(output_dir)
        ctx.log_message("Saved LoRA adapters (requires base model to load)")
    tokenizer.save_pretrained(output_dir)

    final_loss = round(result.training_loss, 4)

    # Save training metadata
    with open(os.path.join(output_dir, "training_config.json"), "w") as f:
        json.dump({
            "base_model": model_name,
            "method": "lora_finetuning",
            "lora_rank": r,
            "lora_alpha": alpha,
            "lora_dropout": lora_dropout,
            "target_modules": target_modules,
            "learning_rate": lr,
            "epochs": epochs,
            "batch_size": batch_size,
            "max_seq_length": max_seq_length,
            "save_merged": save_merged,
            "final_loss": final_loss,
            "trainable_params": trainable,
            "total_params": total_params,
        }, f, indent=2)

    ctx.log_metric("train/loss", final_loss)
    ctx.log_metric("epochs_completed", epochs)
    ctx.log_metric("trainable_params", trainable)
    ctx.save_output("model", output_dir)
    ctx.save_output("metrics", {
        "final_loss": final_loss,
        "total_steps": result.global_step,
        "epochs_completed": epochs,
        "trainable_params": trainable,
        "total_params": total_params,
        "lora_rank": r,
        "lora_alpha": alpha,
        "save_merged": save_merged,
    })
    ctx.log_message(f"LoRA training complete. Final loss: {final_loss}")
    ctx.report_progress(1, 1)


def _run_fallback(
    ctx, model_name, raw_data, r, alpha, lora_dropout, target_modules,
    lr, epochs, batch_size, max_seq_length, save_merged,
):
    """Config-only fallback when PEFT/transformers are not installed.

    Generates a configuration plan JSON with all training parameters,
    estimated compute, and instructions for installing the required libraries.
    """
    ctx.log_message("Running in config-only mode: generating LoRA training plan")

    # Estimate trainable parameters based on LoRA config
    # LoRA adds r * d_model * 2 * num_target_modules parameters
    est_params = r * 4096 * 2 * len(target_modules)  # rough estimate assuming d_model=4096
    estimated_steps = (len(raw_data) // batch_size) * epochs

    output_dir = os.path.join(ctx.run_dir, "model")
    os.makedirs(output_dir, exist_ok=True)

    training_plan = {
        "base_model": model_name,
        "method": "lora_finetuning",
        "status": "plan_only",
        "message": (
            "LoRA training could not run because required libraries are not installed. "
            "Install them with: pip install torch transformers peft datasets"
        ),
        "lora_config": {
            "r": r,
            "lora_alpha": alpha,
            "lora_dropout": lora_dropout,
            "target_modules": target_modules,
            "bias": "none",
            "task_type": "CAUSAL_LM",
        },
        "training_config": {
            "learning_rate": lr,
            "epochs": epochs,
            "batch_size": batch_size,
            "max_seq_length": max_seq_length,
            "save_merged": save_merged,
        },
        "dataset_info": {
            "num_samples": len(raw_data),
            "sample_keys": list(raw_data[0].keys()) if isinstance(raw_data[0], dict) else [],
        },
        "estimates": {
            "trainable_params": est_params,
            "estimated_steps": estimated_steps,
            "estimated_epochs": epochs,
        },
        "requirements": [
            "pip install torch transformers peft datasets",
            f"Model: {model_name}",
            "GPU recommended for efficient LoRA training",
        ],
    }

    plan_path = os.path.join(output_dir, "lora_training_plan.json")
    with open(plan_path, "w") as f:
        json.dump(training_plan, f, indent=2)

    ctx.save_artifact("training_plan", plan_path)

    ctx.log_message(f"Dataset: {len(raw_data)} samples, {epochs} epochs, batch_size={batch_size}")
    ctx.log_message(f"Estimated steps: {estimated_steps}")
    ctx.log_message(f"Training plan saved to {plan_path}")
    ctx.log_message("Install torch + transformers + peft to execute actual training")

    ctx.save_output("model", output_dir)
    ctx.save_output("metrics", {
        "status": "plan_only",
        "estimated_steps": estimated_steps,
        "lora_rank": r,
        "lora_alpha": alpha,
    })
    ctx.report_progress(1, 1)
