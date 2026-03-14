"""Coherence Eval — evaluate text quality, fluency, and readability.

Computes heuristic quality metrics: readability (Flesch-Kincaid grade),
repetition ratio (n-gram deduplication), vocabulary diversity, and
length adequacy. Optionally uses a connected LLM for perplexity scoring.
"""

import json
import math
import os
import re
from collections import Counter


def run(ctx):
    # Read upstream dataset metadata
    _dataset_meta = {}
    try:
        _meta_input = ctx.load_input("dataset_meta")
        if isinstance(_meta_input, dict):
            _dataset_meta = _meta_input
    except (ValueError, KeyError):
        pass

    # ── Configuration ─────────────────────────────────────────────────────
    text_column = _dataset_meta.get("text_column", ctx.config.get("text_column", "text"))
    metrics_str = ctx.config.get("metrics_to_compute", "readability,repetition,length,vocabulary")
    min_length = int(ctx.config.get("min_length", 10))
    max_rep_ratio = float(ctx.config.get("max_repetition_ratio", 0.3))
    max_samples = int(ctx.config.get("max_samples", 0))
    repetition_ngram_size = int(ctx.config.get("repetition_ngram_size", 3))

    # ── Output format config ───────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "json")
    decimal_precision = int(ctx.config.get("decimal_precision", 4))


    metrics_to_compute = [m.strip() for m in metrics_str.split(",") if m.strip()]

    # ── Load dataset ──────────────────────────────────────────────────────
    rows = None
    try:
        dataset_path = ctx.load_input("dataset")
        data_file = (os.path.join(dataset_path, "data.json")
                     if os.path.isdir(dataset_path) else dataset_path)
        with open(data_file, "r", encoding="utf-8") as f:
            rows = json.load(f)
    except (ValueError, Exception):
        pass

    if not rows:
        ctx.log_message("No dataset connected — using demo data")
        rows = [
            {"text": "The quick brown fox jumps over the lazy dog. This is a well-written sentence that demonstrates proper grammar and vocabulary usage."},
            {"text": "The the the the the the the. Bad bad bad."},
            {"text": "Machine learning models can process vast amounts of data to identify patterns and make predictions, enabling applications across healthcare, finance, and technology sectors."},
            {"text": "good"},
            {"text": "I think that the implementation of the new algorithm shows significant improvements in both speed and accuracy, which should lead to better user experiences overall."},
        ]

    if max_samples > 0:
        rows = rows[:max_samples]

    ctx.log_message(f"Evaluating {len(rows)} texts for: {', '.join(metrics_to_compute)}")

    # ── Analyze each text ─────────────────────────────────────────────────
    results = []
    for i, row in enumerate(rows):
        text = str(row.get(text_column, row) if isinstance(row, dict) else row)
        words = text.split()
        sentences = _split_sentences(text)

        entry = {"text": text[:200]}

        if "length" in metrics_to_compute:
            entry["word_count"] = len(words)
            entry["sentence_count"] = len(sentences)
            entry["too_short"] = len(words) < min_length

        if "readability" in metrics_to_compute:
            entry["flesch_kincaid_grade"] = round(_flesch_kincaid(words, sentences), 2)
            entry["avg_sentence_length"] = round(len(words) / max(len(sentences), 1), 2)
            entry["avg_word_length"] = round(
                sum(len(w) for w in words) / max(len(words), 1), 2
            )

        if "repetition" in metrics_to_compute:
            rep_ratio = _repetition_ratio(words, repetition_ngram_size)
            entry["repetition_ratio"] = round(rep_ratio, 4)
            entry["is_degenerate"] = rep_ratio > max_rep_ratio

        if "vocabulary" in metrics_to_compute:
            unique = len(set(w.lower() for w in words))
            entry["unique_words"] = unique
            entry["vocabulary_diversity"] = round(unique / max(len(words), 1), 4)

        results.append(entry)
        ctx.report_progress(i + 1, len(rows))

    # ── Aggregate metrics ─────────────────────────────────────────────────
    n = max(len(results), 1)
    metrics = {"total_texts": len(results)}

    if "length" in metrics_to_compute:
        word_counts = [r.get("word_count", 0) for r in results]
        metrics["avg_word_count"] = round(sum(word_counts) / n, 2)
        metrics["too_short_count"] = sum(1 for r in results if r.get("too_short", False))
        metrics["too_short_rate"] = round(metrics["too_short_count"] / n, 4)

    if "readability" in metrics_to_compute:
        fk_grades = [r.get("flesch_kincaid_grade", 0) for r in results]
        metrics["avg_flesch_kincaid"] = round(sum(fk_grades) / n, 2)

    if "repetition" in metrics_to_compute:
        rep_ratios = [r.get("repetition_ratio", 0) for r in results]
        metrics["avg_repetition_ratio"] = round(sum(rep_ratios) / n, 4)
        metrics["degenerate_count"] = sum(1 for r in results if r.get("is_degenerate", False))
        metrics["degenerate_rate"] = round(metrics["degenerate_count"] / n, 4)

    if "vocabulary" in metrics_to_compute:
        diversities = [r.get("vocabulary_diversity", 0) for r in results]
        metrics["avg_vocabulary_diversity"] = round(sum(diversities) / n, 4)

    ctx.log_message(f"\nCoherence Results:")
    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            ctx.log_message(f"  {k}: {v}")

    # ── Save outputs ──────────────────────────────────────────────────────
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    ctx.save_output("dataset", out_dir)

    # ── Save report output ─────────────────────────────────────────────
    _flagged = [r for r in results if r.get("too_short") or r.get("is_degenerate")]
    _report = {"summary": metrics, "total_flagged": len(_flagged), "flagged_texts": _flagged[:50]}
    _report_path = os.path.join(ctx.run_dir, "coherence_report.json")
    with open(_report_path, "w", encoding="utf-8") as f:
        json.dump(_report, f, indent=2)
    ctx.save_artifact("coherence_report", _report_path)
    ctx.save_output("report", _report_path)

    ctx.save_output("metrics", metrics)
    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            ctx.log_metric(k, v)
    ctx.report_progress(1, 1)


def _split_sentences(text):
    """Split text into sentences."""
    sentences = re.split(r'[.!?]+', text)
    return [s.strip() for s in sentences if s.strip()]


def _count_syllables(word):
    """Approximate syllable count for English words."""
    word = word.lower().strip()
    if len(word) <= 2:
        return 1
    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    # Adjust for silent e
    if word.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)


def _flesch_kincaid(words, sentences):
    """Compute Flesch-Kincaid grade level."""
    if not words or not sentences:
        return 0.0
    total_syllables = sum(_count_syllables(w) for w in words)
    asl = len(words) / max(len(sentences), 1)  # avg sentence length
    asw = total_syllables / max(len(words), 1)  # avg syllables per word
    return 0.39 * asl + 11.8 * asw - 15.59


def _repetition_ratio(words, n=3):
    """Compute fraction of repeated n-grams."""
    if len(words) < n:
        return 0.0
    ngrams = []
    for i in range(len(words) - n + 1):
        ngrams.append(tuple(w.lower() for w in words[i:i + n]))
    counts = Counter(ngrams)
    repeated = sum(c - 1 for c in counts.values() if c > 1)
    return repeated / max(len(ngrams), 1)
