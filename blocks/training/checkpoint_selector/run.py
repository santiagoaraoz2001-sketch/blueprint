"""Checkpoint Selector — scan a directory for training checkpoints and pick the best one."""

import json
import os
import re
import sys

# Import shared training utilities
_TRAINING_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TRAINING_PKG_DIR not in sys.path:
    sys.path.insert(0, _TRAINING_PKG_DIR)
try:
    from _training_utils import detect_training_framework
except ImportError:
    detect_training_framework = None

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
    checkpoint_dir = ctx.config.get("checkpoint_dir", "")
    metric_name = ctx.config.get("metric", "eval/loss")
    mode = ctx.config.get("mode", "min")  # "min" or "max"

    # Try to get checkpoint dir from input
    try:
        model_info = ctx.load_input("model")
        if isinstance(model_info, dict):
            checkpoint_dir = checkpoint_dir or model_info.get("path", "")
        elif isinstance(model_info, str):
            checkpoint_dir = checkpoint_dir or model_info
    except (ValueError, Exception):
        pass

    # Framework preference (for consistency; checkpoint selection does no training)
    _prefer = ctx.config.get("prefer_framework", "auto")

    ctx.log_message(f"Scanning for checkpoints in: {checkpoint_dir or '(not set)'}")
    ctx.log_message(f"Selection metric: {metric_name} (mode={mode})")

    checkpoints = []

    if checkpoint_dir and os.path.isdir(checkpoint_dir):
        # Scan for checkpoint directories (checkpoint-*)
        for entry in sorted(os.listdir(checkpoint_dir)):
            ckpt_path = os.path.join(checkpoint_dir, entry)
            if os.path.isdir(ckpt_path) and "checkpoint" in entry.lower():
                # Try to read trainer_state.json or metrics
                trainer_state = os.path.join(ckpt_path, "trainer_state.json")
                config_file = os.path.join(ckpt_path, "config.json")

                ckpt_info = {
                    "name": entry,
                    "path": ckpt_path,
                    "step": 0,
                    "metrics": {},
                }

                # Extract step number from name
                step_match = re.search(r"(\d+)", entry)
                if step_match:
                    ckpt_info["step"] = int(step_match.group(1))

                # Read metrics if available
                if os.path.isfile(trainer_state):
                    with open(trainer_state, "r") as f:
                        state = json.load(f)
                    if "log_history" in state:
                        for log_entry in reversed(state["log_history"]):
                            if metric_name in log_entry:
                                ckpt_info["metrics"] = log_entry
                                break
                elif os.path.isfile(config_file):
                    with open(config_file, "r") as f:
                        cfg = json.load(f)
                    ckpt_info["metrics"] = cfg

                checkpoints.append(ckpt_info)

        ctx.log_message(f"Found {len(checkpoints)} checkpoints")
        ctx.log_metric("simulation_mode", 0.0)
    else:
        # Demo mode: generate fake checkpoints
        ctx.log_message("⚠️ SIMULATION MODE: No valid checkpoint directory found. Generating sample checkpoints with synthetic metrics. Provide a valid checkpoint_dir for real checkpoint selection.")
        ctx.log_metric("simulation_mode", 1.0)
        import math
        import random
        random.seed(42)
        for step in [500, 1000, 1500, 2000, 2500, 3000]:
            loss = 2.5 * math.exp(-0.0005 * step) + random.gauss(0, 0.1) + 0.3
            checkpoints.append({
                "name": f"checkpoint-{step}",
                "path": f"/demo/checkpoints/checkpoint-{step}",
                "step": step,
                "metrics": {
                    "eval/loss": round(loss, 4),
                    "eval_accuracy": round(1.0 - loss / 3.0, 4),
                    "step": step,
                },
            })

    # Select best checkpoint
    best = None
    best_metric_val = None

    for ckpt in checkpoints:
        val = ckpt["metrics"].get(metric_name)
        if val is None:
            continue
        val = float(val)

        if best_metric_val is None:
            best = ckpt
            best_metric_val = val
        elif mode == "min" and val < best_metric_val:
            best = ckpt
            best_metric_val = val
        elif mode == "max" and val > best_metric_val:
            best = ckpt
            best_metric_val = val

    if best:
        ctx.log_message(f"Best checkpoint: {best['name']} ({metric_name}={best_metric_val})")
        # Branch: best checkpoint found by metric
        ctx.save_output("model", {"path": best["path"], "source": "checkpoint", **best})
    else:
        # Fall back to latest
        if checkpoints:
            best = max(checkpoints, key=lambda c: c["step"])
            ctx.log_message(f"No metric found. Selecting latest: {best['name']}")
            # Branch: checkpoints exist but no metric — use latest
            ctx.save_output("model", {"path": best["path"], "source": "checkpoint", **best})
        else:
            ctx.log_message("No checkpoints found.")
            # Branch: no checkpoints found
            ctx.save_output("model", {"path": "", "source": "checkpoint", "error": "no checkpoints found"})

    ctx.save_output("metrics", {
        "total_checkpoints": len(checkpoints),
        "best_checkpoint": best["name"] if best else "",
        "best_metric_value": best_metric_val,
        "all_checkpoints": [{"name": c["name"], "step": c["step"], metric_name: c["metrics"].get(metric_name)} for c in checkpoints],
    })
    ctx.log_metric("total_checkpoints", len(checkpoints))
    if best_metric_val is not None:
        ctx.log_metric(f"best_{metric_name}", best_metric_val)
    ctx.report_progress(1, 1)
