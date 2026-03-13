"""A/B Test Inference — compare outputs from two model configurations.

Workflows:
  1. Model comparison: same prompt -> model A vs model B -> side-by-side results
  2. Temperature sweep: same model, different temps -> compare creativity vs accuracy
  3. Provider comparison: same model via different providers -> latency/quality comparison
  4. Prompt testing: dataset of prompts -> both models -> aggregate quality metrics
  5. Cost analysis: cloud vs local -> compare quality and cost
  6. Regression testing: old model vs new model -> check for regressions
"""

import json
import os
import time


def run(ctx):
    # Read upstream dataset metadata
    _dataset_meta = {}
    try:
        _meta_input = ctx.load_input("dataset_meta")
        if isinstance(_meta_input, dict):
            _dataset_meta = _meta_input
    except (ValueError, KeyError):
        pass

    provider_a = ctx.config.get("provider_a", "ollama")
    model_a = ctx.config.get("model_a", "llama3.2")
    provider_b = ctx.config.get("provider_b", "ollama")
    model_b = ctx.config.get("model_b", "mistral")
    endpoint_a = ctx.config.get("endpoint_a", "http://localhost:11434")
    endpoint_b = ctx.config.get("endpoint_b", "http://localhost:11434")
    api_key_a = ctx.config.get("api_key_a", "")
    api_key_b = ctx.config.get("api_key_b", "")
    temperature_a = float(ctx.config.get("temperature_a", 0.7))
    temperature_b = float(ctx.config.get("temperature_b", 0.7))
    max_tokens = int(ctx.config.get("max_tokens", 512))
    seed_a = int(ctx.config.get("seed_a", -1))
    seed_a = seed_a if seed_a >= 0 else None
    seed_b = int(ctx.config.get("seed_b", -1))
    seed_b = seed_b if seed_b >= 0 else None
    text_column = _dataset_meta.get("text_column", ctx.config.get("text_column", "text"))
    system_prompt = ctx.config.get("system_prompt", "")
    single_prompt = ctx.config.get("single_prompt", "")
    num_runs = int(ctx.config.get("num_runs", 1))

    ctx.report_progress(0, 3)

    # Build list of prompts
    prompts = []

    if ctx.inputs.get("dataset"):
        data = ctx.load_input("dataset")
        rows = _load_dataset(data)
        for row in rows:
            if isinstance(row, dict):
                prompts.append(str(row.get(text_column, row.get("prompt", ""))))
            else:
                prompts.append(str(row))

    if ctx.inputs.get("text"):
        text_data = ctx.load_input("text")
        if isinstance(text_data, str):
            if os.path.isfile(text_data):
                with open(text_data, "r", encoding="utf-8", errors="ignore") as f:
                    single_prompt = f.read()
            else:
                single_prompt = text_data

    if single_prompt and not prompts:
        prompts = [single_prompt]

    if not prompts:
        raise ValueError("No prompts provided. Connect a dataset or text input, or set single_prompt.")

    ctx.log_message(f"A/B test: {model_a} vs {model_b}, {len(prompts)} prompts")
    ctx.report_progress(1, 3)

    # Run both models on each prompt
    comparisons = []
    total_latency_a = 0
    total_latency_b = 0
    total_len_a = 0
    total_len_b = 0

    for i, prompt in enumerate(prompts):
        run_latencies_a = []
        run_latencies_b = []
        last_response_a = ""
        last_response_b = ""

        for run_idx in range(num_runs):
            start_a = time.time()
            try:
                last_response_a = _call_llm(provider_a, endpoint_a, api_key_a, model_a, prompt, system_prompt, temperature_a, max_tokens, seed=seed_a)
            except Exception as e:
                last_response_a = f"[Error: {e}]"
            run_latencies_a.append(time.time() - start_a)

            start_b = time.time()
            try:
                last_response_b = _call_llm(provider_b, endpoint_b, api_key_b, model_b, prompt, system_prompt, temperature_b, max_tokens, seed=seed_b)
            except Exception as e:
                last_response_b = f"[Error: {e}]"
            run_latencies_b.append(time.time() - start_b)

        mean_a = sum(run_latencies_a) / len(run_latencies_a)
        mean_b = sum(run_latencies_b) / len(run_latencies_b)

        comparison = {
            "prompt": prompt[:500],
            "response_a": last_response_a,
            "response_b": last_response_b,
            "model_a": model_a,
            "model_b": model_b,
            "latency_a": round(mean_a, 3),
            "latency_b": round(mean_b, 3),
            "length_a": len(last_response_a),
            "length_b": len(last_response_b),
        }
        if num_runs > 1:
            import statistics
            comparison["std_latency_a"] = round(statistics.stdev(run_latencies_a), 3) if len(run_latencies_a) > 1 else 0
            comparison["std_latency_b"] = round(statistics.stdev(run_latencies_b), 3) if len(run_latencies_b) > 1 else 0
            comparison["num_runs"] = num_runs
        comparisons.append(comparison)

        total_latency_a += mean_a
        total_latency_b += mean_b
        total_len_a += len(last_response_a)
        total_len_b += len(last_response_b)

        ctx.report_progress(i + 1, len(prompts))
        ctx.log_message(f"  Prompt {i+1}/{len(prompts)}: A={mean_a:.2f}s, B={mean_b:.2f}s")

    ctx.report_progress(2, 3)

    # Save comparisons with format support
    dataset_format = ctx.config.get("dataset_format", "json")
    if dataset_format == "jsonl":
        out_path = os.path.join(ctx.run_dir, "results.jsonl")
        with open(out_path, "w", encoding="utf-8") as f:
            for row in comparisons:
                f.write(json.dumps(row) + "\n")
    elif dataset_format == "csv":
        import csv as _csv
        out_path = os.path.join(ctx.run_dir, "results.csv")
        if comparisons:
            keys = list(comparisons[0].keys())
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = _csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(comparisons)
        else:
            with open(out_path, "w") as f:
                f.write("")
    else:
        out_path = os.path.join(ctx.run_dir, "results.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(comparisons, f, indent=2)
    ctx.save_output("dataset", out_path)

    n = len(comparisons)
    metrics = {
        "model_a": model_a,
        "model_b": model_b,
        "num_prompts": n,
        "avg_latency_a": round(total_latency_a / max(n, 1), 3),
        "avg_latency_b": round(total_latency_b / max(n, 1), 3),
        "avg_length_a": round(total_len_a / max(n, 1)),
        "avg_length_b": round(total_len_b / max(n, 1)),
        "total_latency_a": round(total_latency_a, 3),
        "total_latency_b": round(total_latency_b, 3),
    }
    ctx.save_output("metrics", metrics)
    ctx.log_metric("avg_latency_a", metrics["avg_latency_a"])
    ctx.log_metric("avg_latency_b", metrics["avg_latency_b"])

    ctx.log_message(f"A/B test complete: {n} comparisons")
    ctx.report_progress(3, 3)


def _load_dataset(data):
    if isinstance(data, list):
        return data
    if isinstance(data, str):
        path = os.path.join(data, "data.json") if os.path.isdir(data) else data
        if os.path.isfile(path):
            with open(path, "r") as f:
                return json.load(f)
    return []


def _call_llm(provider, endpoint, api_key, model, prompt, system_prompt, temperature, max_tokens, seed=None):
    import urllib.request

    if provider == "ollama":
        url = f"{endpoint.rstrip('/')}/api/generate"
        options = {"temperature": temperature, "num_predict": max_tokens}
        if seed is not None:
            options["seed"] = seed
        payload = {"model": model, "prompt": prompt, "stream": False,
                   "options": options}
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
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        body = {"model": model, "messages": messages,
                "temperature": temperature, "max_tokens": max_tokens}
        if seed is not None:
            body["seed"] = seed
        payload = json.dumps(body).encode()
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
