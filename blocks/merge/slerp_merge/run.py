"""SLERP Merge — spherical linear interpolation merge of two models."""

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
    output_name = ctx.config.get("output_name", "slerp-merged-model")

    # Auto-differentiate output name when using default
    if output_name == "slerp-merged-model":
        output_name = f"slerp-w{weight:.2f}"

    model_a_name = _get_model_name(ctx, "model_a")
    model_b_name = _get_model_name(ctx, "model_b")
    model_a_name = model_a_name or ctx.config.get("model_a_name", "")
    model_b_name = model_b_name or ctx.config.get("model_b_name", "")

    if not model_a_name or not model_b_name:
        raise ValueError("Both model_a and model_b are required")

    ctx.log_message(f"SLERP Merge")
    ctx.log_message(f"  Model A: {model_a_name}")
    ctx.log_message(f"  Model B: {model_b_name}")
    ctx.log_message(f"  Weight (t): {weight}")

    # Build SLERP merge config — let mergekit auto-detect layer count
    config_dict = {
        "merge_method": "slerp",
        "slices": [{
            "sources": [
                {"model": model_a_name},
                {"model": model_b_name},
            ]
        }],
        "parameters": {"t": {"value": weight}},
        "dtype": "float16",
    }

    ctx.report_progress(1, 3)

    merge_config = MergeConfiguration.model_validate(config_dict)
    model_path = os.path.join(ctx.run_dir, "model")
    os.makedirs(model_path, exist_ok=True)

    ctx.log_message("Running SLERP merge...")
    ctx.report_progress(2, 3)

    run_merge(merge_config, out_path=model_path, options=MergeOptions(
        allow_crimes=False,
        lazy_unpickle=True,
    ))

    ctx.save_output("model", {
        "source": "merge",
        "method": "slerp",
        "path": model_path,
        "model_name": output_name,
        "model_a": model_a_name,
        "model_b": model_b_name,
        "weight": weight,
    })
    ctx.save_output("metrics", {
        "merge_method": "slerp",
        "weight": weight,
        "model_a": model_a_name,
        "model_b": model_b_name,
    })
    ctx.log_message(f"SLERP merge complete: {output_name}")
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
                # For upstream merge outputs, the local path is the actual model
                if info.get("source") == "merge" and info.get("path"):
                    return info["path"]
                return info.get("model_name", info.get("model_id", info.get("path", "")))
            elif isinstance(info, str):
                return info
        except (ValueError, Exception):
            pass
    return ""
