"""A/B Comparator — compare outputs from two or three models.

Supports two modes:
  1. Pre-computed responses: dataset has _response_a and _response_b columns
  2. Live inference: prompts are sent to connected models, responses compared

Comparison methods:
  - heuristic: length, specificity, and diversity scoring
  - llm_judge: uses a third LLM to evaluate which response is better
"""

import json
import os
import random

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
    method = ctx.config.get("comparison_method", "heuristic")
    judge_model = ctx.config.get("judge_model", "")
    judge_endpoint = ctx.config.get("judge_endpoint", "http://localhost:11434")
    prompt_column = ctx.config.get("prompt_column", "input")
    resp_col_a = ctx.config.get("response_column_a", "_response_a")
    resp_col_b = ctx.config.get("response_column_b", "_response_b")
    max_samples = int(ctx.config.get("max_samples", 0))
    seed = int(ctx.config.get("seed", 42))
    generation_temperature = float(ctx.config.get("generation_temperature", 0.7))
    max_new_tokens = int(ctx.config.get("max_new_tokens", 256))
    generation_timeout = int(ctx.config.get("generation_timeout", 60))
    judge_timeout = int(ctx.config.get("judge_timeout", 30))

    # ── Output format config ───────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "json")
    decimal_precision = int(ctx.config.get("decimal_precision", 4))

    random.seed(seed)

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
            {"input": "What is the capital of France?"},
            {"input": "What is Python?"},
            {"input": "At what temperature does water boil?"},
            {"input": "Does the earth orbit the sun?"},
            {"input": "What is ML?"},
        ]

    if max_samples > 0:
        rows = rows[:max_samples]

    # ── Check if we need to generate responses ────────────────────────────
    has_precomputed = (isinstance(rows[0], dict) and
                       resp_col_a in rows[0] and resp_col_b in rows[0])

    if not has_precomputed:
        rows = _generate_responses(ctx, rows, prompt_column, resp_col_a, resp_col_b,
                                   generation_temperature, max_new_tokens, generation_timeout)

    n_pairs = len(rows)
    ctx.log_message(f"Comparing {n_pairs} pairs")

    # ── Judge model config: upstream model input takes priority ──────────
    judge_model_data = {}
    if ctx.inputs.get("model"):
        judge_model_data = ctx.load_input("model")
        if isinstance(judge_model_data, dict):
            ctx.log_message(f"Using connected model: {judge_model_data.get('model_name', 'unknown')}")

    judge_framework = judge_model_data.get("source", judge_model_data.get("backend",
        ctx.config.get("provider", "ollama")))
    judge_model_name = judge_model_data.get("model_name", judge_model_data.get("model_id",
        ctx.config.get("judge_model", "")))
    judge_config = {"endpoint": judge_model_data.get("endpoint", judge_model_data.get("base_url",
        ctx.config.get("judge_endpoint", "http://localhost:11434")))}

    # ── Initialize comparison function ────────────────────────────────────
    if method == "llm_judge" and judge_model_name:
        compare_fn = _make_llm_judge(judge_framework, judge_model_name, judge_config, ctx)
        ctx.log_message(f"Using LLM judge: {judge_model_name}")
    else:
        compare_fn = _heuristic_compare
        if method == "llm_judge" and not judge_model_name:
            ctx.log_message("No judge model specified — falling back to heuristic")

    # ── Compare each pair ─────────────────────────────────────────────────
    comparisons = []
    a_wins, b_wins, ties = 0, 0, 0

    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue

        text_a = str(row.get(resp_col_a, ""))
        text_b = str(row.get(resp_col_b, ""))
        prompt = str(row.get(prompt_column, row.get("prompt", f"Sample {i}")))

        winner, score_a, score_b = compare_fn(prompt, text_a, text_b)

        if winner == "A":
            a_wins += 1
        elif winner == "B":
            b_wins += 1
        else:
            ties += 1

        comparisons.append({
            "index": i,
            "input": prompt[:200],
            "response_a": text_a[:200],
            "response_b": text_b[:200],
            "score_a": round(score_a, 4),
            "score_b": round(score_b, 4),
            "winner": winner,
        })
        ctx.report_progress(i + 1, n_pairs)

    # ── Compute metrics ───────────────────────────────────────────────────
    total = a_wins + b_wins + ties
    metrics = {
        "total_pairs": total,
        "model_a_wins": a_wins,
        "model_b_wins": b_wins,
        "ties": ties,
        "model_a_win_rate": round(a_wins / max(total, 1), 4),
        "model_b_win_rate": round(b_wins / max(total, 1), 4),
        "tie_rate": round(ties / max(total, 1), 4),
        "method": method,
    }

    ctx.log_message(f"\nResults: A wins={a_wins}, B wins={b_wins}, Ties={ties}")
    ctx.log_message(f"Win rates: A={metrics['model_a_win_rate']:.1%}, "
                   f"B={metrics['model_b_win_rate']:.1%}, "
                   f"Tie={metrics['tie_rate']:.1%}")

    # ── Save outputs ──────────────────────────────────────────────────────
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    for _r in comparisons:
        if isinstance(_r, dict):
            for _k, _v in _r.items():
                if isinstance(_v, float):
                    _r[_k] = round(_v, decimal_precision)
    if output_format == "csv" and comparisons:
        import csv as _csv
        with open(os.path.join(out_dir, "data.csv"), "w", newline="", encoding="utf-8") as f:
            _w = _csv.DictWriter(f, fieldnames=comparisons[0].keys())
            _w.writeheader()
            _w.writerows(comparisons)
    else:
        with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
            json.dump(comparisons, f, indent=2)

    ctx.save_output("dataset", out_dir)

    # ── Save report output ─────────────────────────────────────────────
    _report = {"summary": metrics, "comparisons": comparisons[:50]}
    _report_path = os.path.join(ctx.run_dir, "comparison_report.json")
    with open(_report_path, "w", encoding="utf-8") as f:
        json.dump(_report, f, indent=2)
    ctx.save_artifact("comparison_report", _report_path)
    ctx.save_output("report", _report_path)

    ctx.save_output("metrics", metrics)
    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            ctx.log_metric(k, v)
    ctx.report_progress(1, 1)


def _generate_responses(ctx, rows, prompt_column, resp_col_a, resp_col_b,
                        temperature=0.7, max_tokens=256, timeout=60):
    """Generate responses from connected models A and B."""
    models = {}
    for label, port_id in [("A", "model_a"), ("B", "model_b")]:
        try:
            info = ctx.load_input(port_id)
            name = ""
            endpoint = "http://localhost:11434"
            if isinstance(info, dict):
                name = info.get("model_name", info.get("model_id", ""))
                endpoint = info.get("endpoint", endpoint)
            elif isinstance(info, str):
                name = info
            if name:
                models[label] = {"name": name, "endpoint": endpoint}
        except (ValueError, Exception):
            pass

    if not models:
        ctx.log_message("No models connected — using demo responses")
        demo_responses_a = [
            "Paris is the capital.", "Python is a language.", "100C.",
            "Yes, it does.", "ML is a subset of AI.",
        ]
        demo_responses_b = [
            "The capital of France is Paris, located in Western Europe.",
            "Python is a high-level programming language used widely in data science.",
            "Water boils at 100 degrees Celsius at standard atmospheric pressure.",
            "Yes, the earth orbits the sun in an elliptical path.",
            "Machine learning is AI that learns from data patterns.",
        ]
        for i, row in enumerate(rows):
            if isinstance(row, dict):
                row[resp_col_a] = demo_responses_a[i] if i < len(demo_responses_a) else ""
                row[resp_col_b] = demo_responses_b[i] if i < len(demo_responses_b) else ""
        return rows

    import urllib.request

    for label, model in models.items():
        col = resp_col_a if label == "A" else resp_col_b
        ctx.log_message(f"Generating responses for Model {label}: {model['name']}")
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            prompt = str(row.get(prompt_column, row.get("prompt", "")))
            if not prompt:
                row[col] = ""
                continue
            try:
                payload = json.dumps({
                    "model": model["name"], "prompt": prompt,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                    "stream": False,
                }).encode()
                req = urllib.request.Request(
                    f"{model['endpoint'].rstrip('/')}/api/generate",
                    data=payload, headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode())
                    row[col] = data.get("response", "")
            except Exception as e:
                row[col] = f"[Error: {e}]"

    return rows


def _heuristic_compare(prompt, text_a, text_b):
    """Heuristic comparison based on length, specificity, and vocabulary."""
    words_a = text_a.split()
    words_b = text_b.split()

    # Length score (moderate length preferred)
    len_score_a = min(len(words_a), 100) / 100.0
    len_score_b = min(len(words_b), 100) / 100.0

    # Vocabulary diversity
    unique_a = len(set(w.lower() for w in words_a)) / max(len(words_a), 1)
    unique_b = len(set(w.lower() for w in words_b)) / max(len(words_b), 1)

    # Specificity (char length relative to response)
    spec_a = min(len(text_a) / 200.0, 1.0)
    spec_b = min(len(text_b) / 200.0, 1.0)

    score_a = 0.4 * len_score_a + 0.3 * spec_a + 0.3 * unique_a
    score_b = 0.4 * len_score_b + 0.3 * spec_b + 0.3 * unique_b

    if abs(score_a - score_b) < 0.05:
        return "tie", score_a, score_b
    elif score_a > score_b:
        return "A", score_a, score_b
    else:
        return "B", score_a, score_b


def _make_llm_judge(framework, model_name, config, ctx):
    """Create an LLM judge comparison function."""

    def llm_judge(prompt, text_a, text_b):
        judge_prompt = (
            f"You are an impartial judge. Compare two model responses to the same prompt.\n\n"
            f"Prompt: {prompt}\n\n"
            f"Response A: {text_a[:500]}\n\n"
            f"Response B: {text_b[:500]}\n\n"
            f"Which response is better? Consider accuracy, completeness, and clarity.\n"
            f"Reply with exactly one of: A, B, or TIE"
        )
        try:
            judge_cfg = {**config, "temperature": 0.0, "max_tokens": 10}
            response_text, meta = call_inference(
                framework, model_name, judge_prompt, "", judge_cfg,
                log_fn=ctx.log_message,
            )
            verdict = response_text.strip().upper()
            if "TIE" in verdict:
                return "tie", 0.5, 0.5
            elif verdict.startswith("A"):
                return "A", 1.0, 0.0
            elif verdict.startswith("B"):
                return "B", 0.0, 1.0
            return "tie", 0.5, 0.5
        except Exception:
            return "tie", 0.5, 0.5

    return llm_judge
