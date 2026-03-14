"""LLM Inference — Universal inference block.

Auto-detects frameworks and models. Dispatches to Ollama, MLX, or
PyTorch/Transformers via shared _inference_utils.

Workflows:
  1. Auto-detect: picks best available framework for the given model
  2. Explicit framework: user selects ollama/mlx/pytorch
  3. RAG pipeline: context from upstream + prompt → LLM → response
  4. Agent config passthrough: outputs llm_config for downstream agent blocks
"""

import json
import os
import time

from blocks.inference._inference_utils import (
    build_config,
    call_inference,
    detect_best_framework,
)

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
    prompt_template = ctx.config.get("prompt_template", "{input}")
    user_input = ctx.config.get("user_input", "")
    system_prompt_cfg = ctx.config.get("system_prompt", "")

    # ── Model config from upstream (preferred) or fallback ─────────────
    model_data = {}
    if ctx.inputs.get("model"):
        model_data = ctx.load_input("model")
        if isinstance(model_data, dict):
            ctx.log_message(
                f"Using connected model: {model_data.get('model_name', 'unknown')} "
                f"via {model_data.get('source', 'unknown')}"
            )

    framework = model_data.get("source", model_data.get("backend", "auto")) if model_data else "auto"
    model = model_data.get("model_name", model_data.get("model_id", "")) if model_data else ""

    if not model:
        model = ctx.config.get("model_name", "")
    if not model:
        raise BlockConfigError(
            "model_name", "No model specified. Connect a Model Selector block or set model_name in config."
        )

    # ── Load inputs ────────────────────────────────────────────────────
    # Prompt input port takes priority over user_input config
    if ctx.inputs.get("prompt"):
        prompt_text = ctx.load_input("prompt")
        if isinstance(prompt_text, str) and os.path.isfile(prompt_text):
            with open(prompt_text, "r", encoding="utf-8", errors="ignore") as f:
                prompt_text = f.read()
        elif not isinstance(prompt_text, str):
            prompt_text = str(prompt_text)
        user_input = prompt_text

    # System prompt input port overrides config
    if ctx.inputs.get("system_prompt"):
        sp = ctx.load_input("system_prompt")
        if isinstance(sp, str):
            if os.path.isfile(sp):
                with open(sp, "r", encoding="utf-8", errors="ignore") as f:
                    system_prompt_cfg = f.read()
            else:
                system_prompt_cfg = sp

    # Context input
    context_text = ""
    if ctx.inputs.get("context"):
        context_data = ctx.load_input("context")
        if isinstance(context_data, str):
            if os.path.isfile(context_data):
                with open(context_data, "r", encoding="utf-8", errors="ignore") as f:
                    context_text = f.read()
            else:
                context_text = context_data
        elif isinstance(context_data, dict):
            context_text = json.dumps(context_data, indent=2)
        elif isinstance(context_data, list):
            context_text = "\n".join(str(item) for item in context_data)

    # ── Build prompt ───────────────────────────────────────────────────
    prompt = prompt_template.replace("{context}", context_text).replace("{input}", user_input)

    # ── Auto-detect framework ──────────────────────────────────────────
    if framework == "auto":
        framework = detect_best_framework(model)

    ctx.log_message(f"Framework: {framework} | Model: {model}")
    ctx.log_message(f"Prompt length: {len(prompt)} chars")

    # ── Build config with user overrides ───────────────────────────────
    overrides = {}
    # Pass endpoint from upstream model if available
    if model_data:
        endpoint = model_data.get("endpoint", model_data.get("base_url", ""))
        if endpoint:
            overrides["endpoint"] = endpoint
    for key in ["max_tokens", "temperature", "top_p", "repeat_penalty",
                 "stop_sequences", "frequency_penalty", "presence_penalty", "seed"]:
        val = ctx.config.get(key)
        if val is not None and val != "":
            overrides[key] = val
    inf_config = build_config(framework, overrides)

    # ── Run inference ──────────────────────────────────────────────────
    response_text, metadata = call_inference(
        framework=framework,
        model=model,
        prompt=prompt,
        system_prompt=system_prompt_cfg,
        config=inf_config,
        log_fn=ctx.log_message,
    )

    response_text = str(response_text) if response_text else ""

    # ── Output format ──────────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "text")
    if output_format == "json":
        from datetime import datetime

        output_obj = {
            "response": response_text,
            "model": model,
            "framework": framework,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        if metadata:
            output_obj["usage"] = {
                k: v for k, v in metadata.items()
                if k in ("prompt_tokens", "completion_tokens", "total_tokens")
            }
        response_text = json.dumps(output_obj, indent=2)

    # ── Save response ──────────────────────────────────────────────────
    ext = "json" if output_format == "json" else "txt"
    out_path = os.path.join(ctx.run_dir, f"response.{ext}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(response_text)
    ctx.save_output("response", out_path)

    # ── Save metadata ──────────────────────────────────────────────────
    metadata["response_length"] = len(response_text)
    metadata["prompt_length"] = len(prompt)
    ctx.save_output("metadata", metadata)

    # ── Save llm_config for downstream agent blocks ────────────────────
    ctx.save_output("llm_config", {
        "framework": framework,
        "model": model,
        "config": inf_config,
    })

    # ── Log metrics ────────────────────────────────────────────────────
    ctx.log_metric("inference/latency_ms", metadata.get("latency_ms", 0))
    ctx.log_metric("inference/tokens", metadata.get("total_tokens", 0))
    ctx.log_metric("response_length", len(response_text))
    ctx.log_message(f"Response: {len(response_text)} chars in {metadata.get('latency_ms', 0):.0f}ms")
    ctx.report_progress(1, 1)
