"""MergeKit Merge — merge two models using mergekit."""

import json
import os

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

    method = ctx.config.get("method", "slerp")
    weight = float(ctx.config.get("weight", 0.5))
    density = float(ctx.config.get("density", 0.5))
    output_name = ctx.config.get("output_name", "merged-model")

    # Auto-differentiate output name when using default
    if output_name == "merged-model":
        if method in ("ties", "dare_ties"):
            output_name = f"{method}-w{weight:.2f}-d{density:.2f}"
        else:
            output_name = f"{method}-w{weight:.2f}"

    # Get model paths/names
    model_a = _resolve_model(ctx, "model_a", ctx.config.get("model_a_name", ""))
    model_b = _resolve_model(ctx, "model_b", ctx.config.get("model_b_name", ""))
    base_model = _resolve_model(ctx, "base", "")

    if not model_a or not model_b:
        raise BlockInputError("Both model_a and model_b are required", recoverable=False)

    ctx.log_message(f"Merging models with method={method}")
    ctx.log_message(f"  Model A: {model_a}")
    ctx.log_message(f"  Model B: {model_b}")
    ctx.log_message(f"  Weight: {weight}")

    # Build merge config based on method
    if method in ("ties", "dare_ties"):
        # Use connected base model, fall back to model_a
        if not base_model:
            base_model = model_a
            ctx.log_message(
                "WARNING: No base model connected. Using Model A as base. "
                "For proper TIES/DARE merging, connect the pre-trained base model."
            )
        ctx.log_message(f"  Base Model: {base_model}")
        ctx.log_message(f"  Density: {density}")
        config_dict = {
            "merge_method": method,
            "models": [
                {"model": model_a, "parameters": {"weight": 1 - weight, "density": density}},
                {"model": model_b, "parameters": {"weight": weight, "density": density}},
            ],
            "base_model": base_model,
            "dtype": "float16",
        }
    elif method == "slerp":
        # Let mergekit auto-detect layer count — don't hardcode layer_range
        config_dict = {
            "merge_method": "slerp",
            "slices": [{
                "sources": [
                    {"model": model_a},
                    {"model": model_b},
                ]
            }],
            "parameters": {"t": {"value": weight}},
            "dtype": "float16",
        }
    else:  # linear, passthrough
        config_dict = {
            "merge_method": method,
            "models": [
                {"model": model_a, "parameters": {"weight": 1 - weight}},
                {"model": model_b, "parameters": {"weight": weight}},
            ],
            "dtype": "float16",
        }

    ctx.report_progress(1, 3)

    merge_config = MergeConfiguration.model_validate(config_dict)
    output_dir = os.path.join(ctx.run_dir, "model")
    os.makedirs(output_dir, exist_ok=True)

    ctx.log_message("Running merge...")
    ctx.report_progress(2, 3)

    run_merge(merge_config, out_path=output_dir, options=MergeOptions(
        allow_crimes=False,
        lazy_unpickle=True,
    ))

    ctx.log_metric("merge_method", method)
    ctx.log_message(f"Merge complete: {output_name}")
    ctx.save_output("model", {
        "source": "merge",
        "method": method,
        "path": output_dir,
        "model_name": output_name,
        "model_a": model_a,
        "model_b": model_b,
        "weight": weight,
    })
    ctx.save_output("metrics", {
        "merge_method": method,
        "weight": weight,
        "density": density,
        "model_a": model_a,
        "model_b": model_b,
    })
    ctx.report_progress(1, 1)


def _resolve_model(ctx, input_name, fallback_name):
    """Resolve a model reference from an input port or fall back to a config name.

    For chained merges (merge→merge), prefers the local path since the
    upstream output is a local directory, not a HuggingFace repo ID.
    """
    try:
        info = ctx.load_input(input_name)
        if isinstance(info, dict):
            if info.get("source") == "merge" and info.get("path"):
                return info["path"]
            return info.get("model_name", info.get("model_id", info.get("path", "")))
        elif isinstance(info, str):
            return info
    except (ValueError, Exception):
        pass
    return fallback_name
