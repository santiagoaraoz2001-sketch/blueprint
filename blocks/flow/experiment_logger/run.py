"""Experiment Logger — log experiment results with metadata, timestamps, and run info."""

import json
import os
import platform
import sys
import time
from datetime import datetime, timezone


def _flatten_metrics(metrics):
    """Flatten a nested dict of metrics into dot-separated keys with numeric values."""
    flat = {}
    if not isinstance(metrics, dict):
        return flat
    for key, value in metrics.items():
        if isinstance(value, (int, float)):
            flat[key] = value
        elif isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if isinstance(sub_value, (int, float)):
                    flat[f"{key}.{sub_key}"] = sub_value
    return flat


def _try_mlflow_log(experiment_name, record, flat_metrics, ctx):
    """Attempt to log the experiment to MLflow if available."""
    try:
        import mlflow

        mlflow.set_experiment(experiment_name)
        with mlflow.start_run(run_name=record.get("run_id", "blueprint_run")):
            # Log parameters from config
            config = record.get("config", {})
            if isinstance(config, dict):
                for key, value in config.items():
                    try:
                        mlflow.log_param(key, value)
                    except Exception:
                        pass

            # Log metrics
            for key, value in flat_metrics.items():
                try:
                    mlflow.log_metric(key, value)
                except Exception:
                    pass

            # Log tags
            tags = record.get("tags", [])
            for tag in tags:
                try:
                    mlflow.set_tag(tag, "true")
                except Exception:
                    pass

        ctx.log_message("Experiment logged to MLflow successfully.")
        return True
    except ImportError:
        ctx.log_message("MLflow not installed. Skipping MLflow logging.")
        return False
    except Exception as e:
        ctx.log_message(f"MLflow logging failed: {e}")
        return False


def run(ctx):
    experiment_name = ctx.config.get("experiment_name", "default_experiment")
    tags_raw = ctx.config.get("tags", "")
    log_to_file = ctx.config.get("log_to_file", True)

    ctx.log_message(f"Experiment Logger starting: '{experiment_name}'")
    ctx.report_progress(0, 5)

    # Parse tags
    tags = []
    if tags_raw and isinstance(tags_raw, str):
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    elif isinstance(tags_raw, list):
        tags = tags_raw

    # ---- Step 1: Load metrics (required) ----
    ctx.report_progress(1, 5)
    raw_metrics = ctx.resolve_as_dict("metrics")
    if not raw_metrics:
        raise ValueError("No metrics provided. Connect a 'metrics' input to this block.")
    metrics = raw_metrics
    if not isinstance(metrics, dict):
        metrics = {"value": metrics}
    ctx.log_message(f"Loaded metrics with {len(metrics)} keys")

    # ---- Step 2: Load optional config input ----
    ctx.report_progress(2, 5)
    run_config = None
    if ctx.inputs.get("config"):
        raw_config = ctx.resolve_as_dict("config")
        run_config = raw_config
        if run_config is not None:
            ctx.log_message(f"Loaded experiment config input")
    if run_config is None:
        run_config = {}

    # ---- Step 3: Load optional model input ----
    ctx.report_progress(3, 5)
    model_info = None
    if ctx.inputs.get("model"):
        raw_model = ctx.resolve_model_info("model")
        model_info = raw_model
        if model_info is not None:
            ctx.log_message(f"Loaded model info input")
    if model_info is None:
        model_info = {}

    # ---- Step 4: Build experiment record ----
    ctx.report_progress(4, 5)
    now = datetime.now(timezone.utc)
    run_id = f"{experiment_name}_{now.strftime('%Y%m%d_%H%M%S')}"

    record = {
        "run_id": run_id,
        "experiment_name": experiment_name,
        "timestamp": now.isoformat(),
        "tags": tags,
        "metrics": metrics,
        "config": run_config,
        "model": model_info,
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "node": platform.node(),
        },
    }

    # Flatten metrics for logging
    flat_metrics = _flatten_metrics(metrics)
    for key, value in flat_metrics.items():
        ctx.log_metric(key, float(value))

    ctx.log_message(f"Experiment record built: run_id={run_id}, {len(flat_metrics)} numeric metrics")

    # ---- Step 5: Save to file and outputs ----
    ctx.report_progress(5, 5)

    out_path = os.path.join(ctx.run_dir, "experiment_log.json")
    if log_to_file:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, default=str, ensure_ascii=False)
        ctx.log_message(f"Experiment log written to {out_path}")
        ctx.save_artifact("experiment_log", out_path)

        # Also append to a cumulative experiments log if it exists
        cumulative_path = os.path.join(ctx.run_dir, "experiments_history.jsonl")
        with open(cumulative_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
        ctx.log_message(f"Appended to experiments history: {cumulative_path}")

    ctx.save_output("experiment_log", out_path)

    # Try MLflow integration
    _try_mlflow_log(experiment_name, record, flat_metrics, ctx)

    ctx.log_metric("num_metrics", float(len(flat_metrics)))
    ctx.log_metric("num_tags", float(len(tags)))
    ctx.log_message("Experiment logging complete.")
