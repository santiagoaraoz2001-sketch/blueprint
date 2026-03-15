"""RAG Eval — evaluate Retrieval-Augmented Generation pipeline quality.

Evaluates four key RAG dimensions:
  - Faithfulness: Is the answer grounded in the retrieved context?
  - Answer Relevance: Does the answer address the question?
  - Context Relevance: Is the retrieved context relevant to the question?
  - Answer Correctness: Does the answer match the reference? (requires ground truth)

Supports heuristic (token overlap) and LLM-as-judge evaluation methods.
"""

import json
import os
import re
from collections import Counter

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
    question_col = ctx.config.get("question_column", "question")
    context_col = ctx.config.get("context_column", "context")
    answer_col = ctx.config.get("answer_column", "answer")
    reference_col = ctx.config.get("reference_column", "reference")
    metrics_str = ctx.config.get("metrics_to_compute",
                  "faithfulness,answer_relevance,context_relevance,answer_correctness")
    method = ctx.config.get("method", "heuristic")
    max_samples = int(ctx.config.get("max_samples", 0))
    judge_timeout = int(ctx.config.get("judge_timeout", 30))

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

    # ── Model config: upstream model input takes priority ────────────────
    model_data = {}
    if ctx.inputs.get("model"):
        model_data = ctx.load_input("model")
        if isinstance(model_data, dict):
            ctx.log_message(f"Using connected model: {model_data.get('model_name', 'unknown')}")

    framework = model_data.get("source", model_data.get("backend",
        ctx.config.get("provider", "ollama")))
    model_name = model_data.get("model_name", model_data.get("model_id",
        ctx.config.get("model_name", "")))
    inf_config = {"endpoint": model_data.get("endpoint", model_data.get("base_url",
        ctx.config.get("endpoint", "http://localhost:11434")))}

    # ── Initialize LLM judge if needed ────────────────────────────────────
    judge_fn = None
    if method == "llm_judge":
        judge_fn = _init_judge(ctx, framework, model_name, inf_config, judge_timeout)
        if judge_fn is None:
            ctx.log_message("No judge model available — falling back to heuristic")
            method = "heuristic"

    ctx.log_message(f"RAG Evaluation: {len(rows)} samples, method={method}")
    ctx.log_message(f"Metrics: {', '.join(compute)}")

    # ── Evaluate each sample ──────────────────────────────────────────────
    all_scores = []
    detailed = []

    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue

        question = str(row.get(question_col, ""))
        context = str(row.get(context_col, ""))
        answer = str(row.get(answer_col, ""))
        reference = str(row.get(reference_col, ""))

        scores = {}

        if method == "heuristic":
            if "faithfulness" in compute and context:
                scores["faithfulness"] = _heuristic_faithfulness(answer, context)
            if "answer_relevance" in compute and question:
                scores["answer_relevance"] = _heuristic_relevance(answer, question)
            if "context_relevance" in compute and question and context:
                scores["context_relevance"] = _heuristic_relevance(context, question)
            if "answer_correctness" in compute and reference:
                scores["answer_correctness"] = _token_f1(answer, reference)
        elif method == "llm_judge" and judge_fn:
            if "faithfulness" in compute and context:
                scores["faithfulness"] = judge_fn(
                    f"Is this answer faithful to the context (only uses info from context)?\n"
                    f"Context: {context[:500]}\nAnswer: {answer[:500]}\n"
                    f"Score from 0.0 to 1.0:"
                )
            if "answer_relevance" in compute and question:
                scores["answer_relevance"] = judge_fn(
                    f"Does this answer relevantly address the question?\n"
                    f"Question: {question}\nAnswer: {answer[:500]}\n"
                    f"Score from 0.0 to 1.0:"
                )
            if "context_relevance" in compute and question and context:
                scores["context_relevance"] = judge_fn(
                    f"Is this context relevant to the question?\n"
                    f"Question: {question}\nContext: {context[:500]}\n"
                    f"Score from 0.0 to 1.0:"
                )
            if "answer_correctness" in compute and reference:
                scores["answer_correctness"] = _token_f1(answer, reference)

        all_scores.append(scores)
        detailed.append({
            "index": i,
            "question": question[:200],
            "answer_preview": answer[:200],
            "scores": {k: round(v, 4) for k, v in scores.items()},
        })
        ctx.report_progress(i + 1, len(rows))

    # ── Aggregate ─────────────────────────────────────────────────────────
    metric_keys = set()
    for s in all_scores:
        metric_keys.update(s.keys())

    metrics = {"total_samples": len(all_scores), "method": method}
    for key in sorted(metric_keys):
        values = [s[key] for s in all_scores if key in s]
        if values:
            metrics[f"avg_{key}"] = round(sum(values) / len(values), 4)

    ctx.log_message(f"\nRAG Evaluation Results:")
    for k, v in metrics.items():
        if isinstance(v, float):
            ctx.log_message(f"  {k}: {v:.4f}")

    # ── Save outputs ──────────────────────────────────────────────────────
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(detailed, f, indent=2)

    report_path = os.path.join(ctx.run_dir, "rag_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"metrics": metrics, "detailed": detailed[:50]}, f, indent=2)
    ctx.save_artifact("rag_report", report_path)

    ctx.save_output("metrics", metrics)
    ctx.save_output("eval_dataset", out_dir)
    ctx.save_output("report", report_path)
    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            ctx.log_metric(k, v)
    ctx.report_progress(1, 1)


# ── Heuristic scoring ─────────────────────────────────────────────────────

def _tokenize(text):
    return re.findall(r'\b\w+\b', text.lower())


def _heuristic_faithfulness(answer, context):
    """Score: fraction of answer tokens found in the context."""
    ans_tokens = _tokenize(answer)
    ctx_tokens = set(_tokenize(context))
    if not ans_tokens:
        return 0.0
    grounded = sum(1 for t in ans_tokens if t in ctx_tokens)
    return round(grounded / len(ans_tokens), 4)


def _heuristic_relevance(text, query):
    """Score: token overlap between text and query."""
    text_tokens = set(_tokenize(text))
    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return 0.0
    overlap = len(text_tokens & query_tokens)
    return round(overlap / len(query_tokens), 4)


def _token_f1(prediction, reference):
    """Token-level F1 score."""
    pred_tokens = set(_tokenize(prediction))
    ref_tokens = set(_tokenize(reference))
    if not pred_tokens or not ref_tokens:
        return 0.0
    common = pred_tokens & ref_tokens
    precision = len(common) / len(pred_tokens)
    recall = len(common) / len(ref_tokens)
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def _init_judge(ctx, framework, model_name, config, timeout=30):
    """Initialize LLM judge for scoring via call_inference."""
    if not model_name:
        return None

    inf_config = dict(config)
    inf_config["max_tokens"] = 20
    inf_config["temperature"] = 0.0

    def judge(prompt):
        try:
            response_text, _meta = call_inference(
                framework, model_name, prompt, config=inf_config,
                log_fn=ctx.log_message,
            )
            response = (response_text or "0.5").strip()
            # Extract numeric score
            nums = re.findall(r'(\d+\.?\d*)', response)
            if nums:
                score = float(nums[0])
                return min(max(score, 0.0), 1.0)
            return 0.5
        except Exception:
            return 0.5

    return judge
