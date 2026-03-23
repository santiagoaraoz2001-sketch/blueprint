"""W&B Logger — initialize a Weights & Biases run and pass through pipeline data.

This block authenticates with Weights & Biases, creates a new run, and leaves it
active so downstream blocks (e.g. training loops) can stream metrics to it via
the global ``wandb.log()`` API.  Trigger data is forwarded unchanged on the
passthrough output to allow inline placement in any pipeline.

Thread safety
-------------
wandb uses global process state for login credentials and the active run.
A module-level lock serializes the login → init sequence so concurrent
pipeline executions sharing the same server process cannot race.
"""

import json
import os
import threading
from datetime import datetime, timezone

# wandb uses global process state (active run, login credentials).
# Serialize the login → init sequence so concurrent pipeline executions
# sharing the same server process do not race each other.
_wandb_lock = threading.Lock()


def _resolve_input(raw):
    """Resolve an input value that might be a file path or directory to a Python object.

    Handles four cases in order:
    1. ``None`` → ``None``
    2. File path → JSON-parsed contents (fallback: raw string)
    3. Directory → ``data.json`` inside it
    4. JSON string → parsed object
    5. Anything else → returned as-is
    """
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
    """Extract numeric key-value pairs from *data* for W&B logging.

    Walks one level of nesting so that ``{"eval": {"loss": 0.5}}`` produces
    ``{"eval.loss": 0.5}``.  Booleans are excluded because ``bool`` is a
    subclass of ``int`` in Python and would silently coerce to ``0``/``1``.
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

    # ---- Step 2: Authenticate and initialize ----
    ctx.report_progress(2, 5)

    # Hold the lock for the entire login → init sequence.  wandb stores
    # credentials and the "current run" as module-level globals, so two
    # threads calling login()/init() concurrently can corrupt each other.
    with _wandb_lock:
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
            from backend.block_sdk.exceptions import BlockExecutionError
            raise BlockExecutionError(
                f"Failed to initialize W&B run: {e}",
                details="Check network connectivity and project permissions.",
            )

    # Validate that init actually returned a run object.  In rare edge
    # cases (e.g. disabled mode misconfiguration) wandb.init can return None.
    if wb_run is None:
        from backend.block_sdk.exceptions import BlockExecutionError
        raise BlockExecutionError(
            "wandb.init() returned None — run creation failed silently",
            details="This can happen in certain W&B modes. Check your wandb configuration.",
        )

    # Resolve run URL with backward compatibility for older wandb versions.
    try:
        run_url = wb_run.get_url()
    except AttributeError:
        run_url = getattr(wb_run, "url", "") or ""

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

    # Log any numeric metrics found in the input data to W&B.
    if data is not None:
        loggable = _extract_loggable_metrics(data)
        if loggable:
            try:
                wandb.log(loggable)
                ctx.log_message(f"Logged {len(loggable)} initial metric(s) to W&B")
            except Exception as e:
                # Network hiccup during logging should not kill the block;
                # the W&B run is still usable for downstream blocks.
                ctx.log_message(f"Warning: failed to log initial metrics to W&B: {e}")

    # ---- Step 5: Save outputs and artifact ----
    ctx.report_progress(5, 5)
    ctx.save_output("wandb_run_url", run_url)

    # Persist run metadata for auditability
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

    ctx.log_message("W&B Logger complete — downstream blocks can log to the active run.")
