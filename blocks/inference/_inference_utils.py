"""Shared inference utilities used by LLM Inference block and agent blocks.

Provides a single `call_inference()` entry point that dispatches to the
appropriate framework (Ollama, MLX, PyTorch/Transformers).
"""

import json
import os
import time


# ── Framework defaults ──────────────────────────────────────────────────

FRAMEWORK_DEFAULTS = {
    "ollama": {"max_tokens": 2048, "temperature": 0.7},
    "mlx": {"max_tokens": 100, "temperature": 0.0},
    "pytorch": {"max_tokens": 512, "temperature": 0.7},
}


def build_config(framework: str, overrides: dict | None = None) -> dict:
    """Merge framework defaults with user overrides. None values use default."""
    defaults = dict(FRAMEWORK_DEFAULTS.get(framework, {}))
    if overrides:
        for key in ["max_tokens", "temperature", "top_p", "repeat_penalty",
                     "stop_sequences", "frequency_penalty", "presence_penalty", "seed"]:
            val = overrides.get(key)
            if val is not None:
                defaults[key] = val
    return defaults


def detect_best_framework(model: str) -> str:
    """Pick the best framework for a given model name.

    Heuristic:
    - No slash in name (e.g. 'llama3.2') → try Ollama first
    - Has slash (e.g. 'mlx-community/Llama-3.2-3B') → check MLX then PyTorch
    """
    if not model or "/" not in model:
        # Check if Ollama is reachable
        try:
            import urllib.request
            req = urllib.request.Request(
                "http://localhost:11434/api/tags",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode())
                available = [m["name"] for m in data.get("models", [])]
                if not model or model in available or any(model in m for m in available):
                    return "ollama"
        except Exception:
            pass

    # Check MLX availability
    try:
        import mlx  # noqa: F401
        return "mlx"
    except ImportError:
        pass

    # Fallback to PyTorch
    try:
        import torch  # noqa: F401
        return "pytorch"
    except ImportError:
        pass

    return "ollama"  # default even if not reachable


def call_inference(
    framework: str,
    model: str,
    prompt: str,
    system_prompt: str = "",
    config: dict | None = None,
    log_fn=None,
) -> tuple[str, dict]:
    """Universal inference call. Returns (response_text, metadata_dict).

    Args:
        framework: One of 'ollama', 'mlx', 'pytorch'
        model: Model identifier
        prompt: The prompt text
        system_prompt: Optional system prompt (ignored by MLX)
        config: Override dict for max_tokens, temperature, etc.
        log_fn: Optional callable for logging messages
    """
    merged = build_config(framework, config)
    start_time = time.time()

    if framework == "ollama":
        response, meta = _run_ollama(model, prompt, system_prompt, merged, log_fn)
    elif framework == "mlx":
        response, meta = _run_mlx(model, prompt, merged, log_fn)
    elif framework == "pytorch":
        response, meta = _run_pytorch(model, prompt, system_prompt, merged, log_fn)
    else:
        raise ValueError(f"Unknown framework: {framework}")

    elapsed = time.time() - start_time
    meta["latency_ms"] = round(elapsed * 1000, 1)
    meta["framework"] = framework
    meta["model"] = model
    return response, meta


# ── Ollama ──────────────────────────────────────────────────────────────

def _run_ollama(model, prompt, system_prompt, config, log_fn=None):
    import urllib.request

    endpoint = config.get("endpoint", "http://localhost:11434")
    url = f"{endpoint.rstrip('/')}/api/generate"

    options = {
        "temperature": config.get("temperature", 0.7),
        "num_predict": config.get("max_tokens", 2048),
    }
    top_p = config.get("top_p")
    if top_p is not None and top_p < 1.0:
        options["top_p"] = top_p
    seed = config.get("seed")
    if seed is not None and seed >= 0:
        options["seed"] = seed
    stop = config.get("stop_sequences")
    if stop:
        if isinstance(stop, str):
            stop = [s.strip() for s in stop.split(",") if s.strip()]
        options["stop"] = stop
    freq_pen = config.get("frequency_penalty", 0.0)
    if freq_pen:
        options["frequency_penalty"] = freq_pen
    pres_pen = config.get("presence_penalty", 0.0)
    if pres_pen:
        options["presence_penalty"] = pres_pen
    repeat_penalty = config.get("repeat_penalty")
    if repeat_penalty is not None:
        options["repeat_penalty"] = repeat_penalty

    payload = {
        "model": model,
        "prompt": prompt,
        "options": options,
        "stream": False,
    }
    if system_prompt:
        payload["system"] = system_prompt

    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    if log_fn:
        log_fn(f"Calling Ollama at {url} model={model}")

    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode())
        token_usage = {
            "prompt_tokens": result.get("prompt_eval_count", 0),
            "completion_tokens": result.get("eval_count", 0),
            "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
        }
        return result.get("response", ""), token_usage


# ── MLX ─────────────────────────────────────────────────────────────────

def _run_mlx(model, prompt, config, log_fn=None):
    try:
        from mlx_lm import load, generate
    except ImportError:
        raise RuntimeError("mlx-lm not installed. Run: pip install mlx-lm")

    if log_fn:
        log_fn(f"Loading MLX model: {model}")

    loaded_model, tokenizer = load(model)

    if log_fn:
        log_fn("Generating response...")

    max_tokens = config.get("max_tokens", 100)
    temperature = config.get("temperature", 0.0)
    response = generate(loaded_model, tokenizer, prompt=prompt, max_tokens=max_tokens, temp=temperature)

    return response, {"total_tokens": 0}


# ── PyTorch / Transformers ──────────────────────────────────────────────

def _run_pytorch(model, prompt, system_prompt, config, log_fn=None):
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch
    except ImportError:
        raise RuntimeError("transformers/torch not installed. Run: pip install transformers torch")

    if log_fn:
        log_fn(f"Loading PyTorch model: {model}")

    tokenizer = AutoTokenizer.from_pretrained(model, trust_remote_code=True)
    loaded_model = AutoModelForCausalLM.from_pretrained(
        model, trust_remote_code=True, torch_dtype=torch.float16, device_map="auto",
    )

    # Build chat-template prompt if system_prompt provided
    if system_prompt and hasattr(tokenizer, "apply_chat_template"):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        full_prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    else:
        full_prompt = prompt

    if log_fn:
        log_fn("Generating response...")

    inputs = tokenizer(full_prompt, return_tensors="pt").to(loaded_model.device)
    max_tokens = config.get("max_tokens", 512)
    temperature = config.get("temperature", 0.7)

    gen_kwargs = {
        "max_new_tokens": max_tokens,
        "do_sample": temperature > 0,
    }
    if temperature > 0:
        gen_kwargs["temperature"] = temperature
        top_p = config.get("top_p")
        if top_p is not None:
            gen_kwargs["top_p"] = top_p

    with torch.no_grad():
        output_ids = loaded_model.generate(**inputs, **gen_kwargs)

    # Decode only the new tokens
    new_tokens = output_ids[0][inputs["input_ids"].shape[1]:]
    response = tokenizer.decode(new_tokens, skip_special_tokens=True)

    token_usage = {
        "prompt_tokens": inputs["input_ids"].shape[1],
        "completion_tokens": len(new_tokens),
        "total_tokens": inputs["input_ids"].shape[1] + len(new_tokens),
    }
    return response, token_usage
