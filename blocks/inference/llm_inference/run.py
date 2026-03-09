"""LLM Inference — send a prompt to a local or cloud LLM and get a response.

Workflows:
  1. Ollama local inference: user_input -> Ollama -> response
  2. MLX local inference (macOS): user_input -> MLX model -> response
  3. OpenAI cloud inference: user_input -> GPT-4o -> response
  4. Anthropic cloud inference: user_input -> Claude -> response
  5. RAG pipeline: context (from retriever) + user_input -> LLM -> response
  6. Model comparison: swap providers via config to compare outputs
  7. Connected model: upstream model block auto-sets provider/model
  8. Template-driven: prompt_template with {context}/{input} placeholders
"""

import json
import os
import time


def run(ctx):
    model_name = ctx.config.get("model_name", "")
    prompt_template = ctx.config.get("prompt_template", "{input}")
    user_input = ctx.config.get("user_input", "")
    provider = ctx.config.get("provider", "ollama")
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")
    api_key = ctx.config.get("api_key", "")
    temperature = float(ctx.config.get("temperature", 0.7))
    max_tokens = int(ctx.config.get("max_tokens", 512))
    system_prompt = ctx.config.get("system_prompt", "")
    top_p = float(ctx.config.get("top_p", 1.0))
    stop_seq_str = ctx.config.get("stop_sequences", "")
    stop_sequences = [s.strip() for s in stop_seq_str.split(",") if s.strip()] if stop_seq_str else None
    seed = int(ctx.config.get("seed", -1))
    seed = seed if seed >= 0 else None
    frequency_penalty = float(ctx.config.get("frequency_penalty", 0.0))
    presence_penalty = float(ctx.config.get("presence_penalty", 0.0))

    # Override from connected model input
    if ctx.inputs.get("model"):
        model_data = ctx.load_input("model")
        if isinstance(model_data, dict):
            model_name = model_data.get("model_name", model_data.get("model_id", model_name))
            provider = model_data.get("backend", model_data.get("provider", provider))
            endpoint = model_data.get("base_url", model_data.get("endpoint", endpoint))
            api_key = model_data.get("api_key", api_key)
            ctx.log_message(f"Using model from connected block: {model_name}")

    # Build prompt from template
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

    prompt = prompt_template.replace("{context}", context_text).replace("{input}", user_input)
    ctx.log_message(f"Provider: {provider} | Model: {model_name}")
    ctx.log_message(f"Prompt length: {len(prompt)} chars")

    start_time = time.time()
    response_text = ""
    token_usage = {}

    try:
        if provider == "ollama":
            response_text, token_usage = _call_ollama(endpoint, model_name, prompt, system_prompt, temperature, max_tokens, top_p, seed, stop_sequences, frequency_penalty, presence_penalty, ctx)
        elif provider == "mlx":
            response_text = _call_mlx(model_name, prompt, temperature, max_tokens, ctx)
        elif provider == "openai":
            response_text, token_usage = _call_openai(endpoint, api_key, model_name, prompt, system_prompt, temperature, max_tokens, top_p, seed, stop_sequences, frequency_penalty, presence_penalty, ctx)
        elif provider == "anthropic":
            response_text, token_usage = _call_anthropic(endpoint, api_key, model_name, prompt, system_prompt, temperature, max_tokens, top_p, stop_sequences, ctx)
        elif provider == "manual":
            response_text = f"[Manual mode] Prompt received ({len(prompt)} chars). No model configured."
            ctx.log_message("Manual mode — no inference performed")
        else:
            raise ValueError(f"Unknown provider: {provider}")
    except Exception as e:
        ctx.log_message(f"Inference error: {e}")
        raise

    elapsed = time.time() - start_time
    response_text = str(response_text) if response_text else ""

    # Apply output format
    output_format = ctx.config.get("output_format", "text")
    if output_format == "json":
        from datetime import datetime
        output_obj = {
            "response": response_text,
            "model": model_name,
            "provider": provider,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        if token_usage:
            output_obj["usage"] = token_usage
        response_text = json.dumps(output_obj, indent=2)

    # Save response
    ext = "json" if output_format == "json" else "txt"
    out_path = os.path.join(ctx.run_dir, f"response.{ext}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(response_text)
    ctx.save_output("response", out_path)

    # Build metrics
    metrics = {
        "latency_s": round(float(elapsed), 3),
        "response_length": len(response_text),
        "prompt_length": len(prompt),
        "model": model_name,
        "provider": provider,
    }
    metrics.update(token_usage)

    ctx.save_output("metrics", metrics)
    ctx.log_metric("latency_s", round(float(elapsed), 3))
    ctx.log_metric("response_length", len(response_text))
    if token_usage.get("total_tokens"):
        ctx.log_metric("total_tokens", token_usage["total_tokens"])
    ctx.log_message(f"Response: {len(response_text)} chars in {elapsed:.2f}s")
    ctx.report_progress(1, 1)


def _call_ollama(endpoint, model, prompt, system_prompt, temperature, max_tokens, top_p, seed, stop_sequences, frequency_penalty, presence_penalty, ctx):
    import urllib.request

    url = f"{endpoint.rstrip('/')}/api/generate"
    options = {"temperature": temperature, "num_predict": max_tokens}
    if top_p < 1.0:
        options["top_p"] = top_p
    if seed is not None:
        options["seed"] = seed
    if stop_sequences:
        options["stop"] = stop_sequences
    if frequency_penalty != 0:
        options["frequency_penalty"] = frequency_penalty
    if presence_penalty != 0:
        options["presence_penalty"] = presence_penalty
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
    ctx.log_message(f"Calling Ollama at {url}")

    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode())
        token_usage = {
            "prompt_tokens": result.get("prompt_eval_count", 0),
            "completion_tokens": result.get("eval_count", 0),
            "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
        }
        return result.get("response", ""), token_usage


def _call_mlx(model_name, prompt, temperature, max_tokens, ctx):
    try:
        from mlx_lm import load, generate
    except ImportError:
        raise RuntimeError("mlx-lm not installed. Run: pip install mlx-lm")

    ctx.log_message(f"Loading MLX model: {model_name}")
    model, tokenizer = load(model_name)
    ctx.log_message("Generating response...")
    response = generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens, temp=temperature)
    return response


def _call_openai(endpoint, api_key, model, prompt, system_prompt, temperature, max_tokens, top_p, seed, stop_sequences, frequency_penalty, presence_penalty, ctx):
    import urllib.request

    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OpenAI API key required. Set api_key config or OPENAI_API_KEY env var.")

    url = endpoint.rstrip("/")
    if "/v1/" not in url:
        url = f"{url}/v1/chat/completions"
    else:
        url = f"{url}/chat/completions" if not url.endswith("/chat/completions") else url

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if top_p < 1.0:
        body["top_p"] = top_p
    if seed is not None:
        body["seed"] = seed
    if stop_sequences:
        body["stop"] = stop_sequences
    if frequency_penalty != 0:
        body["frequency_penalty"] = frequency_penalty
    if presence_penalty != 0:
        body["presence_penalty"] = presence_penalty
    payload = json.dumps(body).encode()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(url, data=payload, headers=headers)
    ctx.log_message(f"Calling OpenAI API at {url}")

    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode())
        text = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})
        token_usage = {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }
        return text, token_usage


def _call_anthropic(endpoint, api_key, model, prompt, system_prompt, temperature, max_tokens, top_p, stop_sequences, ctx):
    import urllib.request

    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("Anthropic API key required. Set api_key config or ANTHROPIC_API_KEY env var.")

    url = endpoint.rstrip("/")
    if not url.endswith("/v1/messages"):
        url = f"{url}/v1/messages"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if top_p < 1.0:
        payload["top_p"] = top_p
    if stop_sequences:
        payload["stop_sequences"] = stop_sequences
    if system_prompt:
        payload["system"] = system_prompt

    data = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    req = urllib.request.Request(url, data=data, headers=headers)
    ctx.log_message(f"Calling Anthropic API at {url}")

    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode())
        text = result["content"][0]["text"]
        usage = result.get("usage", {})
        token_usage = {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        }
        return text, token_usage
