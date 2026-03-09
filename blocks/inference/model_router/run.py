"""Model Router — route prompts to different models based on complexity/cost/latency.

Workflows:
  1. Cost optimization: simple prompts -> local model, complex -> cloud API
  2. Latency routing: short queries -> fast model, long -> thorough model
  3. Keyword routing: code questions -> code model, general -> chat model
  4. Fallback chain: try primary -> if error, use fallback
  5. Load balancing: distribute across models based on complexity
  6. Tiered inference: quick filter -> detailed analysis pipeline
"""

import json
import os
import time


def run(ctx):
    routing_strategy = ctx.config.get("routing_strategy", "complexity")
    primary_provider = ctx.config.get("primary_provider", "ollama")
    primary_model = ctx.config.get("primary_model", "llama3.2")
    primary_endpoint = ctx.config.get("primary_endpoint", "http://localhost:11434")
    fallback_provider = ctx.config.get("fallback_provider", "openai")
    fallback_model = ctx.config.get("fallback_model", "gpt-4o-mini")
    fallback_endpoint = ctx.config.get("fallback_endpoint", "https://api.openai.com")
    api_key = ctx.config.get("api_key", "")
    threshold = float(ctx.config.get("threshold", 0.5))
    keyword_triggers = ctx.config.get("keyword_triggers", "code,math,analyze,complex")
    prompt = ctx.config.get("prompt", "")
    temperature = float(ctx.config.get("temperature", 0.7))
    max_tokens = int(ctx.config.get("max_tokens", 512))
    max_retries = int(ctx.config.get("max_retries", 1))

    # Override primary from connected model input
    if ctx.inputs.get("model"):
        model_data = ctx.load_input("model")
        if isinstance(model_data, dict):
            primary_model = model_data.get("model_name", model_data.get("model_id", primary_model))
            primary_provider = model_data.get("backend", model_data.get("provider", primary_provider))
            primary_endpoint = model_data.get("base_url", model_data.get("endpoint", primary_endpoint))
            api_key = model_data.get("api_key", api_key)

    ctx.report_progress(0, 3)

    # Load prompt from input or config
    if ctx.inputs.get("text"):
        text_data = ctx.load_input("text")
        if isinstance(text_data, str):
            if os.path.isfile(text_data):
                with open(text_data, "r", encoding="utf-8", errors="ignore") as f:
                    prompt = f.read()
            else:
                prompt = text_data

    if not prompt:
        raise ValueError("No prompt provided.")

    # Compute routing decision
    word_count = len(prompt.split())
    complexity_score = 0.0

    if routing_strategy == "complexity":
        complexity_score = min(word_count / 200, 1.0)
        technical_words = ["explain", "analyze", "compare", "implement", "debug", "optimize", "algorithm"]
        tech_count = sum(1 for w in technical_words if w in prompt.lower())
        complexity_score = min(complexity_score + tech_count * 0.1, 1.0)
        use_fallback = complexity_score > threshold

    elif routing_strategy == "cost":
        complexity_score = min(word_count / 500, 1.0)
        use_fallback = complexity_score > threshold

    elif routing_strategy == "latency":
        complexity_score = 1.0 - min(word_count / 50, 1.0)
        use_fallback = False

    elif routing_strategy == "keyword":
        keywords = [k.strip().lower() for k in keyword_triggers.split(",") if k.strip()]
        prompt_lower = prompt.lower()
        matches = [k for k in keywords if k in prompt_lower]
        complexity_score = len(matches) / max(len(keywords), 1)
        use_fallback = len(matches) > 0
    else:
        use_fallback = False

    selected_provider = fallback_provider if use_fallback else primary_provider
    selected_model = fallback_model if use_fallback else primary_model
    selected_endpoint = fallback_endpoint if use_fallback else primary_endpoint

    ctx.log_message(f"Strategy: {routing_strategy}, score={complexity_score:.2f}, threshold={threshold}")
    ctx.log_message(f"Routed to: {selected_provider}/{selected_model}")
    ctx.report_progress(1, 3)

    # Call selected model
    start_time = time.time()
    response_text = ""

    last_error = None
    for attempt in range(max_retries):
        try:
            response_text = _call_llm(selected_provider, selected_endpoint, api_key, selected_model, prompt, "", temperature, max_tokens)
            last_error = None
            break
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                ctx.log_message(f"Primary attempt {attempt+1}/{max_retries} failed: {e}")

    if last_error is not None:
        if not use_fallback:
            ctx.log_message(f"Primary failed after {max_retries} retries: {last_error} — trying fallback")
            try:
                response_text = _call_llm(fallback_provider, fallback_endpoint, api_key, fallback_model, prompt, "", temperature, max_tokens)
                selected_provider = fallback_provider
                selected_model = fallback_model
                use_fallback = True
            except Exception as e2:
                raise RuntimeError(f"Both models failed. Primary: {last_error}, Fallback: {e2}")
        else:
            raise last_error

    elapsed = time.time() - start_time
    ctx.report_progress(2, 3)

    # Save response
    out_path = os.path.join(ctx.run_dir, "response.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(response_text)
    ctx.save_output("response", out_path)

    routing_decision = {
        "strategy": routing_strategy,
        "complexity_score": round(complexity_score, 4),
        "threshold": threshold,
        "selected_model": selected_model,
        "selected_provider": selected_provider,
        "used_fallback": use_fallback,
        "prompt_word_count": word_count,
    }
    ctx.save_output("routing", routing_decision)

    metrics = {**routing_decision, "latency_s": round(elapsed, 3), "response_length": len(response_text)}
    ctx.save_output("metrics", metrics)
    ctx.log_metric("latency_s", round(elapsed, 3))

    ctx.log_message(f"Response: {len(response_text)} chars in {elapsed:.2f}s")
    ctx.report_progress(3, 3)


def _call_llm(provider, endpoint, api_key, model, prompt, system_prompt, temperature, max_tokens):
    import urllib.request

    if provider == "ollama":
        url = f"{endpoint.rstrip('/')}/api/generate"
        payload = {"model": model, "prompt": prompt, "stream": False,
                   "options": {"temperature": temperature, "num_predict": max_tokens}}
        if system_prompt:
            payload["system"] = system_prompt
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode()).get("response", "")

    elif provider == "mlx":
        try:
            from mlx_lm import load, generate
        except ImportError:
            raise RuntimeError("mlx-lm not installed.")
        model_obj, tokenizer = load(model)
        return generate(model_obj, tokenizer, prompt=prompt, max_tokens=max_tokens, temp=temperature)

    elif provider == "openai":
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OpenAI API key required.")
        url = endpoint.rstrip("/")
        if "/v1/" not in url:
            url = f"{url}/v1/chat/completions"
        messages = [{"role": "user", "content": prompt}]
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})
        payload = json.dumps({"model": model, "messages": messages,
                              "temperature": temperature, "max_tokens": max_tokens}).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode())["choices"][0]["message"]["content"]

    elif provider == "anthropic":
        if not api_key:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("Anthropic API key required.")
        url = endpoint.rstrip("/")
        if not url.endswith("/v1/messages"):
            url = f"{url}/v1/messages"
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
                   "temperature": temperature, "max_tokens": max_tokens}
        if system_prompt:
            payload["system"] = system_prompt
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode())["content"][0]["text"]

    else:
        raise ValueError(f"Unknown provider: {provider}")
