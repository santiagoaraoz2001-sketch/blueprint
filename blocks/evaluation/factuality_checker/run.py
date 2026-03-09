"""Factuality Checker — evaluate factual accuracy of model responses.

Supports five comparison methods:
  - exact_match: normalized string equality
  - contains: reference text appears within the output
  - f1: token-level F1 score with configurable threshold
  - semantic_sim: embedding cosine similarity (requires sentence-transformers)
  - llm_judge: uses a connected LLM to evaluate correctness
"""

import json
import os
import re


def run(ctx):
    # ── Configuration ─────────────────────────────────────────────────────
    output_column = ctx.config.get("output_column", "_response")
    reference_column = ctx.config.get("reference_column", "reference")
    method = ctx.config.get("method", "exact_match")
    case_sensitive = ctx.config.get("case_sensitive", False)
    f1_threshold = float(ctx.config.get("f1_threshold", 0.5))
    sim_threshold = float(ctx.config.get("similarity_threshold", 0.8))
    max_samples = int(ctx.config.get("max_samples", 0))
    embedding_model = ctx.config.get("embedding_model", "all-MiniLM-L6-v2")
    judge_timeout = int(ctx.config.get("judge_timeout", 30))

    # ── Output format config ───────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "json")
    decimal_precision = int(ctx.config.get("decimal_precision", 4))


    # ── Load dataset ──────────────────────────────────────────────────────
    try:
        dataset_path = ctx.load_input("dataset")
        data_file = (os.path.join(dataset_path, "data.json")
                     if os.path.isdir(dataset_path) else dataset_path)
        with open(data_file, "r", encoding="utf-8") as f:
            rows = json.load(f)
    except (ValueError, Exception):
        ctx.log_message("No dataset connected — using demo data")
        rows = [
            {"_response": "Paris", "reference": "Paris", "question": "Capital of France?"},
            {"_response": "The capital is Berlin", "reference": "Berlin", "question": "Capital of Germany?"},
            {"_response": "Python", "reference": "Python", "question": "Most popular ML language?"},
            {"_response": "100 degrees Celsius", "reference": "100C", "question": "Boiling point of water?"},
            {"_response": "Jupiter", "reference": "Jupiter", "question": "Largest planet?"},
            {"_response": "Mercury", "reference": "Venus", "question": "Hottest planet?"},
            {"_response": "8", "reference": "8", "question": "Number of planets?"},
            {"_response": "Oxygen and Hydrogen", "reference": "H2O", "question": "Water composition?"},
        ]

    if max_samples > 0:
        rows = rows[:max_samples]

    # ── Load judge model if needed ────────────────────────────────────────
    judge_fn = None
    if method == "llm_judge":
        judge_fn = _init_llm_judge(ctx, judge_timeout)
        if judge_fn is None:
            ctx.log_message("No judge model available — falling back to f1 method")
            method = "f1"

    # ── Load embedding model if needed ────────────────────────────────────
    embed_fn = None
    if method == "semantic_sim":
        embed_fn = _init_embeddings(ctx, embedding_model)
        if embed_fn is None:
            ctx.log_message("Embedding model not available — falling back to f1 method")
            method = "f1"

    ctx.log_message(f"Checking factuality: {len(rows)} items, method={method}")

    # ── Evaluate each item ────────────────────────────────────────────────
    results = []
    correct = 0
    total = 0

    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue

        output = str(row.get(output_column, ""))
        reference = str(row.get(reference_column, ""))

        if not reference:
            continue

        total += 1
        is_correct, score = _check_factuality(
            output, reference, method, case_sensitive,
            f1_threshold, sim_threshold, judge_fn, embed_fn,
        )

        if is_correct:
            correct += 1

        results.append({
            "index": i,
            "output": output[:200],
            "reference": reference[:200],
            "correct": is_correct,
            "score": round(score, 4) if score is not None else None,
            "question": row.get("question", row.get("input", row.get("prompt", f"Item {i}"))),
        })
        ctx.report_progress(i + 1, len(rows))

    # ── Compute metrics ───────────────────────────────────────────────────
    accuracy = round(correct / max(total, 1), 4)
    errors = [r for r in results if not r["correct"]]

    ctx.log_message(f"\nFactuality Results:")
    ctx.log_message(f"  Total checked: {total}")
    ctx.log_message(f"  Correct: {correct}")
    ctx.log_message(f"  Accuracy: {accuracy:.1%}")
    ctx.log_message(f"  Method: {method}")

    if errors:
        ctx.log_message(f"\nSample errors ({min(5, len(errors))} of {len(errors)}):")
        for e in errors[:5]:
            ctx.log_message(f"  Q: {e['question']}")
            ctx.log_message(f"    Got: {e['output'][:80]}")
            ctx.log_message(f"    Expected: {e['reference'][:80]}")

    metrics = {
        "accuracy": accuracy,
        "correct": correct,
        "total": total,
        "errors": len(errors),
        "method": method,
    }

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

    report_path = os.path.join(ctx.run_dir, "error_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"metrics": metrics, "errors": errors}, f, indent=2)
    ctx.save_artifact("error_report", report_path)

    ctx.save_output("dataset", out_dir)
    for _mk, _mv in metrics.items():
        if isinstance(_mv, float):
            metrics[_mk] = round(_mv, decimal_precision)
    ctx.save_output("metrics", metrics)
    ctx.save_output("report", report_path)
    ctx.log_metric("accuracy", accuracy)
    ctx.log_metric("correct", correct)
    ctx.log_metric("total", total)
    ctx.report_progress(1, 1)


def _check_factuality(output, reference, method, case_sensitive,
                       f1_threshold, sim_threshold, judge_fn, embed_fn):
    """Check if output matches reference using the specified method."""
    if method == "exact_match":
        norm_out = _normalize(output, case_sensitive)
        norm_ref = _normalize(reference, case_sensitive)
        match = norm_out == norm_ref
        return match, 1.0 if match else 0.0

    elif method == "contains":
        norm_out = _normalize(output, case_sensitive)
        norm_ref = _normalize(reference, case_sensitive)
        match = norm_ref in norm_out
        return match, 1.0 if match else 0.0

    elif method == "f1":
        f1 = _token_f1(output, reference, case_sensitive)
        return f1 >= f1_threshold, f1

    elif method == "semantic_sim" and embed_fn is not None:
        sim = embed_fn(output, reference)
        return sim >= sim_threshold, sim

    elif method == "llm_judge" and judge_fn is not None:
        is_correct, score = judge_fn(output, reference)
        return is_correct, score

    # Fallback
    return _normalize(output, case_sensitive) == _normalize(reference, case_sensitive), None


def _normalize(text, case_sensitive=False):
    t = str(text).strip()
    if not case_sensitive:
        t = t.lower()
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _token_f1(output, reference, case_sensitive=False):
    pred_tokens = set(_normalize(output, case_sensitive).split())
    ref_tokens = set(_normalize(reference, case_sensitive).split())
    if not pred_tokens or not ref_tokens:
        return 0.0
    common = pred_tokens & ref_tokens
    precision = len(common) / len(pred_tokens)
    recall = len(common) / len(ref_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _init_embeddings(ctx, model_name="all-MiniLM-L6-v2"):
    """Initialize sentence-transformers for semantic similarity."""
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np

        model = SentenceTransformer(model_name)
        ctx.log_message("Using sentence-transformers for semantic similarity")

        def compute_similarity(text_a, text_b):
            embeddings = model.encode([text_a, text_b])
            cos = np.dot(embeddings[0], embeddings[1]) / (
                np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
            )
            return float(cos)

        return compute_similarity
    except ImportError:
        ctx.log_message("sentence-transformers not installed (pip install sentence-transformers)")
        return None


def _init_llm_judge(ctx, timeout=30):
    """Initialize LLM judge using the connected model."""
    try:
        model_info = ctx.load_input("model")
    except (ValueError, Exception):
        ctx.log_message("No judge model connected — cannot use llm_judge method")
        return None

    model_name = ""
    endpoint = "http://localhost:11434"
    if isinstance(model_info, dict):
        model_name = model_info.get("model_name", model_info.get("model_id", ""))
        endpoint = model_info.get("endpoint", endpoint)
    elif isinstance(model_info, str):
        model_name = model_info

    if not model_name:
        return None

    ctx.log_message(f"Using LLM judge: {model_name}")

    def judge(output, reference):
        import urllib.request
        prompt = (
            f"You are a factuality judge. Determine if the model's answer is factually "
            f"correct given the reference answer.\n\n"
            f"Reference answer: {reference}\n"
            f"Model's answer: {output}\n\n"
            f"Is the model's answer factually correct? Reply with exactly 'CORRECT' or 'INCORRECT'."
        )
        try:
            payload = json.dumps({
                "model": model_name, "prompt": prompt,
                "options": {"temperature": 0.0, "num_predict": 20},
                "stream": False,
            }).encode()
            req = urllib.request.Request(
                f"{endpoint.rstrip('/')}/api/generate",
                data=payload, headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
                response = data.get("response", "").strip().upper()
                is_correct = "CORRECT" in response and "INCORRECT" not in response
                return is_correct, 1.0 if is_correct else 0.0
        except Exception:
            return False, 0.0

    return judge
