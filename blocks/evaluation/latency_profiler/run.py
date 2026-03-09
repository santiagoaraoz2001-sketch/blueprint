"""Latency Profiler — measure model inference latency and throughput.

Profiles inference performance across different batch sizes and input
lengths. Supports real profiling via Ollama and MLX, with simulated
fallback for demo purposes. Reports avg, min, max, P50, P95 latency
and throughput in items/second.
"""

import json
import os
import time
import random
import math


def run(ctx):
    # ── Configuration ─────────────────────────────────────────────────────
    model_name = ctx.config.get("model_name", "")
    provider = ctx.config.get("provider", "auto")
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")
    batch_sizes_str = ctx.config.get("batch_sizes", "1,2,4,8")
    input_lengths_str = ctx.config.get("input_lengths", "32,128,512")
    output_length = int(ctx.config.get("output_length", 64))
    num_warmup = int(ctx.config.get("num_warmup", 2))
    num_runs = int(ctx.config.get("num_runs", 5))
    temperature = float(ctx.config.get("temperature", 0.0))
    inference_timeout = int(ctx.config.get("inference_timeout", 120))

    # ── Output format config ───────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "json")
    decimal_precision = int(ctx.config.get("decimal_precision", 4))


    # ── Resolve model from input ──────────────────────────────────────────
    try:
        model_info = ctx.load_input("model")
        if isinstance(model_info, dict):
            model_name = model_name or model_info.get("model_name",
                         model_info.get("model_id", ""))
            if provider == "auto":
                provider = model_info.get("source", "ollama")
            endpoint = model_info.get("endpoint", endpoint)
        elif isinstance(model_info, str):
            model_name = model_name or model_info
    except (ValueError, Exception):
        pass

    batch_sizes = [int(b.strip()) for b in batch_sizes_str.split(",") if b.strip()]
    input_lengths = [int(l.strip()) for l in input_lengths_str.split(",") if l.strip()]

    ctx.log_message(f"Latency Profiler: {model_name or '(demo)'}")
    ctx.log_message(f"Provider: {provider}, Endpoint: {endpoint}")
    ctx.log_message(f"Batch sizes: {batch_sizes}, Input lengths: {input_lengths}")
    ctx.log_message(f"Output length: {output_length}, Warmup: {num_warmup}, Runs: {num_runs}")

    # ── Detect real inference capability ───────────────────────────────────
    infer_fn = _get_inference_fn(ctx, provider, model_name, endpoint, output_length,
                                temperature, inference_timeout)

    if infer_fn is None:
        ctx.log_message("No inference provider available — generating simulated profiles")

    # ── Profile each configuration ────────────────────────────────────────
    profiles = []
    total_configs = len(batch_sizes) * len(input_lengths)
    config_idx = 0

    for batch_size in batch_sizes:
        for input_length in input_lengths:
            config_idx += 1
            ctx.log_message(f"\nConfig {config_idx}/{total_configs}: batch={batch_size}, input_len={input_length}")

            sample_text = ("The quick brown fox jumps over the lazy dog. "
                          * max(1, input_length // 45))[:input_length]

            latencies = []
            for run_idx in range(num_warmup + num_runs):
                is_warmup = run_idx < num_warmup

                if infer_fn is not None:
                    start = time.perf_counter()
                    try:
                        infer_fn(sample_text)
                        elapsed = time.perf_counter() - start
                    except Exception as e:
                        elapsed = -1
                        ctx.log_message(f"  Error: {e}")
                else:
                    # Simulated latency
                    base = 0.05 + 0.001 * input_length + 0.02 * batch_size
                    elapsed = max(0.01, base + random.gauss(0, base * 0.1))
                    time.sleep(0.01)

                if not is_warmup and elapsed > 0:
                    latencies.append(elapsed)

            if latencies:
                latencies.sort()
                avg = sum(latencies) / len(latencies)
                p50 = latencies[len(latencies) // 2]
                p95_idx = min(int(len(latencies) * 0.95), len(latencies) - 1)
                p95 = latencies[p95_idx]
                throughput = batch_size / avg

                profile = {
                    "batch_size": batch_size,
                    "input_length": input_length,
                    "output_length": output_length,
                    "avg_latency_ms": round(avg * 1000, 2),
                    "min_latency_ms": round(latencies[0] * 1000, 2),
                    "max_latency_ms": round(latencies[-1] * 1000, 2),
                    "p50_ms": round(p50 * 1000, 2),
                    "p95_ms": round(p95 * 1000, 2),
                    "throughput_items_per_s": round(throughput, 2),
                    "num_runs": len(latencies),
                }
                profiles.append(profile)
                ctx.log_message(
                    f"  Avg: {avg*1000:.1f}ms, P50: {p50*1000:.1f}ms, "
                    f"P95: {p95*1000:.1f}ms, Throughput: {throughput:.1f} items/s"
                )

            ctx.report_progress(config_idx, total_configs)

    # ── Summary ───────────────────────────────────────────────────────────
    if profiles:
        best = min(profiles, key=lambda r: r["avg_latency_ms"])
        ctx.log_message(f"\nBest latency: {best['avg_latency_ms']}ms "
                       f"(batch={best['batch_size']}, len={best['input_length']})")

    # ── Build metrics ─────────────────────────────────────────────────────
    metrics = {
        "num_configs": len(profiles),
        "model": model_name,
        "provider": provider,
        "demo_mode": infer_fn is None,
    }
    if profiles:
        all_avgs = [p["avg_latency_ms"] for p in profiles]
        metrics["best_avg_latency_ms"] = min(all_avgs)
        metrics["worst_avg_latency_ms"] = max(all_avgs)
        metrics["best_throughput"] = max(p["throughput_items_per_s"] for p in profiles)

    # ── Save outputs ──────────────────────────────────────────────────────
    results_path = os.path.join(ctx.run_dir, "latency_profiles.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({"metrics": metrics, "profiles": profiles}, f, indent=2)
    ctx.save_artifact("latency_profiles", results_path)


    # ── Save dataset output (per-config timing table) ──────────────────
    if profiles:
        _ds_dir = os.path.join(ctx.run_dir, "dataset_out")
        os.makedirs(_ds_dir, exist_ok=True)
        _rows = []
        for _p in profiles:
            _row = dict(_p)
            for _k, _v in _row.items():
                if isinstance(_v, float):
                    _row[_k] = round(_v, decimal_precision)
            _rows.append(_row)
        if output_format == "csv" and _rows:
            import csv as _csv
            with open(os.path.join(_ds_dir, "data.csv"), "w", newline="", encoding="utf-8") as _f:
                _w = _csv.DictWriter(_f, fieldnames=_rows[0].keys())
                _w.writeheader()
                _w.writerows(_rows)
        else:
            with open(os.path.join(_ds_dir, "data.json"), "w", encoding="utf-8") as _f:
                json.dump(_rows, _f, indent=2)
        ctx.save_output("dataset", _ds_dir)

    ctx.save_output("metrics", metrics)
    ctx.save_output("results", results_path)
    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            ctx.log_metric(k, v)
    ctx.report_progress(1, 1)


def _get_inference_fn(ctx, provider, model_name, endpoint, output_length,
                      temperature=0.0, timeout=120):
    """Return an inference function or None if no provider is available."""
    if not model_name:
        return None

    if provider in ("ollama", "auto"):
        fn = _try_ollama(ctx, model_name, endpoint, output_length, temperature, timeout)
        if fn is not None:
            return fn

    if provider in ("mlx", "auto"):
        fn = _try_mlx(ctx, model_name, output_length, temperature)
        if fn is not None:
            return fn

    return None


def _try_ollama(ctx, model_name, endpoint, output_length, temperature=0.0, timeout=120):
    """Check Ollama availability and return inference function."""
    try:
        import urllib.request
        url = f"{endpoint.rstrip('/')}/api/tags"
        with urllib.request.urlopen(url, timeout=5):
            pass
    except Exception:
        return None

    ctx.log_message(f"Ollama connected: {model_name}")
    import urllib.request

    def infer(text):
        payload = json.dumps({
            "model": model_name, "prompt": text,
            "options": {"num_predict": output_length, "temperature": temperature},
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            f"{endpoint.rstrip('/')}/api/generate",
            data=payload, headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()

    return infer


def _try_mlx(ctx, model_name, output_length, temperature=0.0):
    """Check MLX availability and return inference function."""
    try:
        from mlx_lm import load, generate
        model, tokenizer = load(model_name)
        ctx.log_message(f"MLX loaded: {model_name}")

        def infer(text):
            generate(model, tokenizer, prompt=text, max_tokens=output_length, temp=temperature)

        return infer
    except (ImportError, Exception):
        return None
