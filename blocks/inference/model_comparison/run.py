"""Model Comparison — compare multiple models on the same prompts and rank by quality and speed.

Workflows:
  1. Model selection: compare 3 models -> pick best for your task
  2. Provider comparison: same model on ollama vs openai -> latency/quality
  3. Size comparison: 7B vs 13B vs 70B -> quality/speed tradeoff
  4. Cost analysis: local vs cloud -> compare latency and response quality
  5. Regression testing: old vs new model version -> check for regressions
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

    # ── Model config: upstream model input takes priority ──────────────
    model_data = {}
    if ctx.inputs.get("model"):
        model_data = ctx.load_input("model")
        if isinstance(model_data, dict):
            ctx.log_message(f"Using connected model: {model_data.get('model_name', 'unknown')}")

    models_text = ctx.config.get("models", "")
    endpoint = model_data.get("endpoint", model_data.get("base_url",
        ctx.config.get("endpoint", "http://localhost:11434")))
    api_key = model_data.get("api_key",
        ctx.config.get("api_key", ""))

    # Config conflict warnings
    if ctx.inputs.get("model") and ctx.config.get("models"):
        ctx.log_message(
            f"\u26a0 Config conflict: upstream model='{model_data.get('model_name')}' "
            f"but local config has models='{ctx.config.get('models')}'. "
            f"Using upstream. Clear local config to remove this warning."
        )

    temperature = float(ctx.config.get("temperature", 0.7))
    max_tokens = int(ctx.config.get("max_tokens", 256))
    prompts_text = ctx.config.get("prompts", "")
    text_column = _dataset_meta.get("text_column", ctx.config.get("text_column", "text"))

    # Parse model list
    model_configs = []
    for line in models_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            parts = line.split(":", 1)
            model_configs.append({"provider": parts[0].strip(), "model": parts[1].strip()})
        else:
            model_configs.append({"provider": "ollama", "model": line})

    if len(model_configs) < 2:
        raise ValueError("At least 2 models required for comparison. Format: provider:model_name per line.")

    # Build prompt list
    prompts = []
    if ctx.inputs.get("dataset"):
        data = ctx.load_input("dataset")
        rows = _load_dataset(data)
        for row in rows:
            if isinstance(row, dict):
                prompts.append(str(row.get(text_column, row.get("prompt", ""))))
            else:
                prompts.append(str(row))

    if not prompts and prompts_text:
        prompts = [p.strip() for p in prompts_text.strip().split("\n") if p.strip()]

    if not prompts:
        raise ValueError("No prompts provided. Connect a dataset or set prompts in config.")

    num_models = len(model_configs)
    ctx.log_message(f"Comparing {num_models} models on {len(prompts)} prompts")
    for i, mc in enumerate(model_configs):
        ctx.log_message(f"  Model {i+1}: {mc['provider']}:{mc['model']}")

    total_steps = len(prompts) * num_models
    step = 0
    ctx.report_progress(0, total_steps)

    # Run comparisons
    comparison_results = []
    # Track per-model totals
    model_latencies = {i: [] for i in range(num_models)}
    model_lengths = {i: [] for i in range(num_models)}
    model_errors = {i: 0 for i in range(num_models)}

    for pi, prompt in enumerate(prompts):
        row = {"prompt": prompt[:500]}

        for mi, mc in enumerate(model_configs):
            idx = mi + 1
            start = time.time()
            try:
                response = _call_llm(
                    mc["provider"], endpoint, api_key, mc["model"],
                    prompt, temperature, max_tokens,
                )
                latency = time.time() - start
                row[f"response_{idx}"] = response
                row[f"latency_{idx}"] = round(latency, 4)
                row[f"length_{idx}"] = len(response)
                model_latencies[mi].append(latency)
                model_lengths[mi].append(len(response))
            except Exception as e:
                latency = time.time() - start
                row[f"response_{idx}"] = ""
                row[f"latency_{idx}"] = round(latency, 4)
                row[f"length_{idx}"] = 0
                row[f"error_{idx}"] = str(e)
                model_errors[mi] += 1

            row[f"model_{idx}"] = mc["model"]
            row[f"provider_{idx}"] = mc["provider"]
            step += 1
            ctx.report_progress(step, total_steps)

        # Determine fastest and longest for this prompt
        valid_latencies = {}
        valid_lengths = {}
        for mi, mc in enumerate(model_configs):
            idx = mi + 1
            if f"error_{idx}" not in row:
                valid_latencies[mc["model"]] = row[f"latency_{idx}"]
                valid_lengths[mc["model"]] = row[f"length_{idx}"]

        if valid_latencies:
            row["fastest_model"] = min(valid_latencies, key=valid_latencies.get)
            row["longest_response_model"] = max(valid_lengths, key=valid_lengths.get)
        else:
            row["fastest_model"] = ""
            row["longest_response_model"] = ""

        comparison_results.append(row)
        ctx.log_message(f"  Prompt {pi+1}/{len(prompts)} complete")

    # Save dataset with format support
    dataset_format = ctx.config.get("dataset_format", "json")
    if dataset_format == "jsonl":
        out_path = os.path.join(ctx.run_dir, "results.jsonl")
        with open(out_path, "w", encoding="utf-8") as f:
            for row in comparison_results:
                f.write(json.dumps(row) + "\n")
    elif dataset_format == "csv":
        import csv as _csv
        out_path = os.path.join(ctx.run_dir, "results.csv")
        if comparison_results:
            keys = list(comparison_results[0].keys())
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = _csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(comparison_results)
        else:
            with open(out_path, "w") as f:
                f.write("")
    else:
        out_path = os.path.join(ctx.run_dir, "results.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(comparison_results, f, indent=2)
    ctx.save_output("dataset", out_path)

    # Build summary metrics
    metrics = {
        "num_prompts": len(comparison_results),
        "num_models": num_models,
        "models": [mc["model"] for mc in model_configs],
    }

    avg_latencies = {}
    for mi, mc in enumerate(model_configs):
        idx = mi + 1
        lats = model_latencies[mi]
        lens = model_lengths[mi]
        avg_lat = round(sum(lats) / max(len(lats), 1), 4) if lats else 0
        avg_len = round(sum(lens) / max(len(lens), 1), 1) if lens else 0
        metrics[f"avg_latency_{idx}"] = avg_lat
        metrics[f"avg_length_{idx}"] = avg_len
        metrics[f"total_latency_{idx}"] = round(sum(lats), 3)
        metrics[f"errors_{idx}"] = model_errors[mi]
        avg_latencies[mc["model"]] = avg_lat

    if avg_latencies:
        ranking = sorted(avg_latencies, key=avg_latencies.get)
        metrics["fastest_model"] = ranking[0]
        metrics["ranking_by_speed"] = ranking

    ctx.save_output("metrics", metrics)
    ctx.log_metric("num_models", num_models)
    ctx.log_metric("num_prompts", len(comparison_results))
    if avg_latencies:
        ctx.log_metric("fastest_model", metrics["fastest_model"])
    ctx.log_message(f"Comparison complete: {num_models} models, {len(comparison_results)} prompts")


def _load_dataset(data):
    if isinstance(data, list):
        return data
    if isinstance(data, str):
        path = os.path.join(data, "data.json") if os.path.isdir(data) else data
        if os.path.isfile(path):
            with open(path, "r") as f:
                return json.load(f)
    return []


def _call_llm(provider, endpoint, api_key, model, prompt, temperature, max_tokens):
    import urllib.request

    if provider == "ollama":
        url = f"{endpoint.rstrip('/')}/api/generate"
        payload = {
            "model": model, "prompt": prompt, "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
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
        body = {"model": model, "messages": messages,
                "temperature": temperature, "max_tokens": max_tokens}
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
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode())["content"][0]["text"]

    else:
        raise ValueError(f"Unknown provider: {provider}")
