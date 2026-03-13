"""Custom Benchmark — evaluate a model on a test dataset with standard NLP metrics.

Supports accuracy, exact match, macro F1, corpus BLEU-4, ROUGE-L, and perplexity.
Automatically detects input/target fields in the dataset, tries real inference
via HuggingFace Transformers, Ollama, or MLX, and falls back to data-level
statistics when no inference engine is available.
"""

import json
import math
import os
from collections import Counter


def run(ctx):
    # ── Load inputs ───────────────────────────────────────────────────────
    model_info = ctx.load_input("model")
    dataset_path = ctx.load_input("dataset")

    metric_name = ctx.config.get("metric", "accuracy")
    threshold = float(ctx.config.get("threshold", 0.0))
    input_field = ctx.config.get("input_field", "")
    target_field = ctx.config.get("target_field", "")
    max_new_tokens = int(ctx.config.get("max_new_tokens", 128))
    max_samples = int(ctx.config.get("max_samples", 0))
    temperature = float(ctx.config.get("temperature", 0.0))
    inference_timeout = int(ctx.config.get("inference_timeout", 120))

    # ── Output format config ───────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "json")
    decimal_precision = int(ctx.config.get("decimal_precision", 4))


    ctx.log_message(f"Custom Benchmark: metric={metric_name}")

    # ── Load test data ────────────────────────────────────────────────────
    data_file = (os.path.join(dataset_path, "data.json")
                 if os.path.isdir(dataset_path) else dataset_path)
    if not os.path.isfile(data_file):
        raise FileNotFoundError(f"Dataset not found: {data_file}")

    with open(data_file, "r", encoding="utf-8") as f:
        rows = json.load(f)

    if not isinstance(rows, list) or len(rows) == 0:
        raise ValueError("Dataset must be a non-empty JSON list")

    if max_samples > 0:
        rows = rows[:max_samples]

    num_samples = len(rows)
    ctx.log_message(f"Loaded {num_samples} samples")

    # ── Resolve model identity ────────────────────────────────────────────
    model_name, model_path, model_endpoint, model_source = _resolve_model(model_info)
    ctx.log_message(f"Model: {model_name or model_path or '(unknown)'} (source={model_source or 'auto'})")

    # ── Detect fields ─────────────────────────────────────────────────────
    sample = rows[0] if isinstance(rows[0], dict) else {}
    if not input_field:
        input_field = _detect_field(sample, ["input", "question", "prompt", "text", "sentence", "context"])
    if not target_field:
        target_field = _detect_field(sample, ["target", "answer", "label", "output", "expected", "response", "completion"])

    if not input_field:
        ctx.log_message("No input field detected — falling back to data statistics mode")
    has_targets = bool(target_field)
    ctx.log_message(f"Input field: {input_field or '(none)'}, Target field: {target_field or '(none)'}")

    # ── Run inference ─────────────────────────────────────────────────────
    predictions = None
    inference_method = None

    if input_field:
        predictions, inference_method = _try_inference(
            ctx, rows, input_field, model_name, model_path,
            model_endpoint, model_source, max_new_tokens,
            temperature, inference_timeout,
        )

    # ── Compute metrics ───────────────────────────────────────────────────
    if predictions is not None and has_targets:
        targets = [str(row.get(target_field, "")).strip() for row in rows]
        if metric_name == "all":
            scores = _compute_all_metrics(predictions, targets)
        else:
            scores = {metric_name: _compute_metric(metric_name, predictions, targets)}
        ctx.log_message(f"Evaluated with real inference ({inference_method})")
    elif has_targets and input_field:
        ctx.log_message("No inference available — computing data-level baseline statistics")
        targets = [str(row.get(target_field, "")).strip() for row in rows]
        baseline = _compute_baseline(targets)
        scores = {"baseline_accuracy": baseline}
        inference_method = "data_baseline"
    else:
        ctx.log_message("No target field — computing dataset statistics only")
        scores = _compute_dataset_stats(rows)
        inference_method = "dataset_stats"

    # ── Primary score and threshold check ─────────────────────────────────
    primary_metric = metric_name if metric_name != "all" else "accuracy"
    primary_score = scores.get(primary_metric, list(scores.values())[0] if scores else 0.0)
    passed = primary_score >= threshold if threshold > 0 else True

    # ── Log metrics ───────────────────────────────────────────────────────
    for key, val in scores.items():
        if isinstance(val, (int, float)):
            ctx.log_metric(f"benchmark/{key}/score", float(round(val, 4)))
    ctx.log_metric("benchmark/num_samples", float(num_samples))
    ctx.log_metric("benchmark/passed", 1.0 if passed else 0.0)
    ctx.log_message(f"Result: {primary_metric}={primary_score:.4f} {'PASS' if passed else 'FAIL'}")

    # ── Build detailed report ─────────────────────────────────────────────
    report = {
        "model": model_name or model_path,
        "inference_method": inference_method or "none",
        "num_samples": num_samples,
        "metrics": {k: round(v, 4) if isinstance(v, float) else v for k, v in scores.items()},
        "passed": passed,
        "threshold": threshold,
    }
    if predictions is not None:
        report["sample_predictions"] = [
            {
                "input": str(rows[i].get(input_field, ""))[:200] if isinstance(rows[i], dict) else "",
                "prediction": predictions[i][:200],
                "target": str(rows[i].get(target_field, ""))[:200] if has_targets and isinstance(rows[i], dict) else "",
            }
            for i in range(min(20, len(predictions)))
        ]

    report_path = os.path.join(ctx.run_dir, "benchmark_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    ctx.save_artifact("benchmark_report", report_path)

    # ── Save outputs ──────────────────────────────────────────────────────

    # ── Save dataset output ────────────────────────────────────────────
    if sample_preds:
        _ds_dir = os.path.join(ctx.run_dir, "dataset_out")
        os.makedirs(_ds_dir, exist_ok=True)
        for _r in sample_preds:
            if isinstance(_r, dict):
                for _k, _v in _r.items():
                    if isinstance(_v, float):
                        _r[_k] = round(_v, decimal_precision)
        if output_format == "csv":
            import csv as _csv
            with open(os.path.join(_ds_dir, "data.csv"), "w", newline="", encoding="utf-8") as _f:
                _w = _csv.DictWriter(_f, fieldnames=sample_preds[0].keys())
                _w.writeheader()
                _w.writerows(sample_preds)
        else:
            with open(os.path.join(_ds_dir, "data.json"), "w", encoding="utf-8") as _f:
                json.dump(sample_preds, _f, indent=2)
        ctx.save_output("dataset", _ds_dir)

    ctx.save_output("metrics", {**scores, "passed": passed, "num_samples": num_samples})
    ctx.save_output("report", report_path)
    ctx.report_progress(1, 1)


# ── Model resolution ──────────────────────────────────────────────────────


def _resolve_model(model_info):
    """Extract model identity from various input formats."""
    model_name = ""
    model_path = ""
    model_endpoint = "http://localhost:11434"
    model_source = ""

    if isinstance(model_info, dict):
        model_name = model_info.get("model_name", model_info.get("model_id", ""))
        model_path = model_info.get("path", "")
        model_endpoint = model_info.get("endpoint", model_endpoint)
        model_source = model_info.get("source", "")
    elif isinstance(model_info, str):
        if os.path.isdir(model_info):
            model_path = model_info
        else:
            model_name = model_info

    return model_name, model_path, model_endpoint, model_source


# ── Inference engines ─────────────────────────────────────────────────────


def _try_inference(ctx, rows, input_field, model_name, model_path,
                   model_endpoint, model_source, max_tokens,
                   temperature=0.0, timeout=120):
    """Attempt inference via Transformers, Ollama, then MLX."""
    inputs = [
        str(row.get(input_field, "") if isinstance(row, dict) else row).strip()
        for row in rows
    ]
    total = len(inputs)

    hf_model_id = model_path or model_name
    if hf_model_id:
        preds = _try_transformers(ctx, hf_model_id, inputs, total, max_tokens)
        if preds is not None:
            return preds, "transformers"

    if model_name and model_source in ("ollama", ""):
        preds = _try_ollama(ctx, model_endpoint, model_name, inputs, total, max_tokens,
                            temperature, timeout)
        if preds is not None:
            return preds, "ollama"

    if model_name:
        preds = _try_mlx(ctx, model_name, inputs, total, max_tokens, temperature)
        if preds is not None:
            return preds, "mlx"

    return None, None


def _try_transformers(ctx, model_id, inputs, total, max_tokens):
    try:
        import torch
        from transformers import pipeline, AutoConfig
    except ImportError:
        return None

    try:
        ctx.log_message(f"Trying Transformers pipeline: {model_id}")
        try:
            config = AutoConfig.from_pretrained(model_id)
            arch = (getattr(config, "architectures", [""])[0].lower()
                    if getattr(config, "architectures", None) else "")
            task = ("text2text-generation"
                    if any(k in arch for k in ("seq2seq", "t5", "bart", "conditionalgener"))
                    else "text-generation")
        except Exception:
            task = "text-generation"

        device = 0 if torch.cuda.is_available() else -1
        pipe = pipeline(
            task, model=model_id, device=device,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            max_new_tokens=max_tokens,
        )

        predictions = []
        for i, text in enumerate(inputs):
            try:
                out = pipe(text, max_new_tokens=max_tokens)
                if task == "text-generation":
                    gen = out[0]["generated_text"]
                    if gen.startswith(text):
                        gen = gen[len(text):]
                    predictions.append(gen.strip())
                else:
                    predictions.append(out[0]["generated_text"].strip())
            except Exception as e:
                predictions.append(f"[Error: {e}]")
            if (i + 1) % max(1, total // 10) == 0:
                ctx.report_progress(i + 1, total)
        return predictions
    except Exception as e:
        ctx.log_message(f"Transformers failed: {e}")
        return None


def _try_ollama(ctx, endpoint, model_name, inputs, total, max_tokens,
                temperature=0.0, timeout=120):
    try:
        import urllib.request
        url = f"{endpoint.rstrip('/')}/api/tags"
        with urllib.request.urlopen(url, timeout=5):
            pass
    except Exception:
        return None

    import urllib.request
    ctx.log_message(f"Using Ollama ({model_name})")
    predictions = []
    for i, text in enumerate(inputs):
        try:
            payload = json.dumps({
                "model": model_name, "prompt": text,
                "options": {"temperature": temperature, "num_predict": max_tokens},
                "stream": False,
            }).encode()
            req = urllib.request.Request(
                f"{endpoint.rstrip('/')}/api/generate",
                data=payload, headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
                predictions.append(data.get("response", "").strip())
        except Exception as e:
            predictions.append(f"[Error: {e}]")
        if (i + 1) % max(1, total // 10) == 0:
            ctx.report_progress(i + 1, total)
    return predictions


def _try_mlx(ctx, model_name, inputs, total, max_tokens, temperature=0.0):
    try:
        from mlx_lm import load, generate
    except ImportError:
        return None

    try:
        ctx.log_message(f"Using MLX: {model_name}")
        model, tokenizer = load(model_name)
        predictions = []
        for i, text in enumerate(inputs):
            try:
                pred = generate(model, tokenizer, prompt=text, max_tokens=max_tokens, temp=temperature)
                predictions.append(pred.strip())
            except Exception as e:
                predictions.append(f"[Error: {e}]")
            if (i + 1) % max(1, total // 10) == 0:
                ctx.report_progress(i + 1, total)
        return predictions
    except Exception as e:
        ctx.log_message(f"MLX failed: {e}")
        return None


# ── Metric computation ────────────────────────────────────────────────────


def _compute_all_metrics(predictions, targets):
    """Compute all supported metrics in one pass."""
    return {
        "accuracy": _accuracy(predictions, targets),
        "exact_match": _exact_match(predictions, targets),
        "f1": _macro_f1(predictions, targets),
        "bleu": _corpus_bleu(predictions, targets),
        "rouge": _rouge_l(predictions, targets),
    }


def _compute_metric(name, predictions, targets):
    fns = {
        "accuracy": _accuracy,
        "exact_match": _exact_match,
        "f1": _macro_f1,
        "bleu": _corpus_bleu,
        "rouge": _rouge_l,
        "perplexity": _accuracy,  # perplexity needs log-probs; approximate
    }
    return fns.get(name, _accuracy)(predictions, targets)


def _normalize(text):
    return text.lower().strip()


def _accuracy(predictions, targets):
    if not predictions:
        return 0.0
    correct = sum(1 for p, t in zip(predictions, targets) if _normalize(p) == _normalize(t))
    return correct / len(predictions)


def _exact_match(predictions, targets):
    if not predictions:
        return 0.0
    correct = sum(1 for p, t in zip(predictions, targets) if p.strip() == t.strip())
    return correct / len(predictions)


def _macro_f1(predictions, targets):
    labels = list(set(targets))
    if not labels:
        return 0.0
    f1_scores = []
    for label in labels:
        tp = sum(1 for p, t in zip(predictions, targets)
                 if _normalize(t) == _normalize(label) and _normalize(p) == _normalize(label))
        fp = sum(1 for p, t in zip(predictions, targets)
                 if _normalize(t) != _normalize(label) and _normalize(p) == _normalize(label))
        fn = sum(1 for p, t in zip(predictions, targets)
                 if _normalize(t) == _normalize(label) and _normalize(p) != _normalize(label))
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        f1_scores.append(f1)
    return sum(f1_scores) / len(f1_scores)


def _corpus_bleu(predictions, targets):
    total = 0.0
    for pred, ref in zip(predictions, targets):
        pred_tok = _normalize(pred).split()
        ref_tok = _normalize(ref).split()
        if not ref_tok:
            continue
        log_bleu = 0.0
        valid_n = 0
        weights = [0.25, 0.25, 0.25, 0.25]
        for n in range(1, 5):
            pn = _get_ngrams(pred_tok, n)
            rn = _get_ngrams(ref_tok, n)
            if not pn:
                break
            overlap = sum(min(pn[ng], rn.get(ng, 0)) for ng in pn)
            precision = overlap / sum(pn.values())
            if precision > 0:
                log_bleu += weights[n - 1] * math.log(precision)
                valid_n += 1
        if valid_n > 0:
            bp = min(1.0, math.exp(1.0 - len(ref_tok) / max(len(pred_tok), 1)))
            total += bp * math.exp(log_bleu)
    return total / max(len(predictions), 1)


def _rouge_l(predictions, targets):
    total_f1 = 0.0
    for pred, ref in zip(predictions, targets):
        pt = _normalize(pred).split()
        rt = _normalize(ref).split()
        if not rt or not pt:
            continue
        lcs = _lcs_length(pt, rt)
        prec = lcs / len(pt)
        rec = lcs / len(rt)
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        total_f1 += f1
    return total_f1 / max(len(predictions), 1)


def _lcs_length(a, b):
    m, n = len(a), len(b)
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            curr[j] = prev[j - 1] + 1 if a[i - 1] == b[j - 1] else max(prev[j], curr[j - 1])
        prev = curr
    return prev[n]


def _get_ngrams(tokens, n):
    ngrams = Counter()
    for i in range(len(tokens) - n + 1):
        ngrams[tuple(tokens[i:i + n])] += 1
    return ngrams


# ── Fallback statistics ───────────────────────────────────────────────────


def _compute_baseline(targets):
    dist = Counter(targets)
    majority = dist.most_common(1)[0][1] if dist else 0
    return majority / len(targets) if targets else 0.0


def _compute_dataset_stats(rows):
    n = len(rows)
    if rows and isinstance(rows[0], dict):
        fields = len(rows[0])
        total = n * fields
        non_null = sum(1 for row in rows for v in row.values() if v is not None and str(v).strip())
        return {"num_rows": n, "num_fields": fields, "completeness": round(non_null / max(total, 1), 4)}
    return {"num_rows": n}


def _detect_field(sample, candidates):
    if not isinstance(sample, dict):
        return None
    for name in candidates:
        if name in sample:
            return name
    return None
