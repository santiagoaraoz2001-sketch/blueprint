"""Chat Completion — multi-turn chat with system/user/assistant messages.

Workflows:
  1. Simple chat: user_message -> LLM -> response
  2. Multi-turn: messages history input -> append user message -> LLM -> updated history
  3. RAG chat: context injected into system prompt -> chat -> response
  4. Agent loop: output messages fed back as input for next turn
  5. System prompt engineering: test different system prompts with same query
  6. Model A/B: compare chat behavior across providers
  7. Connected model: upstream model block auto-configures provider
"""

import json
import os


def run(ctx):
    provider = ctx.config.get("backend", "ollama")
    model_name = ctx.config.get("model_name", "llama3.2")
    system_prompt = ctx.config.get("system_prompt", "You are a helpful assistant.")
    user_message = ctx.config.get("user_message", "")
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")
    api_key = ctx.config.get("api_key", "")
    temperature = float(ctx.config.get("temperature", 0.7))
    max_tokens = int(ctx.config.get("max_tokens", 1024))
    top_p = float(ctx.config.get("top_p", 1.0))
    max_history_turns = int(ctx.config.get("max_history_turns", 0))
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

    ctx.report_progress(0, 3)

    # Build messages array
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # Load conversation history
    if ctx.inputs.get("messages"):
        history_data = ctx.load_input("messages")
        history = _load_messages(history_data)
        # Truncate history if max_history_turns is set
        if max_history_turns > 0 and len(history) > max_history_turns * 2:
            history = history[-(max_history_turns * 2):]
        messages.extend(history)

    # Add current user message from input port or config
    if ctx.inputs.get("text"):
        text_data = ctx.load_input("text")
        if isinstance(text_data, str):
            if os.path.isfile(text_data):
                with open(text_data, "r", encoding="utf-8", errors="ignore") as f:
                    user_message = f.read()
            else:
                user_message = text_data

    if user_message:
        messages.append({"role": "user", "content": user_message})

    if not any(m["role"] == "user" for m in messages):
        raise ValueError("No user message provided. Set user_message config or connect a text input.")

    ctx.log_message(f"Chat via {provider}/{model_name} — {len(messages)} messages")
    ctx.report_progress(1, 3)

    # Call LLM
    response_text = ""
    token_usage = {}

    if provider == "ollama":
        response_text, token_usage = _chat_ollama(endpoint, model_name, messages, temperature, max_tokens, top_p, frequency_penalty, presence_penalty, ctx)
    elif provider == "mlx":
        response_text = _chat_mlx(model_name, messages, temperature, max_tokens, ctx)
    elif provider == "openai":
        response_text, token_usage = _chat_openai(endpoint, api_key, model_name, messages, temperature, max_tokens, top_p, frequency_penalty, presence_penalty, ctx)
    elif provider == "anthropic":
        response_text, token_usage = _chat_anthropic(endpoint, api_key, model_name, messages, system_prompt, temperature, max_tokens, top_p, ctx)
    else:
        raise ValueError(f"Unknown provider: {provider}")

    ctx.report_progress(2, 3)

    # Apply output format
    output_format = ctx.config.get("output_format", "text")
    save_text = response_text
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
        save_text = json.dumps(output_obj, indent=2)

    # Save response text
    ext = "json" if output_format == "json" else "txt"
    out_path = os.path.join(ctx.run_dir, f"response.{ext}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(save_text)
    ctx.save_output("response", out_path)

    # Save full conversation (for chaining)
    messages.append({"role": "assistant", "content": response_text})
    conv_path = os.path.join(ctx.run_dir, "conversation.json")
    with open(conv_path, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2)
    ctx.save_output("messages", conv_path)

    # Save metrics
    metrics = {
        "model": model_name,
        "provider": provider,
        "message_count": len(messages),
        "response_length": len(response_text),
    }
    metrics.update(token_usage)
    ctx.save_output("metrics", metrics)

    ctx.log_message(f"Response: {len(response_text)} chars")
    if token_usage.get("total_tokens"):
        ctx.log_metric("total_tokens", token_usage["total_tokens"])
    ctx.report_progress(3, 3)


def _load_messages(data):
    """Parse message history from various input formats."""
    if isinstance(data, list):
        return [m for m in data if isinstance(m, dict) and "role" in m]
    if isinstance(data, str):
        if os.path.isfile(data):
            with open(data, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        else:
            content = data
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return [m for m in parsed if isinstance(m, dict) and "role" in m]
        except (json.JSONDecodeError, ValueError):
            return [{"role": "user", "content": content}]
    return []


def _chat_ollama(endpoint, model, messages, temperature, max_tokens, top_p, frequency_penalty, presence_penalty, ctx):
    import urllib.request

    url = f"{endpoint.rstrip('/')}/api/chat"
    options = {"temperature": temperature, "num_predict": max_tokens}
    if top_p < 1.0:
        options["top_p"] = top_p
    if frequency_penalty != 0:
        options["frequency_penalty"] = frequency_penalty
    if presence_penalty != 0:
        options["presence_penalty"] = presence_penalty
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "options": options,
        "stream": False,
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    ctx.log_message(f"Calling Ollama chat at {url}")

    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode())
        text = result.get("message", {}).get("content", "")
        token_usage = {
            "prompt_tokens": result.get("prompt_eval_count", 0),
            "completion_tokens": result.get("eval_count", 0),
            "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
        }
        return text, token_usage


def _chat_mlx(model_name, messages, temperature, max_tokens, ctx):
    try:
        from mlx_lm import load, generate
    except ImportError:
        raise RuntimeError("mlx-lm not installed. Run: pip install mlx-lm")

    ctx.log_message(f"Loading MLX model: {model_name}")
    model, tokenizer = load(model_name)

    if hasattr(tokenizer, "apply_chat_template"):
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    else:
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        prompt += "\nassistant:"

    return generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens, temp=temperature)


def _chat_openai(endpoint, api_key, model, messages, temperature, max_tokens, top_p, frequency_penalty, presence_penalty, ctx):
    import urllib.request

    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OpenAI API key required. Set api_key config or OPENAI_API_KEY env var.")

    url = endpoint.rstrip("/")
    if "/v1/" not in url:
        url = f"{url}/v1/chat/completions"

    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if top_p < 1.0:
        body["top_p"] = top_p
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
    ctx.log_message(f"Calling OpenAI at {url}")

    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode())
        text = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})
        return text, {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }


def _chat_anthropic(endpoint, api_key, model, messages, system_prompt, temperature, max_tokens, top_p, ctx):
    import urllib.request

    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("Anthropic API key required. Set api_key config or ANTHROPIC_API_KEY env var.")

    url = endpoint.rstrip("/")
    if not url.endswith("/v1/messages"):
        url = f"{url}/v1/messages"

    # Anthropic: system at top level, not in messages
    api_messages = [m for m in messages if m["role"] != "system"]
    payload = {
        "model": model,
        "messages": api_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if top_p < 1.0:
        payload["top_p"] = top_p
    if system_prompt:
        payload["system"] = system_prompt

    data = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    req = urllib.request.Request(url, data=data, headers=headers)
    ctx.log_message(f"Calling Anthropic at {url}")

    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode())
        text = result["content"][0]["text"]
        usage = result.get("usage", {})
        return text, {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        }
