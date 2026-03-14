"""Summarization Eval — evaluate summarization quality.

Computes ROUGE-1/2/L F1 scores against reference summaries, plus
source-based metrics: compression ratio, extractive coverage,
and abstractive novelty. Works with any dataset containing
summary/reference/source columns.
"""

import json
import math
import os
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
    summary_col = ctx.config.get("summary_column", "summary")
    reference_col = ctx.config.get("reference_column", "reference")
    source_col = ctx.config.get("source_column", "source")
    metrics_str = ctx.config.get("metrics_to_compute",
                  "rouge1,rouge2,rougeL,compression,coverage,novelty")
    max_samples = int(ctx.config.get("max_samples", 0))

    # ── Output format config ───────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "json")
    decimal_precision = int(ctx.config.get("decimal_precision", 4))


    compute = set(m.strip() for m in metrics_str.split(",") if m.strip())

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

    ctx.log_message(f"Evaluating {len(rows)} summaries")

    # ── Evaluate each sample ──────────────────────────────────────────────
    all_scores = []
    detailed = []

    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue

        summary = str(row.get(summary_col, ""))
        reference = str(row.get(reference_col, ""))
        source = str(row.get(source_col, ""))

        scores = {}
        sum_tokens = _tokenize(summary)
        ref_tokens = _tokenize(reference)
        src_tokens = _tokenize(source)

        # ROUGE metrics (require reference)
        if reference and ref_tokens:
            if "rouge1" in compute:
                scores["rouge1"] = _rouge_n(sum_tokens, ref_tokens, 1)
            if "rouge2" in compute:
                scores["rouge2"] = _rouge_n(sum_tokens, ref_tokens, 2)
            if "rougeL" in compute:
                scores["rougeL"] = _rouge_l(sum_tokens, ref_tokens)

        # Source-based metrics
        if source and src_tokens and sum_tokens:
            if "compression" in compute:
                scores["compression_ratio"] = round(len(sum_tokens) / max(len(src_tokens), 1), 4)

            if "coverage" in compute:
                # Extractive coverage: fraction of summary tokens found in source
                src_set = set(t.lower() for t in src_tokens)
                covered = sum(1 for t in sum_tokens if t.lower() in src_set)
                scores["coverage"] = round(covered / max(len(sum_tokens), 1), 4)

            if "novelty" in compute:
                # Abstractive novelty: fraction of summary n-grams NOT in source
                sum_bigrams = set(_get_ngrams(sum_tokens, 2).keys())
                src_bigrams = set(_get_ngrams(src_tokens, 2).keys())
                if sum_bigrams:
                    novel = len(sum_bigrams - src_bigrams)
                    scores["novelty"] = round(novel / len(sum_bigrams), 4)
                else:
                    scores["novelty"] = 0.0

        all_scores.append(scores)
        detailed.append({
            "index": i,
            "summary_preview": summary[:200],
            "scores": {k: round(v, 4) for k, v in scores.items()},
        })
        ctx.report_progress(i + 1, len(rows))

    # ── Aggregate ─────────────────────────────────────────────────────────
    metric_keys = set()
    for s in all_scores:
        metric_keys.update(s.keys())

    metrics = {"total_samples": len(all_scores)}
    for key in sorted(metric_keys):
        values = [s[key] for s in all_scores if key in s]
        if values:
            metrics[f"avg_{key}"] = round(sum(values) / len(values), 4)

    ctx.log_message(f"\nSummarization Results:")
    for k, v in metrics.items():
        if isinstance(v, float):
            ctx.log_message(f"  {k}: {v:.4f}")

    # ── Save outputs ──────────────────────────────────────────────────────
    report_path = os.path.join(ctx.run_dir, "summarization_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"metrics": metrics, "detailed": detailed}, f, indent=2)
    ctx.save_artifact("summarization_report", report_path)


    # ── Save dataset output ────────────────────────────────────────────
    _ds_dir = os.path.join(ctx.run_dir, "dataset_out")
    os.makedirs(_ds_dir, exist_ok=True)
    for _r in scores:
        if isinstance(_r, dict):
            for _k, _v in _r.items():
                if isinstance(_v, float):
                    _r[_k] = round(_v, decimal_precision)
    if output_format == "csv" and scores:
        import csv as _csv
        with open(os.path.join(_ds_dir, "data.csv"), "w", newline="", encoding="utf-8") as _f:
            _w = _csv.DictWriter(_f, fieldnames=scores[0].keys())
            _w.writeheader()
            _w.writerows(scores)
    else:
        with open(os.path.join(_ds_dir, "data.json"), "w", encoding="utf-8") as _f:
            json.dump(scores, _f, indent=2)
    ctx.save_output("dataset", _ds_dir)

    ctx.save_output("metrics", metrics)
    ctx.save_output("report", report_path)
    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            ctx.log_metric(k, v)
    ctx.report_progress(1, 1)


# ── Tokenization ──────────────────────────────────────────────────────────

def _tokenize(text):
    """Simple whitespace tokenizer with lowercasing."""
    import re
    return re.findall(r'\b\w+\b', text.lower())


# ── ROUGE metrics ─────────────────────────────────────────────────────────

def _rouge_n(hypothesis, reference, n):
    """ROUGE-N F1 score."""
    hyp_ngrams = _get_ngrams(hypothesis, n)
    ref_ngrams = _get_ngrams(reference, n)

    if not hyp_ngrams or not ref_ngrams:
        return 0.0

    overlap = sum(min(hyp_ngrams[ng], ref_ngrams.get(ng, 0)) for ng in hyp_ngrams)
    precision = overlap / sum(hyp_ngrams.values())
    recall = overlap / sum(ref_ngrams.values())

    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def _rouge_l(hypothesis, reference):
    """ROUGE-L F1 score based on longest common subsequence."""
    if not hypothesis or not reference:
        return 0.0

    lcs_len = _lcs_length(hypothesis, reference)
    precision = lcs_len / len(hypothesis)
    recall = lcs_len / len(reference)

    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def _get_ngrams(tokens, n):
    """Return Counter of n-grams."""
    ngrams = Counter()
    for i in range(len(tokens) - n + 1):
        ngrams[tuple(tokens[i:i + n])] += 1
    return ngrams


def _lcs_length(a, b):
    """Length of longest common subsequence."""
    m, n = len(a), len(b)
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            curr[j] = prev[j - 1] + 1 if a[i - 1] == b[j - 1] else max(prev[j], curr[j - 1])
        prev = curr
    return prev[n]
