"""HumanEval — code generation benchmark evaluation.

Loads official HumanEval problems, generates completions using the
connected model, and evaluates functional correctness via pass@k.
Falls back to realistic simulation when human_eval package is not installed.
"""

import json
import os
import random
import time


def run(ctx):
    # ── Configuration ─────────────────────────────────────────────────────
    model_name = ctx.config.get("model_name", "")
    num_problems = int(ctx.config.get("num_problems", 164))
    temperature = float(ctx.config.get("temperature", 0.8))
    k_values_str = ctx.config.get("k_values", "1,10,100")
    num_samples_per = int(ctx.config.get("num_samples_per_problem", 0))
    timeout = float(ctx.config.get("timeout", 5.0))
    seed = int(ctx.config.get("seed", 42))
    max_new_tokens = int(ctx.config.get("max_new_tokens", 256))
    inference_timeout = int(ctx.config.get("inference_timeout", 30))

    # ── Output format config ───────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "json")
    decimal_precision = int(ctx.config.get("decimal_precision", 4))


    random.seed(seed)

    k_values = [int(k.strip()) for k in k_values_str.split(",") if k.strip()]

    # ── Resolve model from input ──────────────────────────────────────────
    model_info_dict = None
    try:
        model_info = ctx.load_input("model")
        if isinstance(model_info, dict):
            model_info_dict = model_info
            model_name = model_name or model_info.get("model_name",
                         model_info.get("model_id", ""))
        elif isinstance(model_info, str):
            model_name = model_name or model_info
    except (ValueError, Exception):
        pass

    # Auto samples: generate max(k) samples per problem
    if num_samples_per <= 0:
        num_samples_per = max(k_values) if k_values else 1

    ctx.log_message(f"HumanEval: {model_name or '(simulation)'}")
    ctx.log_message(f"Problems: {num_problems}, k={k_values}, temp={temperature}")
    ctx.log_message(f"Samples per problem: {num_samples_per}")

    # ── Try real evaluation ───────────────────────────────────────────────
    try:
        from human_eval.data import read_problems, write_jsonl
        from human_eval.evaluation import evaluate_functional_correctness

        ctx.log_message("human-eval package found — running real evaluation")
        _run_real_eval(ctx, model_name, model_info_dict, num_problems,
                       temperature, k_values, num_samples_per, timeout,
                       max_new_tokens, inference_timeout)
        return
    except ImportError:
        ctx.log_message("human-eval not installed (pip install human-eval) — running simulation")

    # ── Simulation fallback ───────────────────────────────────────────────
    _run_simulation(ctx, model_name, num_problems, temperature, k_values, seed)


def _run_real_eval(ctx, model_name, model_info_dict, num_problems,
                   temperature, k_values, num_samples_per, timeout,
                   max_new_tokens=256, inference_timeout=30):
    """Run actual HumanEval evaluation."""
    from human_eval.data import read_problems, write_jsonl
    from human_eval.evaluation import evaluate_functional_correctness

    problems = read_problems()
    problem_ids = list(problems.keys())[:num_problems]
    ctx.log_message(f"Loaded {len(problem_ids)} problems")

    generate_fn = _get_generate_fn(model_info_dict, model_name,
                                   max_new_tokens, inference_timeout)

    samples = []
    for i, task_id in enumerate(problem_ids):
        prompt = problems[task_id]["prompt"]
        for _ in range(num_samples_per):
            completion = generate_fn(prompt, temperature)
            samples.append({"task_id": task_id, "completion": completion})

        if (i + 1) % 20 == 0:
            ctx.log_message(f"  Generated {i + 1}/{len(problem_ids)} problems")
        ctx.report_progress(i + 1, len(problem_ids) * 2)

    completions_file = os.path.join(ctx.run_dir, "completions.jsonl")
    write_jsonl(completions_file, samples)

    ctx.log_message("Evaluating functional correctness...")
    results = evaluate_functional_correctness(
        completions_file, k=k_values, n_workers=4, timeout=timeout,
    )

    pass_at_k = {}
    for key, val in results.items():
        if key.startswith("pass@"):
            pass_at_k[key] = round(val, 4)

    ctx.log_message("HumanEval Results:")
    for key, score in sorted(pass_at_k.items()):
        ctx.log_message(f"  {key}: {score:.1%}")

    metrics = {
        **pass_at_k,
        "num_problems": len(problem_ids),
        "total_samples": len(samples),
        "model": model_name,
        "temperature": temperature,
        "demo_mode": False,
    }

    _save_results(ctx, metrics, pass_at_k, [])


def _run_simulation(ctx, model_name, num_problems, temperature, k_values, seed):
    """Simulation fallback when human_eval is not installed."""
    demo_problems = [
        {"task_id": f"HumanEval/{i}", "difficulty": random.choice(["easy", "medium", "hard"])}
        for i in range(min(num_problems, 164))
    ]

    base_quality = random.uniform(0.3, 0.7)
    problem_results = []

    for i, problem in enumerate(demo_problems):
        diff_mod = {"easy": 0.2, "medium": 0.0, "hard": -0.2}[problem["difficulty"]]
        pass_prob = max(0.05, min(0.95, base_quality + diff_mod + random.gauss(0, 0.1)))

        attempts = {}
        for k in k_values:
            pass_at_k_prob = 1.0 - (1.0 - pass_prob) ** k
            attempts[f"pass@{k}"] = random.random() < pass_at_k_prob

        problem_results.append({
            "task_id": problem["task_id"],
            "difficulty": problem["difficulty"],
            **attempts,
        })

        if (i + 1) % 20 == 0:
            ctx.log_message(f"  Evaluated {i + 1}/{len(demo_problems)} problems")
        ctx.report_progress(i + 1, len(demo_problems))
        time.sleep(0.01)

    pass_at_k = {}
    for k in k_values:
        key = f"pass@{k}"
        passed = sum(1 for r in problem_results if r.get(key, False))
        pass_at_k[key] = round(passed / max(len(problem_results), 1), 4)

    ctx.log_message("HumanEval Results (simulated):")
    for key, score in sorted(pass_at_k.items()):
        ctx.log_message(f"  {key}: {score:.1%}")

    for diff in ["easy", "medium", "hard"]:
        subset = [r for r in problem_results if r["difficulty"] == diff]
        if subset:
            pass1 = sum(1 for r in subset if r.get("pass@1", False)) / len(subset)
            ctx.log_message(f"  {diff}: pass@1={pass1:.1%} ({len(subset)} problems)")

    metrics = {
        **pass_at_k,
        "num_problems": len(problem_results),
        "model": model_name,
        "temperature": temperature,
        "demo_mode": True,
    }

    _save_results(ctx, metrics, pass_at_k, problem_results)


def _save_results(ctx, metrics, pass_at_k, problem_results):
    """Save outputs and artifacts."""
    results_path = os.path.join(ctx.run_dir, "human_eval_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({"metrics": metrics, "results": problem_results}, f, indent=2)
    ctx.save_artifact("human_eval_results", results_path)


    # ── Save dataset output ────────────────────────────────────────────
    if results_data:
        _ds_dir = os.path.join(ctx.run_dir, "dataset_out")
        os.makedirs(_ds_dir, exist_ok=True)
        _rows = results_data if isinstance(results_data, list) else [results_data]
        for _r in _rows:
            if isinstance(_r, dict):
                for _k, _v in _r.items():
                    if isinstance(_v, float):
                        _r[_k] = round(_v, decimal_precision)
        if output_format == "csv" and _rows and isinstance(_rows[0], dict):
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
    for key, score in pass_at_k.items():
        ctx.log_metric(key, score)
    ctx.log_metric("num_problems", metrics.get("num_problems", 0))
    ctx.report_progress(1, 1)


def _get_generate_fn(model_info, model_name, max_new_tokens=256, inference_timeout=30):
    """Return a function that generates code completions."""
    if model_info and model_info.get("source") == "ollama":
        import urllib.request

        def generate_ollama(prompt, temperature):
            try:
                payload = json.dumps({
                    "model": model_info.get("model_name", model_name),
                    "prompt": prompt, "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_new_tokens},
                }).encode("utf-8")
                req = urllib.request.Request(
                    f"{model_info.get('endpoint', 'http://localhost:11434')}/api/generate",
                    data=payload, headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=inference_timeout) as resp:
                    return json.loads(resp.read().decode("utf-8")).get("response", "pass")
            except Exception:
                return "pass  # generation failed"
        return generate_ollama

    if model_info and model_info.get("source") == "huggingface":
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM
            import torch

            hf_id = model_info.get("model_id", model_name)
            tokenizer = AutoTokenizer.from_pretrained(hf_id)
            model = AutoModelForCausalLM.from_pretrained(hf_id)
            model.eval()

            def generate_hf(prompt, temperature):
                inputs = tokenizer(prompt, return_tensors="pt")
                with torch.no_grad():
                    outputs = model.generate(
                        **inputs, max_new_tokens=max_new_tokens,
                        temperature=max(temperature, 0.01),
                        do_sample=temperature > 0,
                    )
                return tokenizer.decode(outputs[0], skip_special_tokens=True)[len(prompt):]
            return generate_hf
        except Exception:
            pass

    def generate_stub(prompt, temperature):
        return "pass  # placeholder"
    return generate_stub
