"""Synthetic Data Generator — generates a dataset using an LLM."""

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
    # Required inputs — prompt is optional with a default fallback
    try:
        prompt_input = ctx.resolve_as_text("prompt")
    except ValueError:
        prompt_input = ""
    model_ref = ctx.resolve_model_info("model")

    # Optional input
    try:
        seed_data_path = ctx.resolve_as_file_path("seed_data")
    except ValueError:
        seed_data_path = None

    # Config
    num_samples = int(ctx.config.get("num_samples", 1000))
    temperature = float(ctx.config.get("temperature", 0.8))
    diversity_penalty = float(ctx.config.get("diversity_penalty", 0.0))
    max_tokens = int(ctx.config.get("max_tokens", 256))
    batch_size = int(ctx.config.get("batch_size", 10))
    seed_mode = ctx.config.get("seed_mode", "none")
    output_format = ctx.config.get("output_format", "raw")
    system_prompt = ctx.config.get("system_prompt", "")
    vary_prompt = ctx.config.get("vary_prompt", False)
    output_column = ctx.config.get("output_column", "generated_text")

    if num_samples <= 0:
        raise BlockConfigError("num_samples", "num_samples must be greater than 0")

    # Load prompt template text
    if isinstance(prompt_input, str) and os.path.isfile(prompt_input):
        with open(prompt_input, "r", encoding="utf-8") as f:
            prompt_text = f.read()
    else:
        prompt_text = str(prompt_input) if prompt_input else "Generate a synthetic data example:"

    # Load seed data if provided and seed_mode is active
    seed_rows = []
    if seed_data_path and seed_mode != "none":
        data_file = os.path.join(seed_data_path, "data.json") if os.path.isdir(seed_data_path) else seed_data_path
        if os.path.isfile(data_file):
            with open(data_file, "r", encoding="utf-8") as f:
                seed_rows = json.load(f)
            ctx.log_message(f"Loaded {len(seed_rows)} seed examples (mode: {seed_mode})")

    # Build generation prompt incorporating seed data
    if seed_mode == "in_context" and seed_rows:
        # Prepend a few seed examples to the prompt
        examples = seed_rows[:5]
        example_text = "\n".join(json.dumps(ex) for ex in examples)
        prompt_text = f"Here are some examples:\n{example_text}\n\n{prompt_text}"
    elif seed_mode == "schema_only" and seed_rows:
        # Extract schema from seed data
        schema_cols = list(seed_rows[0].keys()) if seed_rows else []
        prompt_text = f"Generate data with these columns: {schema_cols}\n\n{prompt_text}"

    # Prepend system prompt if provided
    if system_prompt:
        prompt_text = f"{system_prompt}\n\n{prompt_text}"
        ctx.log_message(f"System prompt: {len(system_prompt)} chars")

    # Resolve model
    if isinstance(model_ref, dict):
        model_id = model_ref.get("model_id", model_ref.get("model_name", ""))
    else:
        model_id = str(model_ref) if model_ref else ""
    if not model_id:
        raise BlockInputError("No model specified. Connect a model input or set model_name in config.", recoverable=False)
    if os.path.isdir(model_id):
        # Local model path
        ctx.log_message(f"Using local model at: {model_id}")
    else:
        ctx.log_message(f"Using model: {model_id}")

    # Load model via transformers
    try:
        from transformers import pipeline as hf_pipeline
    except ImportError as e:
        from backend.block_sdk.exceptions import BlockDependencyError
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install transformers",
        )

    ctx.log_message(f"Loading pipeline for '{model_id}'...")
    generator = hf_pipeline("text-generation", model=model_id, device=-1)

    generated_data = []
    ctx.log_message(f"Generating {num_samples} samples (batch_size={batch_size}, temp={temperature})...")

    import random as _rng
    for i in range(0, num_samples, batch_size):
        current_batch = min(batch_size, num_samples - i)
        # Vary the prompt per batch by rotating seed examples
        batch_prompt = prompt_text
        if vary_prompt and seed_mode == "in_context" and seed_rows and len(seed_rows) > 5:
            sampled = _rng.sample(seed_rows, min(5, len(seed_rows)))
            example_text = "\n".join(json.dumps(ex) for ex in sampled)
            # Reconstruct prompt with rotated examples
            base_prompt = prompt_input if isinstance(prompt_input, str) and not os.path.isfile(prompt_input) else prompt_text.split("\n\n", 1)[-1] if "\n\n" in prompt_text else prompt_text
            batch_prompt = f"Here are some examples:\n{example_text}\n\n{base_prompt}"
            if system_prompt:
                batch_prompt = f"{system_prompt}\n\n{batch_prompt}"
        out = generator(
            batch_prompt,
            max_new_tokens=max_tokens,
            num_return_sequences=current_batch,
            temperature=max(temperature, 0.01),
            repetition_penalty=1.0 + diversity_penalty,
            truncation=True,
        )
        for j, result in enumerate(out):
            text = result["generated_text"].replace(batch_prompt, "").strip()
            entry = {"id": i + j, "source": "synthetic"}
            if output_format == "json":
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        entry.update(parsed)
                    else:
                        entry[output_column] = text
                        entry["_parse_error"] = "not a JSON object"
                except json.JSONDecodeError:
                    entry[output_column] = text
                    entry["_parse_error"] = "invalid JSON"
            else:
                entry[output_column] = text
            generated_data.append(entry)
        ctx.report_progress(min(i + current_batch, num_samples), num_samples)

    # Save dataset
    out_path = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "data.json"), "w", encoding="utf-8") as f:
        json.dump(generated_data, f)

    stats = {
        "total_generated": len(generated_data),
        "temperature": temperature,
        "diversity_penalty": diversity_penalty,
        "max_tokens": max_tokens,
        "seed_mode": seed_mode,
        "seed_examples_used": len(seed_rows) if seed_mode != "none" else 0,
    }

    ctx.save_output("dataset", out_path)
    ctx.save_output("metrics", stats)
    ctx.log_metric("synthetic_rows", len(generated_data))
    ctx.log_message(f"Generated {len(generated_data)} synthetic rows.")
