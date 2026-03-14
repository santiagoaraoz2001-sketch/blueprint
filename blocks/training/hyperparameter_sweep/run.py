"""Hyperparameter Sweep — Grid/random search over hyperparameters.

When torch and transformers are installed, runs real training trials
using the HuggingFace Trainer.  Falls back to simulated sweeps otherwise.
"""

import json
import os
import time
import itertools
import random

from backend.block_sdk.exceptions import BlockTimeoutError


def run(ctx):
    dataset_path = ctx.load_input("dataset")

    # model input is optional
    model_name = "base_model"
    try:
        model_info = ctx.load_input("model")
        if isinstance(model_info, dict):
            model_name = model_info.get("model_name", model_info.get("model_id", model_info.get("path", "base_model")))
        elif isinstance(model_info, str):
            model_name = model_info
    except (ValueError, Exception):
        pass

    search_type = ctx.config.get("search_type", "grid")
    param_space_str = ctx.config.get("param_space", "{}")
    n_trials = int(ctx.config.get("n_trials", 10))
    optimize_metric = ctx.config.get("metric", "eval_loss")
    mode = ctx.config.get("mode", "min")

    ctx.log_message(f"Starting {search_type} sweep. Target metric: {optimize_metric} (mode={mode})")

    try:
        param_space = json.loads(param_space_str)
    except Exception:
        param_space = {"lr": [1e-4, 5e-5], "batch_size": [4, 8]}
        ctx.log_message("Failed to parse param_space JSON, using fallback: " + str(param_space))

    # ── Generate trial hyperparameter combinations ───────────────────────
    trials = _generate_trials(param_space, search_type, n_trials)
    if not trials:
        trials = [{"lr": 5e-5, "batch_size": 4}]

    ctx.log_message(f"Generated {len(trials)} trials for sweep.")

    # ── Try real training with transformers ───────────────────────────────
    try:
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            TrainingArguments,
            Trainer,
            TrainerCallback,
            DataCollatorForLanguageModeling,
        )
        from datasets import Dataset as HFDataset
        import torch

        ctx.log_message("torch + transformers found. Running real hyperparameter sweep.")
        ctx.log_metric("simulation_mode", 0.0)

        # ── Load training data ───────────────────────────────────────────
        texts = _load_texts(dataset_path)
        if not texts:
            raise RuntimeError("No training texts found in dataset")
        ctx.log_message(f"Loaded {len(texts)} training samples")

        # ── Run trials ───────────────────────────────────────────────────
        best_value = float("inf") if mode == "min" else float("-inf")
        best_trial = None
        best_trial_idx = -1
        best_output_dir = None

        for i, trial_params in enumerate(trials):
            ctx.log_message(f"--- Trial {i + 1}/{len(trials)}: {trial_params} ---")

            lr = float(trial_params.get("lr", trial_params.get("learning_rate", 5e-5)))
            batch_size = int(trial_params.get("batch_size", trial_params.get("per_device_train_batch_size", 4)))
            epochs = int(trial_params.get("epochs", trial_params.get("num_train_epochs", 1)))
            warmup_ratio = float(trial_params.get("warmup_ratio", 0.1))
            weight_decay = float(trial_params.get("weight_decay", 0.01))

            trial_dir = os.path.join(ctx.run_dir, f"trial_{i}")
            os.makedirs(trial_dir, exist_ok=True)

            # Load fresh model for each trial
            tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                device_map="auto" if torch.cuda.is_available() else None,
            )

            # Tokenize
            def tokenize_fn(examples):
                return tokenizer(
                    examples["text"],
                    truncation=True,
                    max_length=512,
                    padding="max_length",
                )

            dataset = HFDataset.from_dict({"text": texts})
            tokenized = dataset.map(tokenize_fn, batched=True, remove_columns=["text"])

            # Split into train/eval (90/10)
            split = tokenized.train_test_split(test_size=0.1, seed=42)
            train_dataset = split["train"]
            eval_dataset = split["test"]

            data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

            training_args = TrainingArguments(
                output_dir=trial_dir,
                num_train_epochs=epochs,
                per_device_train_batch_size=batch_size,
                learning_rate=lr,
                warmup_ratio=warmup_ratio,
                weight_decay=weight_decay,
                logging_steps=max(1, len(train_dataset) // (batch_size * 10)),
                save_strategy="no",
                eval_strategy="epoch",
                fp16=torch.cuda.is_available(),
                report_to="none",
                disable_tqdm=True,
            )

            # Callback to report metrics back to ctx
            trial_metrics = {}

            class TrialCallback(TrainerCallback):
                def on_log(self, args, state, control, logs=None, **kwargs):
                    if logs:
                        if "loss" in logs:
                            ctx.log_metric(f"trial_{i + 1}/loss", round(logs["loss"], 4), state.global_step)
                        if "eval_loss" in logs:
                            ctx.log_metric(f"trial_{i + 1}/eval_loss", round(logs["eval_loss"], 4), state.global_step)
                            trial_metrics["eval_loss"] = logs["eval_loss"]
                        if "eval_accuracy" in logs:
                            trial_metrics["eval_accuracy"] = logs["eval_accuracy"]

                def on_epoch_end(self, args, state, control, **kwargs):
                    ctx.report_progress(
                        i * epochs + int(state.epoch),
                        len(trials) * epochs,
                    )

            trainer = Trainer(
                model=model,
                args=training_args,
                train_dataset=train_dataset,
                eval_dataset=eval_dataset,
                data_collator=data_collator,
                callbacks=[TrialCallback()],
            )

            train_result = trainer.train()

            # Get final eval metrics
            eval_result = trainer.evaluate()
            trial_metric_val = eval_result.get(optimize_metric, eval_result.get(f"eval_{optimize_metric}"))
            if trial_metric_val is None:
                # Fall back to train loss
                trial_metric_val = train_result.metrics.get("train_loss", 0.0)

            ctx.log_message(f"Trial {i + 1} completed. {optimize_metric}: {trial_metric_val:.4f}")

            # Save trial model
            trainer.save_model(trial_dir)
            tokenizer.save_pretrained(trial_dir)

            is_better = (
                (mode == "min" and trial_metric_val < best_value)
                or (mode == "max" and trial_metric_val > best_value)
            )
            if is_better:
                best_value = trial_metric_val
                best_trial = trial_params
                best_trial_idx = i
                best_output_dir = trial_dir

            # Free GPU memory between trials
            del model, trainer
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        ctx.log_message(f"Sweep complete! Best trial: {best_trial_idx + 1} with {optimize_metric}: {best_value:.4f}")
        ctx.log_message(f"Best hyperparameters: {best_trial}")

        # Copy best model to output
        out_model_path = os.path.join(ctx.run_dir, "best_model")
        if best_output_dir and os.path.isdir(best_output_dir):
            import shutil
            if os.path.exists(out_model_path):
                shutil.rmtree(out_model_path)
            shutil.copytree(best_output_dir, out_model_path)
        else:
            os.makedirs(out_model_path, exist_ok=True)

        with open(os.path.join(out_model_path, "sweep_config.json"), "w") as f:
            json.dump({
                "base_model": model_name,
                "best_hyperparameters": best_trial,
                "best_metric": round(best_value, 4),
                "optimize_metric": optimize_metric,
                "mode": mode,
                "total_trials": len(trials),
                "demo_mode": False,
            }, f, indent=2)

        ctx.save_output("model", {
            "path": out_model_path,
            "model_name": model_name,
            "source": "hyperparameter_sweep",
            "demo_mode": False,
        })
        ctx.save_output("metrics", {
            "best_metric_value": round(best_value, 4),
            "best_trial_idx": best_trial_idx,
            "best_hyperparameters": best_trial,
            "optimize_metric": optimize_metric,
            "mode": mode,
            "total_trials": len(trials),
        })
        ctx.log_metric("best_metric_value", round(best_value, 4))
        ctx.report_progress(1, 1)
        return

    except ImportError:
        ctx.log_message(
            "⚠️ SIMULATION MODE: torch/transformers not installed. "
            "Training runs are simulated with synthetic loss curves. "
            "Install with: pip install torch transformers datasets"
        )
    except Exception as e:
        ctx.log_message(
            f"⚠️ SIMULATION MODE: Training failed ({e}). "
            "Falling back to simulated hyperparameter sweep."
        )

    # ── Simulation fallback ──────────────────────────────────────────────
    ctx.log_metric("simulation_mode", 1.0)

    best_value = float("inf") if mode == "min" else float("-inf")
    best_trial = None
    best_trial_idx = -1

    for i, trial_params in enumerate(trials):
        ctx.log_message(f"--- Trial {i + 1}/{len(trials)}: {trial_params} ---")

        # Simulate training for this trial
        trial_loss = 0.0
        steps = 5
        for s in range(steps):
            loss = 2.0 - (0.2 * s) + (random.random() * 0.1)
            # Add some penalty/bonus based on hyperparams for mock realism
            if "lr" in trial_params and isinstance(trial_params["lr"], (int, float)):
                lr_val = float(trial_params["lr"])
                loss += lr_val * 1000
            if "batch_size" in trial_params and isinstance(trial_params["batch_size"], (int, float)):
                bs = int(trial_params["batch_size"])
                loss -= bs * 0.01

            ctx.log_metric(f"trial_{i + 1}_loss", round(loss, 4), s)
            time.sleep(0.05)
            trial_loss = loss

        ctx.log_message(f"Trial {i + 1} completed. {optimize_metric}: {trial_loss:.4f}")
        ctx.report_progress(i + 1, len(trials))

        is_better = (
            (mode == "min" and trial_loss < best_value)
            or (mode == "max" and trial_loss > best_value)
        )
        if is_better:
            best_value = trial_loss
            best_trial = trial_params
            best_trial_idx = i

    ctx.log_message(f"Sweep complete! Best trial: {best_trial_idx + 1} with {optimize_metric}: {best_value:.4f}")
    ctx.log_message(f"Best hyperparameters: {best_trial}")

    out_model_path = os.path.join(ctx.run_dir, "best_model")
    os.makedirs(out_model_path, exist_ok=True)
    with open(os.path.join(out_model_path, "config.json"), "w") as f:
        json.dump({
            "base_model": model_name,
            "best_hyperparameters": best_trial,
            "best_metric": round(best_value, 4),
            "mode": mode,
            "demo_mode": True,
        }, f, indent=2)

    ctx.save_output("model", {
        "path": out_model_path,
        "model_name": model_name,
        "source": "hyperparameter_sweep",
        "demo_mode": True,
    })
    ctx.save_output("metrics", {
        "best_metric_value": round(best_value, 4),
        "best_trial_idx": best_trial_idx,
        "best_hyperparameters": best_trial,
        "optimize_metric": optimize_metric,
        "mode": mode,
        "total_trials": len(trials),
    })
    ctx.log_metric("best_metric_value", round(best_value, 4))
    ctx.report_progress(1, 1)


# ── Helpers ────────────────────────────────────────────────────────────────


def _generate_trials(param_space, search_type, n_trials):
    """Generate hyperparameter trial combinations."""
    trials = []
    if search_type == "grid":
        keys = list(param_space.keys())
        values = [v if isinstance(v, list) else [v] for v in param_space.values()]
        for combo in itertools.product(*values):
            trials.append(dict(zip(keys, combo)))
        if len(trials) > n_trials:
            trials = trials[:n_trials]
    else:
        keys = list(param_space.keys())
        for _ in range(n_trials):
            trial = {}
            for k in keys:
                v = param_space.get(k)
                if isinstance(v, list) and len(v) > 0:
                    trial[k] = random.choice(v)
                else:
                    trial[k] = v
            trials.append(trial)
    return trials


def _load_texts(dataset_path):
    """Load text data from a dataset path (directory or file)."""
    if not dataset_path:
        return []

    data_file = dataset_path
    if os.path.isdir(dataset_path):
        data_file = os.path.join(dataset_path, "data.json")
        if not os.path.isfile(data_file):
            return []

    if not os.path.isfile(data_file):
        return []

    with open(data_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        texts = []
        for item in data:
            if isinstance(item, dict):
                text = item.get("text", item.get("content", item.get("input", "")))
                if text:
                    texts.append(str(text))
            elif isinstance(item, str):
                texts.append(item)
        return texts
    return []
