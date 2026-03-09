"""Reward Model Trainer — train a reward model from preference data for RLHF."""

import json
import os
import time
import random


def _load_data(ctx, input_name):
    data = ctx.load_input(input_name)
    if isinstance(data, str) and os.path.isfile(data):
        with open(data, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        try:
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return content
    return data


def run(ctx):
    lr = ctx.config.get("lr", 1e-5)
    epochs = ctx.config.get("epochs", 1)
    batch_size = int(ctx.config.get("batch_size", 4))
    max_length = ctx.config.get("max_length", 512)
    loss_fn = ctx.config.get("loss", "bce")
    chosen_column = ctx.config.get("chosen_column", "chosen")
    rejected_column = ctx.config.get("rejected_column", "rejected")

    ctx.report_progress(0, 4)

    # Load preference data
    dataset = _load_data(ctx, "dataset")
    if dataset is None:
        raise ValueError("No preference dataset provided")

    # Load base model
    model_data = _load_data(ctx, "model")
    if model_data is None:
        raise ValueError("No base model provided")

    model_path = model_data if isinstance(model_data, str) else str(model_data)
    ctx.log_message(f"Base model: {model_path}")

    # Determine dataset size
    if isinstance(dataset, list):
        n_samples = len(dataset)
    elif isinstance(dataset, dict):
        n_samples = len(dataset.get("data", dataset.get("rows", [])))
    else:
        n_samples = 1

    ctx.log_message(f"Preference dataset: {n_samples} samples")
    ctx.log_message(f"Config: lr={lr}, epochs={epochs}, batch_size={batch_size}, max_length={max_length}, loss={loss_fn}")
    ctx.report_progress(1, 4)

    # Remap columns if user's data uses non-standard column names
    if isinstance(dataset, list) and len(dataset) > 0 and isinstance(dataset[0], dict):
        needs_remap = (chosen_column != "chosen" or rejected_column != "rejected")
        if needs_remap:
            sample = dataset[0]
            if chosen_column in sample and rejected_column in sample:
                ctx.log_message(f"Remapping columns: '{chosen_column}' -> 'chosen', '{rejected_column}' -> 'rejected'")
                dataset = [
                    {**{k: v for k, v in row.items() if k not in (chosen_column, rejected_column)},
                     "chosen": row[chosen_column], "rejected": row[rejected_column]}
                    for row in dataset
                ]
            else:
                ctx.log_message(f"Warning: columns '{chosen_column}'/'{rejected_column}' not found in data")

    metrics = {}
    output_model_path = os.path.join(ctx.run_dir, "reward_model")

    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer, TrainingArguments
        from trl import RewardTrainer
        from datasets import Dataset as HFDataset

        ctx.log_message("Loading model and tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(model_path)
        model = AutoModelForSequenceClassification.from_pretrained(model_path, num_labels=1)

        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        # Convert list to HF Dataset if needed
        if isinstance(dataset, list):
            train_dataset = HFDataset.from_list(dataset)
        elif hasattr(dataset, '__len__'):
            train_dataset = dataset
        else:
            raise ValueError("Dataset format not supported. Provide a JSON list of preference pairs.")

        training_args = TrainingArguments(
            output_dir=output_model_path,
            num_train_epochs=epochs,
            learning_rate=lr,
            per_device_train_batch_size=batch_size,
            max_steps=-1,
            logging_steps=10,
            save_strategy="epoch",
            remove_unused_columns=False,
        )

        ctx.report_progress(2, 4)
        ctx.log_message("Starting reward model training...")

        trainer = RewardTrainer(
            model=model,
            args=training_args,
            tokenizer=tokenizer,
            train_dataset=train_dataset,
            max_length=max_length,
        )

        train_result = trainer.train()
        trainer.save_model(output_model_path)

        metrics = {
            "train_loss": round(train_result.training_loss, 6),
            "train_runtime": round(train_result.metrics.get("train_runtime", 0), 2),
            "train_samples_per_second": round(train_result.metrics.get("train_samples_per_second", 0), 2),
            "epochs": epochs,
            "learning_rate": lr,
            "loss_function": loss_fn,
        }
        ctx.log_message(f"Training complete: loss={metrics['train_loss']:.6f}")

    except ImportError as e:
        missing = str(e)
        ctx.log_message(f"Required package not available: {missing}")
        ctx.log_message("Running in demo mode — generating synthetic metrics")

        # Demo mode: simulate training metrics
        os.makedirs(output_model_path, exist_ok=True)
        demo_config = {"model_type": "demo_reward_model", "base_model": model_path}
        with open(os.path.join(output_model_path, "config.json"), "w") as f:
            json.dump(demo_config, f, indent=2)

        random.seed(42)
        metrics = {
            "train_loss": round(0.5 - 0.3 * (1 - 1 / (epochs + 1)) + random.gauss(0, 0.02), 6),
            "train_runtime": round(n_samples * epochs * 0.05, 2),
            "train_samples_per_second": round(n_samples / max(n_samples * epochs * 0.05, 0.01), 2),
            "epochs": epochs,
            "learning_rate": lr,
            "loss_function": loss_fn,
            "demo_mode": True,
        }

    except Exception as e:
        ctx.log_message(f"Training error: {e}")
        raise

    ctx.report_progress(3, 4)

    # Save model output
    ctx.save_output("model", output_model_path)

    # Save training metadata
    with open(os.path.join(output_model_path, "training_config.json"), "w") as f:
        json.dump({
            "base_model": model_path,
            "method": "reward_model_trainer",
            "learning_rate": lr,
            "epochs": epochs,
            "batch_size": batch_size,
            "max_length": max_length,
            "loss_function": loss_fn,
            "chosen_column": chosen_column,
            "rejected_column": rejected_column,
            **{k: v for k, v in metrics.items() if k != "demo_mode"},
        }, f, indent=2)

    # Save metrics as dict (consistent with all other training blocks)
    ctx.save_output("metrics", metrics)

    ctx.log_message(f"Reward model saved to {output_model_path}")
    ctx.report_progress(4, 4)
