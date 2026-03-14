"""W&B Logger — initialize a Weights & Biases run and pass through pipeline data."""

import json
import os
from datetime import datetime, timezone


def _resolve_input(raw):
    """Resolve an input value that might be a file path or directory to a Python object."""
    if raw is None:
        return None
    if isinstance(raw, str):
        if os.path.isfile(raw):
            with open(raw, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except (json.JSONDecodeError, ValueError):
                    return raw
        if os.path.isdir(raw):
            data_file = os.path.join(raw, "data.json")
            if os.path.isfile(data_file):
                with open(data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw
    return raw


def _extract_loggable_metrics(data):
    """Extract numeric key-value pairs from data for W&B logging.

    Walks one level of nesting so that {"eval": {"loss": 0.5}} produces
    {"eval.loss": 0.5}.
    """
    metrics = {}
    if not isinstance(data, dict):
        return metrics
    for key, value in data.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            metrics[key] = float(value)
        elif isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if isinstance(sub_value, (int, float)) and not isinstance(sub_value, bool):
                    metrics[f"{key}.{sub_key}"] = float(sub_value)
    return metrics


def run(ctx):
    # ---- Step 0: Import wandb ----
    ctx.report_progress(0, 5)
    try:
        import wandb
    except ImportError:
        from backend.block_sdk.exceptions import BlockDependencyError
        raise BlockDependencyError(
            "wandb",
            "Weights & Biases is not installed",
            install_hint="pip install wandb>=0.16.0",
        )

    # ---- Step 1: Read and validate config ----
    ctx.report_progress(1, 5)
    api_key = ctx.config.get("api_key", "").strip()
    project = ctx.config.get("project", "blueprint").strip()
    entity = ctx.config.get("entity", "").strip() or None
    run_name = ctx.config.get("run_name", "").strip() or None
    log_system_metrics = ctx.config.get("log_system_metrics", True)

    if not api_key:
        from backend.block_sdk.exceptions import BlockConfigError
        raise BlockConfigError(
            "api_key",
            "W&B API key is required. Set it directly or use $secret:wandb_api_key",
        )

    ctx.log_message(f"W&B Logger starting (project={project}, entity={entity or 'personal'})")

    # ---- Step 2: Authenticate ----
    ctx.report_progress(2, 5)
    try:
        wandb.login(key=api_key, relogin=True)
    except Exception as e:
        from backend.block_sdk.exceptions import BlockConfigError
        raise BlockConfigError(
            "api_key",
            f"W&B authentication failed: {e}",
            details="Verify your API key at https://wandb.ai/authorize",
        )

    # ---- Step 3: Initialize W&B run ----
    ctx.report_progress(3, 5)
    wandb_settings = wandb.Settings(
        _disable_stats=not log_system_metrics,
        console="off",
    )

    try:
        wb_run = wandb.init(
            project=project,
            entity=entity,
            name=run_name,
            config={"source": "blueprint", "pipeline": ctx.project_name or "unknown"},
            settings=wandb_settings,
        )
    except Exception as e:
        raise RuntimeError(
            f"Failed to initialize W&B run: {e}. "
            f"Check network connectivity and project permissions."
        )

    run_url = wb_run.url or ""
    ctx.log_message(f"W&B run initialized: {run_url}")

    # ---- Step 4: Load and pass through input data ----
    ctx.report_progress(4, 5)
    data = None
    try:
        raw_trigger = ctx.load_input("trigger")
        data = _resolve_input(raw_trigger)
        ctx.save_output("passthrough", raw_trigger)
        ctx.log_message("Trigger data received and passed through")
    except (ValueError, KeyError):
        ctx.log_message("No trigger input connected — pass-through skipped")

    # Log any numeric metrics found in the input data to W&B
    if data is not None:
        loggable = _extract_loggable_metrics(data)
        if loggable:
            wandb.log(loggable)
            ctx.log_message(f"Logged {len(loggable)} initial metric(s) to W&B")

    # ---- Step 5: Save outputs and artifact ----
    ctx.report_progress(5, 5)
    ctx.save_output("wandb_run_url", run_url)

    # Persist run status for auditability
    status_record = {
        "wandb_run_url": run_url,
        "wandb_run_id": wb_run.id,
        "wandb_run_name": wb_run.name,
        "project": project,
        "entity": entity,
        "log_system_metrics": log_system_metrics,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    status_path = os.path.join(ctx.run_dir, "wandb_run_status.json")
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(status_record, f, indent=2, ensure_ascii=False)

    ctx.save_artifact("wandb_run_status", status_path)
    ctx.log_metric("wandb_run_active", 1.0)

    ctx.log_message("W&B Logger complete — downstream blocks will log to the active run.")
