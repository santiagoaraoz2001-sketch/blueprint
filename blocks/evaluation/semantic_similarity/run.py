"""Semantic Similarity — compute embedding-based similarity between text pairs.

Uses sentence-transformers for embedding computation and cosine similarity.
Falls back to TF-IDF cosine similarity when sentence-transformers is not
available. Reports per-pair scores and aggregate statistics.
"""

import json
import math
import os
import re
from collections import Counter

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
    text_a_col = ctx.config.get("text_a_column", "text_a")
    text_b_col = ctx.config.get("text_b_column", "text_b")
    embed_model_name = ctx.config.get("embedding_model", "all-MiniLM-L6-v2")
    threshold = float(ctx.config.get("similarity_threshold", 0.8))
    batch_size = int(ctx.config.get("batch_size", 32))
    max_samples = int(ctx.config.get("max_samples", 0))

    # ── Output format config ───────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "json")
    decimal_precision = int(ctx.config.get("decimal_precision", 4))


    # ── Load dataset ──────────────────────────────────────────────────────
    dataset_path = ctx.load_input("dataset")
    data_file = (os.path.join(dataset_path, "data.json")
                 if os.path.isdir(dataset_path) else dataset_path)
    with open(data_file, "r", encoding="utf-8") as f:
        rows = json.load(f)

    if not isinstance(rows, list) or not rows:
        raise BlockDataError("Dataset must be a non-empty JSON list")

    if max_samples > 0:
        rows = rows[:max_samples]

    ctx.log_message(f"Computing semantic similarity for {len(rows)} pairs")

    # ── Initialize similarity function ────────────────────────────────────
    sim_fn = _init_similarity(ctx, embed_model_name, batch_size)

    # ── Compute similarity for each pair ──────────────────────────────────
    results = []
    above_threshold = 0

    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue

        text_a = str(row.get(text_a_col, ""))
        text_b = str(row.get(text_b_col, ""))

        if not text_a or not text_b:
            sim = 0.0
        else:
            sim = sim_fn(text_a, text_b)

        is_similar = sim >= threshold
        if is_similar:
            above_threshold += 1

        results.append({
            "index": i,
            "text_a": text_a[:200],
            "text_b": text_b[:200],
            "similarity": round(sim, 4),
            "is_similar": is_similar,
        })
        ctx.report_progress(i + 1, len(rows))

    # ── Aggregate metrics ─────────────────────────────────────────────────
    n = max(len(results), 1)
    sims = [r["similarity"] for r in results]

    metrics = {
        "total_pairs": len(results),
        "avg_similarity": round(sum(sims) / n, 4),
        "min_similarity": round(min(sims), 4) if sims else 0.0,
        "max_similarity": round(max(sims), 4) if sims else 0.0,
        "median_similarity": round(sorted(sims)[len(sims) // 2], 4) if sims else 0.0,
        "above_threshold": above_threshold,
        "above_threshold_rate": round(above_threshold / n, 4),
        "threshold": threshold,
    }

    # Standard deviation
    if len(sims) > 1:
        mean = sum(sims) / len(sims)
        variance = sum((s - mean) ** 2 for s in sims) / (len(sims) - 1)
        metrics["std_similarity"] = round(math.sqrt(variance), 4)

    ctx.log_message(f"\nSemantic Similarity Results:")
    ctx.log_message(f"  Avg: {metrics['avg_similarity']:.4f}")
    ctx.log_message(f"  Min: {metrics['min_similarity']:.4f}, Max: {metrics['max_similarity']:.4f}")
    ctx.log_message(f"  Above threshold ({threshold}): {above_threshold} ({metrics['above_threshold_rate']:.1%})")

    # ── Save outputs ──────────────────────────────────────────────────────
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    for _r in results:
        if isinstance(_r, dict):
            for _k, _v in _r.items():
                if isinstance(_v, float):
                    _r[_k] = round(_v, decimal_precision)
    if output_format == "csv" and results:
        import csv as _csv
        with open(os.path.join(out_dir, "data.csv"), "w", newline="", encoding="utf-8") as f:
            _w = _csv.DictWriter(f, fieldnames=results[0].keys())
            _w.writeheader()
            _w.writerows(results)
    else:
        with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)


    # ── Save report output ─────────────────────────────────────────────
    _outliers = sorted(results, key=lambda x: x.get("similarity", 0))[:10]
    _report = {"summary": metrics, "outlier_pairs": _outliers, "total_pairs": len(results)}
    _report_path = os.path.join(ctx.run_dir, "similarity_report.json")
    with open(_report_path, "w", encoding="utf-8") as f:
        json.dump(_report, f, indent=2)
    ctx.save_artifact("similarity_report", _report_path)
    ctx.save_output("report", _report_path)

    ctx.save_output("metrics", metrics)
    ctx.save_output("dataset", out_dir)
    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            ctx.log_metric(k, v)
    ctx.report_progress(1, 1)


def _init_similarity(ctx, model_name, batch_size):
    """Initialize similarity function: sentence-transformers or TF-IDF fallback."""
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np

        model = SentenceTransformer(model_name)
        ctx.log_message(f"Using sentence-transformers: {model_name}")

        def compute_similarity(text_a, text_b):
            embeddings = model.encode([text_a, text_b], batch_size=batch_size)
            cos = float(np.dot(embeddings[0], embeddings[1]) / (
                np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
            ))
            return max(0.0, min(1.0, cos))

        return compute_similarity

    except ImportError as e:
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"Required library not installed: {e}",
            install_hint="pip install numpy sentence-transformers",
        )


def _tokenize(text):
    """Simple tokenizer."""
    return re.findall(r'\b\w+\b', text.lower())
