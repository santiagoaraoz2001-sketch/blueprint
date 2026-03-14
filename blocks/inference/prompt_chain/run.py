"""Prompt Chain — sequential multi-step prompting pipeline.

Workflows:
  1. Analyze-then-summarize: text -> analysis -> summary
  2. Extract-then-format: document -> extract entities -> format output
  3. Translate-then-verify: text -> translate -> back-translate to verify
  4. Brainstorm-then-refine: topic -> ideas -> refined solution
  5. Multi-hop reasoning: question -> decompose -> solve each -> combine
  6. Review pipeline: draft -> review -> edit -> final version
"""

import json
import os
import time


def run(ctx):
    # ── Model config: upstream model input takes priority ──────────────
    model_data = {}
    if ctx.inputs.get("model"):
        model_data = ctx.load_input("model")
        if isinstance(model_data, dict):
            ctx.log_message(f"Using connected model: {model_data.get('model_name', 'unknown')}")

    provider = model_data.get("source", model_data.get("backend",
        ctx.config.get("backend", ctx.config.get("provider", "ollama"))))
    model_name = model_data.get("model_name", model_data.get("model_id",
        ctx.config.get("model_name", "")))
    endpoint = model_data.get("endpoint", model_data.get("base_url",
        ctx.config.get("endpoint", "http://localhost:11434")))
    api_key = model_data.get("api_key",
        ctx.config.get("api_key", ""))

    # Config conflict warnings
    if ctx.inputs.get("model") and ctx.config.get("model_name"):
        ctx.log_message(
            f"\u26a0 Config conflict: upstream model='{model_data.get('model_name')}' "
            f"but local config has model_name='{ctx.config.get('model_name')}'. "
            f"Using upstream. Clear local config to remove this warning."
        )

    if not model_name:
        raise ValueError("No model specified. Connect a Model Selector block or set model_name in config.")

    steps_json = ctx.config.get("steps", '["Analyze: {input}"]')
    pass_context = ctx.config.get("pass_context", True)
    if isinstance(pass_context, str):
        pass_context = pass_context.lower() in ("true", "1", "yes")
    temperature = float(ctx.config.get("temperature", 0.5))
    max_tokens = int(ctx.config.get("max_tokens", 512))
    system_prompt = ctx.config.get("system_prompt", "")
    stop_on_error = ctx.config.get("stop_on_error", True)
    if isinstance(stop_on_error, str):
        stop_on_error = stop_on_error.lower() in ("true", "1", "yes")
    frequency_penalty = float(ctx.config.get("frequency_penalty", 0.0))
    presence_penalty = float(ctx.config.get("presence_penalty", 0.0))

    # Parse steps
    try:
        steps = json.loads(steps_json)
        if not isinstance(steps, list):
            steps = [str(steps)]
    except (json.JSONDecodeError, ValueError):
        steps = [steps_json]

    if not steps:
        raise ValueError("No steps defined in the chain.")

    # Load initial input
    initial_input = ""
    if ctx.inputs.get("text"):
        data = ctx.load_input("text")
        if isinstance(data, str):
            if os.path.isfile(data):
                with open(data, "r", encoding="utf-8", errors="ignore") as f:
                    initial_input = f.read()
            else:
                initial_input = data

    ctx.log_message(f"Prompt chain: {len(steps)} steps via {provider}/{model_name}")
    ctx.report_progress(0, len(steps))

    intermediate_results = []
    current_output = initial_input
    total_tokens = 0

    for i, step_template in enumerate(steps):
        # Substitute placeholders
        prompt = step_template.replace("{input}", initial_input).replace("{previous}", current_output)

        ctx.log_message(f"Step {i+1}/{len(steps)}: {prompt[:80]}...")

        start_time = time.time()
        try:
            step_output, token_usage = _call_llm(provider, endpoint, api_key, model_name, prompt, system_prompt, temperature, max_tokens, frequency_penalty, presence_penalty)
        except Exception as e:
            if stop_on_error:
                raise RuntimeError(f"Chain stopped at step {i+1}: {e}")
            step_output = f"[Error: {e}]"
            token_usage = {}
            ctx.log_message(f"Step {i+1} error (continuing): {e}")
        elapsed = time.time() - start_time

        total_tokens += token_usage.get("total_tokens", 0)

        intermediate_results.append({
            "step": i + 1,
            "prompt": prompt[:500],
            "output": step_output,
            "latency_s": round(elapsed, 3),
            "tokens": token_usage.get("total_tokens", 0),
        })

        if pass_context:
            current_output = step_output

        ctx.report_progress(i + 1, len(steps))

    # Save final output
    out_path = os.path.join(ctx.run_dir, "final_output.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(current_output)
    ctx.save_output("response", out_path)

    # Save intermediate steps
    steps_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(steps_dir, exist_ok=True)
    with open(os.path.join(steps_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(intermediate_results, f, indent=2)
    ctx.save_output("steps", steps_dir)

    # Save metrics
    metrics = {
        "total_steps": len(steps),
        "total_tokens": total_tokens,
        "model": model_name,
        "provider": provider,
        "pass_context": pass_context,
        "final_output_length": len(current_output),
    }
    ctx.save_output("metrics", metrics)
    ctx.log_metric("total_steps", len(steps))
    ctx.log_metric("total_tokens", total_tokens)

    ctx.log_message(f"Chain complete: {len(steps)} steps, {total_tokens} total tokens")


def _call_llm(provider, endpoint, api_key, model, prompt, system_prompt, temperature, max_tokens, frequency_penalty, presence_penalty):
    import urllib.request

    if provider == "ollama":
        url = f"{endpoint.rstrip('/')}/api/generate"
        options = {"temperature": temperature, "num_predict": max_tokens}
        if frequency_penalty != 0:
            options["frequency_penalty"] = frequency_penalty
        if presence_penalty != 0:
            options["presence_penalty"] = presence_penalty
        payload = {
            "model": model, "prompt": prompt, "stream": False,
            "options": options,
        }
        if system_prompt:
            payload["system"] = system_prompt
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode())
            return result.get("response", ""), {
                "prompt_tokens": result.get("prompt_eval_count", 0),
                "completion_tokens": result.get("eval_count", 0),
                "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
            }

    elif provider == "mlx":
        try:
            from mlx_lm import load, generate
        except ImportError:
            raise RuntimeError("mlx-lm not installed.")
        model_obj, tokenizer = load(model)
        text = generate(model_obj, tokenizer, prompt=prompt, max_tokens=max_tokens, temp=temperature)
        return text, {}

    elif provider == "openai":
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OpenAI API key required.")
        url = endpoint.rstrip("/")
        if "/v1/" not in url:
            url = f"{url}/v1/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        body = {
            "model": model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
        }
        if frequency_penalty != 0:
            body["frequency_penalty"] = frequency_penalty
        if presence_penalty != 0:
            body["presence_penalty"] = presence_penalty
        payload = json.dumps(body).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode())
            usage = result.get("usage", {})
            return result["choices"][0]["message"]["content"], {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

    elif provider == "anthropic":
        if not api_key:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("Anthropic API key required.")
        url = endpoint.rstrip("/")
        if not url.endswith("/v1/messages"):
            url = f"{url}/v1/messages"
        body = {
            "model": model, "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature, "max_tokens": max_tokens,
        }
        if system_prompt:
            body["system"] = system_prompt
        payload = json.dumps(body).encode()
        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode())
            usage = result.get("usage", {})
            return result["content"][0]["text"], {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            }

    else:
        raise ValueError(f"Unknown provider: {provider}")
