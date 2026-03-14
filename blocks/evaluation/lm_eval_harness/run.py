"""LM Eval Harness — evaluate models against standardized benchmarks.

Uses EleutherAI's lm-evaluation-harness for reproducible, standardized
evaluation across dozens of NLP benchmarks (HellaSwag, ARC, WinoGrande,
PIQA, BoolQ, MMLU, and more).

Supports HuggingFace, vLLM, and local-completions backends.
"""

import json
import os


def run(ctx):
    # ── Read configuration ────────────────────────────────────────────────
    tasks_str = ctx.config.get("tasks", "hellaswag,arc_easy")
    num_fewshot = int(ctx.config.get("num_fewshot", 0))
    batch_size = ctx.config.get("batch_size", "auto")
    model_name = ctx.config.get("model_name", "")
    model_backend = ctx.config.get("model_backend", "hf")
    device = ctx.config.get("device", "auto")
    limit = int(ctx.config.get("limit", 0)) or None
    trust_remote = ctx.config.get("trust_remote_code", "")

    # ── Output format config ───────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "json")
    decimal_precision = int(ctx.config.get("decimal_precision", 4))


    # ── Resolve model from input port (takes priority) ────────────────────
    model_info = None
    try:
        model_info = ctx.load_input("model")
        if isinstance(model_info, dict):
            model_name = model_info.get("path",
                         model_info.get("model_name",
                         model_info.get("model_id", ""))) or model_name
            # Detect backend from upstream source
            source = model_info.get("source", "")
            if source == "ollama":
                model_backend = "local-completions"
            elif source == "vllm":
                model_backend = "vllm"
        elif isinstance(model_info, str):
            model_name = model_info or model_name
    except (ValueError, Exception):
        pass

    # ── Resolve trust_remote_code: config first, then model metadata ──────
    if trust_remote is None or trust_remote == "":
        if isinstance(model_info, dict):
            trust_remote = model_info.get("trust_remote_code", False)
        else:
            trust_remote = False
    if isinstance(trust_remote, str):
        trust_remote = trust_remote.lower() in ("true", "1", "yes")

    if not model_name:
        raise ValueError(
            "Model required: connect a model via the 'model' input port "
            "or set 'model_name' in config."
        )

    tasks = [t.strip() for t in tasks_str.split(",") if t.strip()]
    if not tasks:
        raise ValueError("No tasks specified. Provide comma-separated task names.")

    # ── Resolve device ────────────────────────────────────────────────────
    if device == "auto":
        device = _detect_device()

    ctx.log_message(f"Model: {model_name}")
    ctx.log_message(f"Backend: {model_backend}, Device: {device}")
    ctx.log_message(f"Tasks ({len(tasks)}): {', '.join(tasks)}")
    ctx.log_message(f"Few-shot: {num_fewshot}, Batch size: {batch_size}")
    if limit:
        ctx.log_message(f"Sample limit: {limit} per task")

    # ── Import lm-eval ────────────────────────────────────────────────────
    try:
        import lm_eval
    except ImportError:
        ctx.log_message("lm-eval not installed; running in plan-only fallback mode")
        _run_fallback(ctx, model_name, model_backend, tasks, num_fewshot, batch_size, device, limit)
        return

    ctx.report_progress(0, len(tasks))

    # ── Build model_args based on backend ─────────────────────────────────
    if model_backend == "hf":
        model_type = "hf"
        model_args = f"pretrained={model_name}"
        if device == "cuda":
            model_args += ",dtype=float16"
        elif device == "mps":
            model_args += ",dtype=float32"
        if trust_remote:
            model_args += ",trust_remote_code=True"
    elif model_backend == "vllm":
        model_type = "vllm"
        model_args = f"pretrained={model_name}"
        if trust_remote:
            model_args += ",trust_remote_code=True"
    elif model_backend == "local-completions":
        model_type = "local-completions"
        model_args = f"model={model_name}"
    else:
        model_type = "hf"
        model_args = f"pretrained={model_name}"

    # ── Run evaluation ────────────────────────────────────────────────────
    ctx.log_message("Starting evaluation...")
    results = lm_eval.simple_evaluate(
        model=model_type,
        model_args=model_args,
        tasks=tasks,
        num_fewshot=num_fewshot,
        batch_size=batch_size,
        device=device if model_backend == "hf" else None,
        limit=limit,
    )

    # ── Extract per-task results ──────────────────────────────────────────
    task_results = {}
    raw_results = results.get("results", {})

    for task_name, task_metrics in raw_results.items():
        acc = task_metrics.get("acc,none",
              task_metrics.get("acc_norm,none",
              task_metrics.get("acc", None)))
        stderr = task_metrics.get("acc_stderr,none",
                 task_metrics.get("acc_norm_stderr,none",
                 task_metrics.get("acc_stderr", None)))

        if acc is not None:
            entry = {"acc": round(acc, 4)}
            if stderr is not None:
                entry["acc_stderr"] = round(stderr, 4)
            task_results[task_name] = entry
            ctx.log_metric(f"benchmark/{task_name}/acc", round(acc, 4))
            msg = f"  {task_name}: acc={acc:.4f}"
            if stderr is not None:
                msg += f" (±{stderr:.4f})"
            ctx.log_message(msg)

    # ── Compute aggregate score ───────────────────────────────────────────
    all_accs = [v["acc"] for v in task_results.values()]
    avg_acc = round(sum(all_accs) / len(all_accs), 4) if all_accs else 0.0
    task_results["_average_acc"] = avg_acc
    ctx.log_metric("benchmark/average/acc", avg_acc)

    ctx.report_progress(len(tasks), len(tasks))

    # ── Save results artifact ─────────────────────────────────────────────
    full_results = {
        "model": model_name,
        "backend": model_backend,
        "num_fewshot": num_fewshot,
        "batch_size": batch_size,
        "limit": limit,
        "task_results": task_results,
    }
    results_path = os.path.join(ctx.run_dir, "eval_results.json")
    with open(results_path, "w") as f:
        json.dump(full_results, f, indent=2)
    ctx.save_artifact("eval_results", results_path)

    # ── Save outputs ──────────────────────────────────────────────────────
    # ── Build per-task dataset ─────────────────────────────────────────
    dataset_rows = []
    for task_name, task_data in task_results.items():
        if task_name.startswith("_"):
            continue
        if isinstance(task_data, dict):
            row = {"task": task_name}
            row.update(task_data)
            dataset_rows.append(row)
    ds_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(ds_dir, exist_ok=True)
    with open(os.path.join(ds_dir, "data.json"), "w") as f:
        json.dump(dataset_rows, f, indent=2)

    ctx.save_output("metrics", task_results)
    ctx.save_output("results", results_path)
    ctx.save_output("dataset", ds_dir)
    ctx.log_message(f"Evaluation complete: {len(task_results) - 1} tasks, avg acc={avg_acc:.4f}")


def _run_fallback(ctx, model_name, model_backend, tasks, num_fewshot, batch_size, device, limit):
    """Plan-only fallback when lm-eval is not installed.

    Generates a benchmark plan with task list, model config, and
    instructions for installing lm-eval.
    """
    ctx.log_message("Generating benchmark plan (lm-eval not available)")

    benchmark_plan = {
        "model": model_name,
        "backend": model_backend,
        "status": "plan_only",
        "message": (
            "lm-eval is not installed. This plan describes the benchmark that would run. "
            "Install with: pip install lm-eval"
        ),
        "tasks": tasks,
        "num_fewshot": num_fewshot,
        "batch_size": batch_size,
        "device": device,
        "limit": limit,
        "expected_metrics": {task: {"acc": "pending"} for task in tasks},
        "requirements": [
            "pip install lm-eval",
            f"For vLLM backend: pip install lm-eval[vllm]",
            f"Model: {model_name}",
            f"Backend: {model_backend}",
        ],
    }

    results_path = os.path.join(ctx.run_dir, "benchmark_plan.json")
    with open(results_path, "w") as f:
        json.dump(benchmark_plan, f, indent=2)

    ctx.save_artifact("benchmark_plan", results_path)

    ctx.log_message(f"Tasks: {', '.join(tasks)}")
    ctx.log_message(f"Benchmark plan saved to {results_path}")
    ctx.log_message("Install lm-eval to execute actual evaluation")

    # Build placeholder dataset
    ds_rows = [{"task": t, "acc": "pending"} for t in tasks]
    ds_dir = os.path.join(ctx.run_dir, "dataset")
    os.makedirs(ds_dir, exist_ok=True)
    with open(os.path.join(ds_dir, "data.json"), "w") as f:
        json.dump(ds_rows, f, indent=2)

    ctx.save_output("metrics", {"status": "plan_only", "tasks": tasks})
    ctx.save_output("results", results_path)
    ctx.save_output("dataset", ds_dir)
    ctx.report_progress(1, 1)


def _detect_device():
    """Auto-detect best available device."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"
