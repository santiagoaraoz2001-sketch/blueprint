"""Model Benchmark — benchmark model performance with latency, throughput, and quality metrics.

Workflows:
  1. Model evaluation: model -> benchmark -> latency/throughput stats
  2. Provider comparison: benchmark same model on different providers
  3. Prompt stress test: dataset of prompts -> benchmark -> find slow queries
  4. Pre-deployment check: model -> benchmark -> verify latency SLAs
  5. Hardware comparison: same model on different hardware -> compare throughput
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
    temperature = float(ctx.config.get("temperature", 0.7))
    max_tokens = int(ctx.config.get("max_tokens", 256))
    prompts_text = ctx.config.get("prompts", "")
    text_column = _dataset_meta.get("text_column", ctx.config.get("text_column", "text"))
    warmup_runs = int(ctx.config.get("warmup_runs", 0))

    if not model_name:
        raise ValueError("model_name is required — set it in config or connect a model input.")

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
        raise ValueError("No prompts provided. Connect a dataset or set benchmark prompts.")

    ctx.log_message(f"Benchmarking: {model_name} ({provider}), {len(prompts)} prompts")
    ctx.report_progress(0, len(prompts) + warmup_runs)

    # Warmup runs
    if warmup_runs > 0:
        ctx.log_message(f"Running {warmup_runs} warmup request(s)...")
        for w in range(warmup_runs):
            try:
                _call_llm(provider, endpoint, api_key, model_name, prompts[0], temperature, max_tokens)
            except Exception:
                pass
            ctx.report_progress(w + 1, len(prompts) + warmup_runs)

    # Benchmark runs
    benchmark_results = []
    total_start = time.time()

    for i, prompt in enumerate(prompts):
        start = time.time()
        success = True
        error_msg = ""
        response = ""

        try:
            response = _call_llm(provider, endpoint, api_key, model_name, prompt, temperature, max_tokens)
        except Exception as e:
            success = False
            error_msg = str(e)
            response = ""

        latency = time.time() - start
        tokens_est = max(1, len(response) // 4)
        tps = tokens_est / max(latency, 0.001) if success else 0

        row = {
            "prompt": prompt[:500],
            "response": response,
            "latency_seconds": round(latency, 4),
            "tokens_generated": tokens_est,
            "tokens_per_second": round(tps, 2),
            "success": success,
        }
        if error_msg:
            row["error"] = error_msg

        benchmark_results.append(row)
        ctx.report_progress(warmup_runs + i + 1, len(prompts) + warmup_runs)
        ctx.log_message(f"  Prompt {i+1}/{len(prompts)}: {latency:.3f}s, {tps:.1f} tok/s")

    total_elapsed = time.time() - total_start

    # Save dataset output with format support
    dataset_format = ctx.config.get("dataset_format", "json")
    if dataset_format == "jsonl":
        out_path = os.path.join(ctx.run_dir, "results.jsonl")
        with open(out_path, "w", encoding="utf-8") as f:
            for row in benchmark_results:
                f.write(json.dumps(row) + "\n")
    elif dataset_format == "csv":
        import csv as _csv
        out_path = os.path.join(ctx.run_dir, "results.csv")
        if benchmark_results:
            keys = list(benchmark_results[0].keys())
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = _csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                writer.writerows(benchmark_results)
        else:
            with open(out_path, "w") as f:
                f.write("")
    else:
        out_path = os.path.join(ctx.run_dir, "results.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(benchmark_results, f, indent=2)
    ctx.save_output("dataset", out_path)

    # Compute summary metrics
    successful = [r for r in benchmark_results if r["success"]]
    failed = [r for r in benchmark_results if not r["success"]]
    latencies = sorted([r["latency_seconds"] for r in successful])

    metrics = {
        "model": model_name,
        "provider": provider,
        "total_prompts": len(benchmark_results),
        "successful": len(successful),
        "failed": len(failed),
        "total_elapsed_s": round(total_elapsed, 3),
    }

    if latencies:
        metrics["avg_latency_s"] = round(sum(latencies) / len(latencies), 4)
        metrics["min_latency_s"] = round(latencies[0], 4)
        metrics["max_latency_s"] = round(latencies[-1], 4)
        metrics["p50_latency_s"] = round(latencies[len(latencies) // 2], 4)
        p95_idx = min(int(len(latencies) * 0.95), len(latencies) - 1)
        metrics["p95_latency_s"] = round(latencies[p95_idx], 4)
        tps_values = [r["tokens_per_second"] for r in successful]
        metrics["avg_tokens_per_second"] = round(sum(tps_values) / len(tps_values), 2)
        resp_lengths = [len(r["response"]) for r in successful]
        metrics["avg_response_length"] = round(sum(resp_lengths) / len(resp_lengths), 1)
    else:
        metrics["avg_latency_s"] = 0
        metrics["min_latency_s"] = 0
        metrics["max_latency_s"] = 0
        metrics["p50_latency_s"] = 0
        metrics["p95_latency_s"] = 0
        metrics["avg_tokens_per_second"] = 0
        metrics["avg_response_length"] = 0

    ctx.save_output("metrics", metrics)
    ctx.log_metric("avg_latency_s", metrics["avg_latency_s"])
    ctx.log_metric("avg_tokens_per_second", metrics["avg_tokens_per_second"])
    ctx.log_metric("total_prompts", metrics["total_prompts"])
    ctx.log_message(
        f"Benchmark complete: {len(successful)}/{len(benchmark_results)} succeeded, "
        f"avg latency {metrics['avg_latency_s']}s"
    )


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
            raise RuntimeError("mlx-lm not installed. Run: pip install mlx-lm")
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
