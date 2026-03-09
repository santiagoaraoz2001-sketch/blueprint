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

    # Import required libraries — raise on failure
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
    except ImportError as e:
        raise ImportError(
            f"Required library not installed: {e}. "
            f"Install with: pip install torch transformers peft datasets"
        ) from e

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

    # Load and tokenize dataset
    ctx.log_message("Loading dataset...")
    ctx.report_progress(1, 3)
    data_file = os.path.join(dataset_path, "data.json") if os.path.isdir(dataset_path) else dataset_path
    if os.path.isfile(data_file):
        with open(data_file, "r") as f:
            raw_data = json.load(f)
    else:
        raise FileNotFoundError(f"Dataset not found: {data_file}")

    # Determine text field
    if isinstance(raw_data, list) and len(raw_data) > 0:
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
    else:
        raise ValueError("Dataset must be a non-empty JSON list")

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
                ctx.log_metric("train_loss", round(logs["loss"], 4), state.global_step)
                ctx.log_message(f"  Step {state.global_step} — loss: {logs['loss']:.4f}")
            if logs and "eval_loss" in logs:
                ctx.log_metric("eval_loss", round(logs["eval_loss"], 4), state.global_step)
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

    ctx.log_metric("final_loss", final_loss)
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
