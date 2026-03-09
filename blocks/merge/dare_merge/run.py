"""DARE Merge — Drop And REscale merge of models via mergekit."""

import json
import os


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

    if not model_a_name or not model_b_name:
        raise ValueError("Both model_a and model_b are required")

    # Fall back to model_a as base if base port not connected
    if not base_name:
        base_name = model_a_name
        ctx.log_message(
            "WARNING: No base model connected. Using Model A as base. "
            "For proper DARE merging, connect the pre-trained base model "
            "that Model A and Model B were fine-tuned from."
        )

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

    run_merge(merge_config, out_path=model_path, options=MergeOptions(
        allow_crimes=False,
        lazy_unpickle=True,
    ))

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
