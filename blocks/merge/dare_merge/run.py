"""DARE Merge — Drop And REscale merge of models via mergekit."""

import json
import os
import time
from pathlib import Path

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

try:
    from blocks.merge._merge_validation import _validate_model_for_merge, _load_model_info
except ImportError:
    def _validate_model_for_merge(name, info, ctx, label="model"):
        return name
    def _load_model_info(ctx, *ids):
        return {}


def run(ctx):
    try:
        import yaml
        from mergekit.config import MergeConfiguration
        from mergekit.merge import MergeOptions, run_merge
    except ImportError as e:
        raise BlockDependencyError(
            "mergekit",
            f"Required library not installed: {e}",
            install_hint="pip install mergekit pyyaml",
        ) from e

    weight = float(ctx.config.get("weight", 0.5))
    density = float(ctx.config.get("density", 0.5))
    rescale = ctx.config.get("rescale", True)
    output_name = ctx.config.get("output_name", "dare-merged-model")

    # Auto-differentiate output name when using default
    if output_name == "dare-merged-model":
        variant = "ties" if rescale else "linear"
        output_name = f"dare-{variant}-w{weight:.2f}-d{density:.2f}"

    # Load model references
    model_a_name = _get_model_name(ctx, "model_a")
    model_b_name = _get_model_name(ctx, "model_b")
    base_name = _get_model_name(ctx, "base")

    model_a_name = model_a_name or ctx.config.get("model_a_name", "")
    model_b_name = model_b_name or ctx.config.get("model_b_name", "")

    # Validate model identifiers are compatible with mergekit
    model_a_name = _validate_model_for_merge(model_a_name, _load_model_info(ctx, "model_a"), ctx, "Model A")
    model_b_name = _validate_model_for_merge(model_b_name, _load_model_info(ctx, "model_b"), ctx, "Model B")

    if not model_a_name or not model_b_name:
        raise BlockInputError("Both model_a and model_b are required", recoverable=False)

    # Fall back to model_a as base if base port not connected
    if not base_name:
        base_name = model_a_name
        ctx.log_message(
            "WARNING: No base model connected. Using Model A as base. "
            "For proper DARE merging, connect the pre-trained base model "
            "that Model A and Model B were fine-tuned from."
        )
    base_name = _validate_model_for_merge(base_name, _load_model_info(ctx, "base"), ctx, "Base Model")

    # Select merge method based on rescale setting
    merge_method = "dare_ties" if rescale else "dare_linear"

    ctx.log_message(f"DARE Merge (Drop And REscale)")
    ctx.log_message(f"  Model A: {model_a_name}")
    ctx.log_message(f"  Model B: {model_b_name}")
    ctx.log_message(f"  Base Model: {base_name}")
    ctx.log_message(f"  Weight: {weight}, Density: {density}, Rescale: {rescale}")
    ctx.log_message(f"  Method: {merge_method}")

    # Build DARE merge config
    config_dict = {
        "merge_method": merge_method,
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

    ctx.log_message("Running DARE merge...")
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
        "method": merge_method,
        "path": model_path,
        "model_name": output_name,
    })
    ctx.save_output("metrics", {
        "merge_method": merge_method,
        "weight": weight,
        "density": density,
        "rescale": rescale,
        "model_a": model_a_name,
        "model_b": model_b_name,
        "base_model": base_name,
    })
    ctx.log_message(f"DARE merge complete: {output_name}")
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
