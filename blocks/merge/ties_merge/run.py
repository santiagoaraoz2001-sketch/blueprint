"""TIES Merge — Trim, Elect Sign & Merge for model merging."""

import json
import os
import time
from pathlib import Path


def run(ctx):
    try:
        import yaml
        from mergekit.config import MergeConfiguration
        from mergekit.merge import MergeOptions, run_merge
    except ImportError as e:
        raise ImportError(
            f"Required library not installed: {e}. "
            f"Install with: pip install mergekit pyyaml"
        ) from e

    weight = float(ctx.config.get("weight", 1.0))
    density = float(ctx.config.get("density", 0.5))
    output_name = ctx.config.get("output_name", "ties-merged-model")

    # Auto-differentiate output name when using default
    if output_name == "ties-merged-model":
        output_name = f"ties-w{weight:.2f}-d{density:.2f}"

    model_a_name = _get_model_name(ctx, "model_a")
    model_b_name = _get_model_name(ctx, "model_b")
    base_name = _get_model_name(ctx, "base")

    model_a_name = model_a_name or ctx.config.get("model_a_name", "")
    model_b_name = model_b_name or ctx.config.get("model_b_name", "")

    if not model_a_name or not model_b_name:
        raise ValueError("Both model_a and model_b are required")

    # Fall back to model_a as base if base port not connected
    if not base_name:
        base_name = model_a_name
        ctx.log_message(
            "WARNING: No base model connected. Using Model A as base. "
            "For proper TIES merging, connect the pre-trained base model "
            "that Model A and Model B were fine-tuned from."
        )

    ctx.log_message(f"TIES Merge (Trim, Elect Sign & Merge)")
    ctx.log_message(f"  Model A: {model_a_name}")
    ctx.log_message(f"  Model B: {model_b_name}")
    ctx.log_message(f"  Base Model: {base_name}")
    ctx.log_message(f"  Weight: {weight}, Density: {density}")

    # Build TIES merge config
    config_dict = {
        "merge_method": "ties",
        "models": [
            {"model": model_a_name, "parameters": {"weight": 1 - weight, "density": density}},
            {"model": model_b_name, "parameters": {"weight": weight, "density": density}},
        ],
        "base_model": base_name,
        "dtype": "float16",
    }

    ctx.report_progress(1, 3)

    merge_config = MergeConfiguration.model_validate(config_dict)
    model_path = os.path.join(ctx.run_dir, "model")
    os.makedirs(model_path, exist_ok=True)

    ctx.log_message("Running TIES merge...")
    ctx.report_progress(2, 3)

    merge_start = time.time()
    run_merge(merge_config, out_path=model_path, options=MergeOptions(
        allow_crimes=False,
        lazy_unpickle=True,
    ))
    merge_time = time.time() - merge_start

    ctx.log_metric("merge_time_s", round(merge_time, 2))
    ctx.log_metric("density", density)
    if os.path.isdir(model_path):
        total = sum(f.stat().st_size for f in Path(model_path).rglob("*") if f.is_file())
        ctx.log_metric("output_size_mb", round(total / (1024 * 1024), 1))

    ctx.save_output("model", {
        "source": "merge",
        "method": "ties",
        "path": model_path,
        "model_name": output_name,
    })
    ctx.save_output("metrics", {
        "merge_method": "ties",
        "weight": weight,
        "density": density,
        "model_a": model_a_name,
        "model_b": model_b_name,
        "base_model": base_name,
    })
    ctx.log_message(f"TIES merge complete: {output_name}")
    ctx.report_progress(1, 1)


def _get_model_name(ctx, *input_ids):
    """Resolve a model name from input ports, trying each in order.

    For chained merges (merge→merge), prefers the local path since the
    upstream output is a local directory, not a HuggingFace repo ID.
    """
    for input_id in input_ids:
        if input_id is None:
            continue
        try:
            info = ctx.load_input(input_id)
            if isinstance(info, dict):
                if info.get("source") == "merge" and info.get("path"):
                    return info["path"]
                return info.get("model_name", info.get("model_id", info.get("path", "")))
            elif isinstance(info, str):
                return info
        except (ValueError, Exception):
            pass
    return ""
