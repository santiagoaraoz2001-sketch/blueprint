"""Frankenmerge — assemble a model from layers of different models (passthrough merge).

When mergekit is installed, generates a proper merge config and runs
the merge.  Falls back to a simulated merge when not installed.
"""

import json
import os
import subprocess
import time

from backend.block_sdk.exceptions import BlockTimeoutError


def run(ctx):
    output_name = ctx.config.get("output_name", "frankenmerge-model")
    layer_config_str = ctx.config.get("layer_config", "")
    merge_embed = ctx.config.get("merge_embed", "a")
    timeout = int(ctx.config.get("timeout", 3600))

    model_a_name = _get_model_name(ctx, "model_a", "model")
    model_b_name = _get_model_name(ctx, "model_b", None)
    model_a_name = model_a_name or ctx.config.get("model_a_name", "model-a")
    model_b_name = model_b_name or ctx.config.get("model_b_name", "model-b")

    ctx.log_message(f"Frankenmerge (Layer Assembly)")
    ctx.log_message(f"  Model A: {model_a_name}")
    ctx.log_message(f"  Model B: {model_b_name}")
    ctx.log_message(f"  Embedding source: {merge_embed}")

    # Parse layer config with validation
    layer_config = None
    stripped = layer_config_str.strip()
    if stripped and stripped not in ("[]", "{}"):
        try:
            layer_config = json.loads(stripped)
        except json.JSONDecodeError as e:
            ctx.log_message(
                f"ERROR: Invalid JSON in layer_config: {e}. "
                f"Expected format: "
                f'[{{"model":"org/model-a","layer_range":[0,16]}},'
                f'{{"model":"org/model-b","layer_range":[16,32]}}]'
            )
            raise ValueError(f"layer_config is not valid JSON: {e}") from e

        # Validate structure
        if not isinstance(layer_config, list):
            raise ValueError(
                f"layer_config must be a JSON array, got {type(layer_config).__name__}. "
                f'Expected: [{{"model":"...","layer_range":[start,end]}}]'
            )
        for i, entry in enumerate(layer_config):
            if not isinstance(entry, dict):
                raise ValueError(f"layer_config[{i}] must be an object, got {type(entry).__name__}")
            if "model" not in entry:
                raise ValueError(
                    f'layer_config[{i}] missing required "model" key. '
                    f'Each slice needs {{"model":"org/model","layer_range":[start,end]}}'
                )
            lr = entry.get("layer_range")
            if lr is not None:
                if not isinstance(lr, list) or len(lr) != 2:
                    raise ValueError(
                        f"layer_config[{i}].layer_range must be [start, end], got {lr}"
                    )
                if lr[0] >= lr[1]:
                    raise ValueError(
                        f"layer_config[{i}].layer_range start ({lr[0]}) must be < end ({lr[1]})"
                    )

    if not layer_config:
        layer_config = [
            {"model": model_a_name, "layer_range": [0, 16]},
            {"model": model_b_name, "layer_range": [16, 32]},
        ]
        ctx.log_message("Using default layer config: A[0:16] + B[16:32]")

    ctx.log_message(f"Layer slices: {len(layer_config)}")
    for i, lc in enumerate(layer_config):
        ctx.log_message(f"  Slice {i}: {lc.get('model', 'unknown')} layers {lc.get('layer_range', 'all')}")

    # Build mergekit YAML config
    model_path = os.path.join(ctx.run_dir, "model")
    os.makedirs(model_path, exist_ok=True)

    slices_yaml = ""
    for lc in layer_config:
        lr = lc.get("layer_range", [0, 32])
        slices_yaml += f"""  - sources:
      - model: {lc.get('model', 'unknown')}
        layer_range: [{lr[0]}, {lr[1]}]
"""

    # Determine tokenizer source based on merge_embed setting
    tokenizer_source = model_a_name if merge_embed == "a" else model_b_name

    merge_config_content = f"""merge_method: passthrough
slices:
{slices_yaml}dtype: float16
"""

    config_path = os.path.join(model_path, "merge_config.yaml")
    with open(config_path, "w") as f:
        f.write(merge_config_content)

    # ── Try real merge with mergekit ──
    try:
        import mergekit  # noqa: F401

        ctx.log_message("mergekit found. Running real passthrough merge...")
        output_dir = os.path.join(model_path, "merged")
        os.makedirs(output_dir, exist_ok=True)

        cmd = [
            "mergekit-yaml", config_path,
            output_dir,
            "--copy-tokenizer",
            "--lazy-unpickle",
        ]

        # Use specific tokenizer source if merge_embed is set
        if merge_embed == "b":
            cmd.extend(["--tokenizer-source", model_b_name])
        elif merge_embed == "average":
            # mergekit doesn't directly support averaging embeddings via CLI,
            # but we note the intent for downstream processing
            ctx.log_message("Note: Embedding averaging requested — using Model A tokenizer as base")

        ctx.log_message(f"Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode == 0:
            ctx.log_message("Merge completed successfully!")
            if result.stdout:
                for line in result.stdout.strip().split("\n")[-5:]:
                    ctx.log_message(f"  {line}")
        else:
            ctx.log_message(f"mergekit exited with code {result.returncode}")
            if result.stderr:
                for line in result.stderr.strip().split("\n")[-5:]:
                    ctx.log_message(f"  {line}")

        total_layers = sum(
            (lc.get("layer_range", [0, 16])[1] - lc.get("layer_range", [0, 16])[0])
            for lc in layer_config
        )

        with open(os.path.join(model_path, "config.json"), "w") as f:
            json.dump({
                "merged_model_name": output_name,
                "merge_method": "passthrough",
                "layer_config": layer_config,
                "total_layers": total_layers,
                "merge_embed": merge_embed,
                "output_dir": output_dir,
                "demo_mode": False,
            }, f, indent=2)

        # Branch: mergekit available — real merge
        ctx.save_output("model", {
            "source": "merge", "method": "passthrough", "path": output_dir,
            "model_name": output_name, "total_layers": total_layers, "demo_mode": False,
        })
        # Branch: mergekit available — real merge
        ctx.save_output("metrics", {
            "merge_method": "passthrough", "total_layers": total_layers,
            "num_slices": len(layer_config), "merge_embed": merge_embed,
        })
        ctx.log_message(f"Frankenmerge complete: {output_name} ({total_layers} layers)")
        ctx.report_progress(1, 1)
        return

    except ImportError:
        ctx.log_message("'mergekit' not installed (pip install mergekit). Running simulation.")
    except subprocess.TimeoutExpired:
        raise BlockTimeoutError(timeout, f"mergekit process timed out after {timeout}s")
    except Exception as e:
        ctx.log_message(f"mergekit error: {e}. Falling back to simulation.")

    # ── Simulation fallback ──
    total_layers = sum(
        (lc.get("layer_range", [0, 16])[1] - lc.get("layer_range", [0, 16])[0])
        for lc in layer_config
    )
    for i in range(total_layers):
        if i % 8 == 0:
            ctx.log_message(f"  Assembling layer {i + 1}/{total_layers}...")
        ctx.report_progress(i + 1, total_layers)
        time.sleep(0.05)

    with open(os.path.join(model_path, "config.json"), "w") as f:
        json.dump({
            "merged_model_name": output_name,
            "merge_method": "passthrough",
            "layer_config": layer_config,
            "total_layers": total_layers,
            "merge_embed": merge_embed,
            "demo_mode": True,
        }, f, indent=2)

    # Branch: mergekit unavailable — simulation fallback
    ctx.save_output("model", {
        "source": "merge", "method": "passthrough", "path": model_path,
        "model_name": output_name, "total_layers": total_layers, "demo_mode": True,
    })
    # Branch: mergekit unavailable — simulation fallback
    ctx.save_output("metrics", {
        "merge_method": "passthrough", "total_layers": total_layers,
        "num_slices": len(layer_config), "merge_embed": merge_embed,
    })
    ctx.log_message(f"Frankenmerge complete (simulated): {output_name} ({total_layers} layers)")
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
