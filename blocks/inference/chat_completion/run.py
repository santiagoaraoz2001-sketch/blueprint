"""Chat Completion — multi-turn chat with conversation history support.

Workflows:
  1. Simple Q&A: user message -> chat completion -> response
  2. Multi-turn: history + message -> chat completion -> updated conversation
  3. Guided generation: system prompt + message -> chat completion -> constrained response
  4. Agent loop: history -> chat completion -> tool call -> append -> repeat
"""

import json
import os
import time

from blocks.inference._inference_utils import call_inference, build_config, detect_best_framework

try:
    from backend.block_sdk.exceptions import (
        BlockConfigError, BlockInputError, BlockDataError,
        BlockExecutionError,
    )
except ImportError:
    class BlockConfigError(ValueError):
        def __init__(self, field, message, **kw): super().__init__(message)
    class BlockInputError(ValueError):
        def __init__(self, message, **kw): super().__init__(message)
    class BlockDataError(ValueError):
        pass
    class BlockExecutionError(RuntimeError):
        def __init__(self, message, **kw): super().__init__(message)


def run(ctx):
    # ── Config ────────────────────────────────────────────────────────
    model_name = ctx.config.get("model_name", "")
    temperature = float(ctx.config.get("temperature", 0.7))
    max_tokens = int(ctx.config.get("max_tokens", 1024))
    system_prompt = ctx.config.get("system_prompt", "You are a helpful assistant.")
    backend = ctx.config.get("backend", "")

    # ── Load model from input port (overrides config) ─────────────────
    model_data = {}
    if ctx.inputs.get("model"):
        try:
            raw_model = ctx.load_input("model")
            if isinstance(raw_model, str) and os.path.isfile(raw_model):
                with open(raw_model, "r", encoding="utf-8") as f:
                    raw_model = json.load(f)
            if isinstance(raw_model, dict):
                model_data = raw_model
                model_name = model_name or model_data.get("model_name", model_data.get("model_id", ""))
                ctx.log_message(f"Using connected model: {model_data.get('model_name', model_name)}")
            elif isinstance(raw_model, str):
                model_name = model_name or raw_model
        except Exception as e:
            ctx.log_message(f"Warning: could not load model input: {e}")

    # Config conflict warning
    if ctx.inputs.get("model") and model_data and ctx.config.get("model_name"):
        ctx.log_message(
            f"\u26a0 Config conflict: upstream model='{model_data.get('model_name')}' "
            f"but local config has model_name='{ctx.config.get('model_name')}'. "
            f"Using upstream. Clear local config to remove this warning."
        )

    if not model_name:
        raise BlockConfigError(
            "model_name",
            "No model specified. Connect a Model Selector or set model_name in config.",
        )

    # ── Load user message ─────────────────────────────────────────────
    user_message = ""
    try:
        data = ctx.load_input("prompt")
        if isinstance(data, str):
            if os.path.isfile(data):
                with open(data, "r", encoding="utf-8") as f:
                    user_message = f.read()
            else:
                user_message = data
        elif isinstance(data, dict):
            user_message = data.get("text", data.get("prompt", json.dumps(data)))
    except (ValueError, Exception):
        pass

    if not user_message:
        raise BlockInputError(
            "No user message provided on 'prompt' input port",
            details="Connect a text source or enter a prompt",
            recoverable=False,
        )

    # ── Load system prompt from input port (overrides config) ─────────
    if ctx.inputs.get("system_prompt"):
        try:
            sys_data = ctx.load_input("system_prompt")
            if isinstance(sys_data, str):
                if os.path.isfile(sys_data):
                    with open(sys_data, "r", encoding="utf-8") as f:
                        system_prompt = f.read()
                else:
                    system_prompt = sys_data
        except (ValueError, Exception):
            pass

    # ── Load chat history ─────────────────────────────────────────────
    history = []
    if ctx.inputs.get("history"):
        try:
            hist_data = ctx.load_input("history")
            if isinstance(hist_data, list):
                history = hist_data
            elif isinstance(hist_data, str) and os.path.isfile(hist_data):
                hist_file = hist_data
                if os.path.isdir(hist_data):
                    hist_file = os.path.join(hist_data, "data.json")
                with open(hist_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    history = loaded if isinstance(loaded, list) else loaded.get("data", loaded.get("messages", []))
            elif isinstance(hist_data, dict):
                history = hist_data.get("data", hist_data.get("messages", []))
        except (ValueError, json.JSONDecodeError) as e:
            ctx.log_message(f"Warning: could not load chat history: {e}")
        except Exception as e:
            ctx.log_message(f"Warning: could not load chat history: {e}")

    # Validate history structure
    if history and not all(isinstance(m, dict) and "role" in m for m in history[:5]):
        ctx.log_message(
            "\u26a0 Chat history entries should be dicts with 'role' and 'content' keys. "
            "Proceeding without history."
        )
        history = []

    # ── Build prompt with history ─────────────────────────────────────
    if history:
        history_text = "\n".join(
            f"{msg.get('role', 'user')}: {msg.get('content', '')}"
            for msg in history
        )
        full_prompt = f"{history_text}\nuser: {user_message}"
    else:
        full_prompt = user_message

    # ── Detect framework and run inference ────────────────────────────
    framework = backend or detect_best_framework(model_name)
    inf_config = build_config(framework)
    inf_config["temperature"] = temperature
    inf_config["max_tokens"] = max_tokens

    ctx.log_message(f"Chat completion: model={model_name}, framework={framework}")
    ctx.report_progress(1, 3)

    start = time.time()
    try:
        response_text, metadata = call_inference(
            framework, model_name, full_prompt,
            system_prompt=system_prompt, config=inf_config,
        )
    except Exception as e:
        raise BlockExecutionError(
            f"Inference failed ({framework}/{model_name}): {e}",
            details=f"Check that the model '{model_name}' is available on the '{framework}' backend",
            recoverable=False,
        )
    latency = time.time() - start

    ctx.report_progress(2, 3)

    # ── Build conversation log ────────────────────────────────────────
    conversation = list(history)
    conversation.append({"role": "user", "content": user_message})
    conversation.append({"role": "assistant", "content": response_text})

    # ── Save outputs ──────────────────────────────────────────────────
    response_path = os.path.join(ctx.run_dir, "response.txt")
    with open(response_path, "w", encoding="utf-8") as f:
        f.write(response_text)
    ctx.save_output("response", response_path)

    log_path = os.path.join(ctx.run_dir, "conversation_log")
    os.makedirs(log_path, exist_ok=True)
    with open(os.path.join(log_path, "data.json"), "w", encoding="utf-8") as f:
        json.dump(conversation, f, indent=2, ensure_ascii=False)
    ctx.save_output("output_dataset", log_path)

    metadata["latency_ms"] = round(latency * 1000, 1)
    ctx.save_output("metadata", metadata)

    ctx.save_output("llm_config", {
        "framework": framework,
        "model": model_name,
        "config": inf_config,
    })

    # ── Metrics ───────────────────────────────────────────────────────
    ctx.log_metric("inference/latency_ms", metadata.get("latency_ms", 0))
    ctx.log_metric("inference/tokens", metadata.get("total_tokens", 0))
    ctx.log_metric("response_length", len(response_text))
    ctx.log_metric("history_turns", len(history))
    ctx.log_message(f"Response: {len(response_text)} chars, {len(conversation)} turns")
    ctx.report_progress(1, 1)
