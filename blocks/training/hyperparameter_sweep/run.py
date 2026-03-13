"""Hyperparameter Sweep — Grid/random search over hyperparameters."""

import json
import os
import time
import itertools
import random


def run(ctx):
    dataset_path = ctx.load_input("dataset")

    # model input is optional
    model_path = "base_model"
    try:
        model_info = ctx.load_input("model")
        if isinstance(model_info, dict):
            model_path = model_info.get("model_name", model_info.get("model_id", "base_model"))
        elif isinstance(model_info, str):
            model_path = model_info
    except (ValueError, Exception):
        pass

    search_type = ctx.config.get("search_type", "grid")
    param_space_str = ctx.config.get("param_space", "{}")
    n_trials = int(ctx.config.get("n_trials", 10))
    optimize_metric = ctx.config.get("metric", "eval/loss")
    mode = ctx.config.get("mode", "min")

    ctx.log_message(f"Starting {search_type} sweep. Target metric: {optimize_metric} (mode={mode})")

    try:
        param_space = json.loads(param_space_str)
    except Exception:
        param_space = {"lr": [1e-4, 5e-5], "batch_size": [4, 8]}
        ctx.log_message("Failed to parse param_space JSON, using fallback: " + str(param_space))

    # Generate trials
    trials = []
    if search_type == "grid":
        keys = list(param_space.keys())
        values = list(param_space.values())
        values = [v if isinstance(v, list) else [v] for v in values]
        combinations = list(itertools.product(*values))
        for combo in combinations:
            trials.append(dict(zip(keys, combo)))
        if len(trials) > n_trials:
            trials = trials[:n_trials]
    else:
        # Random search
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

    if not trials:
        trials = [{"dummy_param": "dummy_value"}]

    ctx.log_message(f"Generated {len(trials)} trials for sweep.")

    best_value = float('inf') if mode == "min" else float('-inf')
    best_trial = None
    best_trial_idx = -1

    for i, trial in enumerate(trials):
        ctx.log_message(f"--- Trial {i+1}/{len(trials)}: {trial} ---")

        # Simulate training for this trial
        trial_loss = 0.0
        steps = 5
        for s in range(steps):
            loss = 2.0 - (0.2 * s) + (random.random() * 0.1)
            # Add some penalty/bonus based on hyperparams for mock realism
            if "lr" in trial and isinstance(trial["lr"], (int, float)):
                lr_val = float(trial["lr"])
                loss += (lr_val * 1000)
            if "batch_size" in trial and isinstance(trial["batch_size"], (int, float)):
                bs = int(trial["batch_size"])
                loss -= (bs * 0.01)

            ctx.log_metric(f"trial_{i+1}_loss", round(loss, 4), s)
            time.sleep(0.1)
            trial_loss = loss

        ctx.log_message(f"Trial {i+1} completed. {optimize_metric}: {trial_loss:.4f}")
        ctx.report_progress(i + 1, len(trials))

        is_better = (mode == "min" and trial_loss < best_value) or (mode == "max" and trial_loss > best_value)
        if is_better:
            best_value = trial_loss
            best_trial = trial
            best_trial_idx = i

    ctx.log_message(f"Sweep complete! Best trial: {best_trial_idx+1} with {optimize_metric}: {best_value:.4f}")
    ctx.log_message(f"Best hyperparameters: {best_trial}")

    # Save the best model
    out_model_path = os.path.join(ctx.run_dir, "best_model")
    os.makedirs(out_model_path, exist_ok=True)
    with open(os.path.join(out_model_path, "config.json"), "w") as f:
        json.dump({
            "base_model": model_path,
            "best_hyperparameters": best_trial,
            "best_metric": round(best_value, 4),
            "mode": mode,
        }, f, indent=2)

    ctx.save_output("model", out_model_path)
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
