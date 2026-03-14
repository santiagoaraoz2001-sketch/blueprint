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

from blocks.inference._inference_utils import call_inference

try:
    from backend.block_sdk.exceptions import (
        BlockConfigError, BlockInputError, BlockDataError,
        BlockDependencyError, BlockExecutionError,
    )
except ImportError:
    class BlockConfigError(ValueError):
        def __init__(self, field, message, **kw): super().__init__(message)
    class BlockInputError(ValueError):
        def __init__(self, message, **kw): super().__init__(message)
    class BlockDataError(ValueError):
        pass
    class BlockDependencyError(ImportError):
        def __init__(self, dep, message="", **kw): super().__init__(message or dep)
    class BlockExecutionError(RuntimeError):
        def __init__(self, message, **kw): super().__init__(message)


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


    # ── Model config: upstream model input takes priority ────────────────
    model_data = {}
    if ctx.inputs.get("model"):
        model_data = ctx.load_input("model")
        if isinstance(model_data, dict):
            ctx.log_message(f"Using connected model: {model_data.get('model_name', 'unknown')}")

    framework = model_data.get("source", model_data.get("backend",
        ctx.config.get("provider", "ollama")))
    model_name = model_data.get("model_name", model_data.get("model_id",
        ctx.config.get("model_name", ""))) if not model_name else model_name
    config = {"endpoint": model_data.get("endpoint", model_data.get("base_url",
        ctx.config.get("endpoint", "http://localhost:11434")))}

    batch_sizes = [int(b.strip()) for b in batch_sizes_str.split(",") if b.strip()]
    input_lengths = [int(l.strip()) for l in input_lengths_str.split(",") if l.strip()]

    ctx.log_message(f"Latency Profiler: {model_name or '(demo)'}")
    ctx.log_message(f"Framework: {framework}, Endpoint: {config.get('endpoint')}")
    ctx.log_message(f"Batch sizes: {batch_sizes}, Input lengths: {input_lengths}")
    ctx.log_message(f"Output length: {output_length}, Warmup: {num_warmup}, Runs: {num_runs}")

    # ── Detect real inference capability ───────────────────────────────────
    infer_fn = _get_inference_fn(ctx, framework, model_name, config, output_length,
                                temperature)

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
        "provider": framework,
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


def _get_inference_fn(ctx, framework, model_name, config, output_length,
                      temperature=0.0):
    """Return an inference function using call_inference, or None if unavailable."""
    if not model_name:
        return None

    inf_config = dict(config)
    inf_config["max_tokens"] = output_length
    inf_config["temperature"] = temperature

    # Quick connectivity check for Ollama
    if framework == "ollama":
        try:
            import urllib.request
            endpoint = config.get("endpoint", "http://localhost:11434")
            url = f"{endpoint.rstrip('/')}/api/tags"
            with urllib.request.urlopen(url, timeout=5):
                pass
            ctx.log_message(f"Ollama connected: {model_name}")
        except Exception:
            ctx.log_message("Ollama not reachable")
            return None

    def infer(text):
        call_inference(framework, model_name, text, config=inf_config,
                       log_fn=ctx.log_message)

    return infer
