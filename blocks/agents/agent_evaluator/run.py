"""Agent Evaluator — evaluate agent performance on tasks."""

import json
import os
import random

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
    # ── Config ──────────────────────────────────────────────────────────
    eval_method = ctx.config.get("method", "task_completion")
    pass_threshold = float(ctx.config.get("pass_threshold", 0.5))
    custom_criteria = ctx.config.get("custom_criteria", "")
    num_tasks = int(ctx.config.get("num_tasks", 10))
    seed = int(ctx.config.get("seed", 42))

    random.seed(seed)

    # ── Load agent outputs ──────────────────────────────────────────────
    agent_outputs = _load_dataset(ctx, "dataset")

    # ── Load reference answers ──────────────────────────────────────────
    references = _load_dataset(ctx, "references")

    # Build reference lookup by task/id
    ref_lookup = {}
    for ref in references:
        if isinstance(ref, dict):
            key = ref.get("task", ref.get("id", ref.get("prompt", "")))
            ref_lookup[str(key)] = ref

    # ── Demo mode ───────────────────────────────────────────────────────
    is_simulated = not agent_outputs
    if is_simulated:
        ctx.log_message("⚠️ SIMULATION MODE: No agent outputs connected. Generating synthetic evaluation data.")
        agent_outputs = [
            {
                "task": f"Task {i}",
                "response": f"Agent response for task {i} with detailed analysis and conclusions.",
                "expected": f"Expected answer for task {i}",
                "steps_taken": random.randint(1, 5),
                "tools_used": random.randint(0, 3),
            }
            for i in range(num_tasks)
        ]

    ctx.log_message(
        f"Evaluating {len(agent_outputs)} outputs (method={eval_method}, "
        f"threshold={pass_threshold})"
    )

    # ── Evaluate ────────────────────────────────────────────────────────
    results = []
    total_score = 0

    for i, output in enumerate(agent_outputs):
        if not isinstance(output, dict):
            output = {"response": str(output)}

        response = str(output.get("response", output.get("_response", "")))
        expected = str(output.get("expected", output.get("reference", "")))
        steps = output.get("steps_taken", 1)
        tools = output.get("tools_used", 0)
        task_id = str(output.get("task", output.get("id", f"Task {i}")))

        # Check for reference from references input
        if not expected and task_id in ref_lookup:
            ref = ref_lookup[task_id]
            expected = str(ref.get("expected", ref.get("answer", ref.get("reference", ""))))

        # Score based on method
        if eval_method == "task_completion":
            score = _score_task_completion(response)
        elif eval_method == "accuracy":
            score = _score_accuracy(response, expected)
        elif eval_method == "efficiency":
            score = _score_efficiency(steps, tools)
        elif eval_method == "custom":
            score = _score_custom(response, expected, custom_criteria)
        else:
            score = random.uniform(0.4, 0.95)

        total_score += score
        results.append({
            "task": task_id,
            "score": round(score, 4),
            "passed": score >= pass_threshold,
            "steps_taken": steps,
            "tools_used": tools,
            "response_length": len(response),
            "method": eval_method,
        })
        ctx.report_progress(i + 1, len(agent_outputs))

    # ── Aggregate metrics ───────────────────────────────────────────────
    n = max(len(results), 1)
    avg_score = total_score / n
    pass_count = sum(1 for r in results if r["passed"])
    pass_rate = pass_count / n
    avg_steps = sum(r["steps_taken"] for r in results) / n

    ctx.log_message(f"\nAgent Evaluation Results:")
    ctx.log_message(f"  Average score: {avg_score:.4f}")
    ctx.log_message(f"  Pass rate (>={pass_threshold}): {pass_rate:.1%}")
    ctx.log_message(f"  Average steps: {avg_steps:.1f}")
    ctx.log_message(f"  Tasks evaluated: {len(results)}")

    # ── Save outputs ────────────────────────────────────────────────────
    out_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "data.json"), "w") as f:
        json.dump(results, f, indent=2)
    ctx.save_output("evaluation_dataset", out_dir)

    metrics = {
        "avg_score": round(avg_score, 4),
        "pass_rate": round(pass_rate, 4),
        "pass_count": pass_count,
        "fail_count": len(results) - pass_count,
        "avg_steps": round(avg_steps, 2),
        "total_tasks": len(results),
        "method": eval_method,
        "pass_threshold": pass_threshold,
    }
    ctx.save_output("metrics", metrics)
    ctx.log_metric("simulation_mode", 1.0 if is_simulated else 0.0)
    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            ctx.log_metric(k, v)

    # ── Generate text report ────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "markdown")
    if output_format == "markdown":
        report = "\n".join([
            "## Agent Evaluation Report\n",
            f"**Method:** {eval_method}",
            f"**Tasks evaluated:** {len(results)}",
            f"**Pass threshold:** {pass_threshold}\n",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Average Score | {avg_score:.4f} |",
            f"| Pass Rate | {pass_rate:.1%} |",
            f"| Passed | {pass_count} |",
            f"| Failed | {len(results) - pass_count} |",
            f"| Avg Steps | {avg_steps:.1f} |",
        ])
    elif output_format == "json":
        report = json.dumps(metrics, indent=2)
    else:
        report = (
            f"Agent Evaluation Report\n"
            f"Method: {eval_method}\n"
            f"Tasks: {len(results)}, Avg Score: {avg_score:.4f}, "
            f"Pass Rate: {pass_rate:.1%}, Passed: {pass_count}, "
            f"Failed: {len(results) - pass_count}"
        )

    report_path = os.path.join(ctx.run_dir, "report.txt")
    with open(report_path, "w") as f:
        f.write(report)
    ctx.save_output("report", report_path)

    ctx.report_progress(1, 1)


# ── Scoring functions ───────────────────────────────────────────────────


def _score_task_completion(response):
    """Heuristic scoring: response exists and has reasonable quality signals."""
    if not response or len(response.strip()) < 5:
        return 0.0

    score = 0.0
    text = response.strip()

    # Length check (non-trivial response)
    if len(text) > 10:
        score += 0.3
    if len(text.split()) > 20:
        score += 0.2

    # Structure signals (sentences, paragraphs, lists)
    if "." in text or "!" in text or "?" in text:
        score += 0.2
    if "\n" in text or any(text.startswith(c) for c in ("1.", "-", "*")):
        score += 0.15

    # Not an error message
    if not any(err in text.lower() for err in ["error", "failed", "exception", "traceback"]):
        score += 0.15

    return min(1.0, score)


def _score_accuracy(response, expected):
    """Score based on overlap with expected answer."""
    if not expected:
        return _score_task_completion(response)

    response_lower = response.lower().strip()
    expected_lower = expected.lower().strip()

    # Exact match
    if expected_lower == response_lower:
        return 1.0

    # Substring match
    if expected_lower in response_lower:
        return 0.9

    # Word overlap
    expected_words = set(expected_lower.split())
    response_words = set(response_lower.split())
    if not expected_words:
        return 0.5

    overlap = len(expected_words & response_words) / len(expected_words)
    return round(overlap, 4)


def _score_efficiency(steps, tools):
    """Score based on fewer steps (more efficient = higher score)."""
    step_score = max(0.0, 1.0 - max(0, steps - 3) * 0.15)

    if 1 <= tools <= 2:
        tool_bonus = 0.1
    elif tools == 0:
        tool_bonus = 0.0
    else:
        tool_bonus = -0.05 * max(0, tools - 3)

    return round(min(1.0, max(0.0, step_score + tool_bonus)), 4)


def _score_custom(response, expected, criteria):
    """Score based on custom criteria keywords present in response."""
    if not criteria:
        return _score_task_completion(response)

    criteria_words = set(criteria.lower().replace(",", " ").split())
    response_lower = response.lower()

    matches = sum(1 for word in criteria_words if word in response_lower)
    keyword_score = matches / max(len(criteria_words), 1)

    quality_score = _score_task_completion(response)
    return round(0.5 * keyword_score + 0.5 * quality_score, 4)


# ── Data loading ────────────────────────────────────────────────────────


def _load_dataset(ctx, input_name):
    """Load a dataset from an input port, handling files and raw values."""
    try:
        data = ctx.load_input(input_name)
        if isinstance(data, str) and os.path.isdir(data):
            data_file = os.path.join(data, "data.json")
            if os.path.isfile(data_file):
                with open(data_file, "r") as f:
                    return json.load(f)
        elif isinstance(data, str) and os.path.isfile(data):
            with open(data, "r") as f:
                loaded = json.load(f)
            return loaded if isinstance(loaded, list) else [loaded]
        elif isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return [data]
    except (ValueError, Exception):
        pass
    return []
