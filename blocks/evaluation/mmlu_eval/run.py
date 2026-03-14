"""MMLU Evaluation — Massive Multitask Language Understanding benchmark.

Evaluates model knowledge across 57 academic subjects grouped into 4
categories: STEM, Humanities, Social Sciences, and Other. Uses the
EleutherAI lm-evaluation-harness for standardized, reproducible results.
"""

import json
import os


# Subject-to-category mapping
CATEGORY_SUBJECTS = {
    "stem": [
        "abstract_algebra", "astronomy", "college_biology", "college_chemistry",
        "college_computer_science", "college_mathematics", "college_physics",
        "computer_security", "conceptual_physics", "electrical_engineering",
        "elementary_mathematics", "high_school_biology", "high_school_chemistry",
        "high_school_computer_science", "high_school_mathematics",
        "high_school_physics", "high_school_statistics", "machine_learning",
    ],
    "humanities": [
        "formal_logic", "high_school_european_history", "high_school_us_history",
        "high_school_world_history", "international_law", "jurisprudence",
        "logical_fallacies", "moral_disputes", "moral_scenarios", "philosophy",
        "prehistory", "professional_law", "world_religions",
    ],
    "social_sciences": [
        "econometrics", "high_school_geography", "high_school_government_and_politics",
        "high_school_macroeconomics", "high_school_microeconomics",
        "high_school_psychology", "human_sexuality", "professional_psychology",
        "public_relations", "security_studies", "sociology", "us_foreign_policy",
    ],
    "other": [
        "anatomy", "business_ethics", "clinical_knowledge", "college_medicine",
        "global_facts", "human_aging", "management", "marketing",
        "medical_genetics", "miscellaneous", "nutrition",
        "professional_accounting", "professional_medicine", "virology",
    ],
}


def run(ctx):
    # ── Configuration ─────────────────────────────────────────────────────
    model_name = ctx.config.get("model_name", "")
    num_fewshot = int(ctx.config.get("num_fewshot", 5))
    subjects_str = ctx.config.get("subjects", "all")
    batch_size = ctx.config.get("batch_size", "auto")
    limit = int(ctx.config.get("limit", 0)) or None
    seed = int(ctx.config.get("seed", 42))
    device = ctx.config.get("device", "auto")
    trust_remote = ctx.config.get("trust_remote_code", "")

    # ── Output format config ───────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "json")
    decimal_precision = int(ctx.config.get("decimal_precision", 4))


    # ── Resolve model from input port ─────────────────────────────────────
    model_info = None
    try:
        model_info = ctx.load_input("model")
        if isinstance(model_info, dict):
            model_name = model_info.get("path",
                         model_info.get("model_name",
                         model_info.get("model_id", ""))) or model_name
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
            "Model required: connect via 'model' input port or set 'model_name' in config."
        )

    # ── Build task list ───────────────────────────────────────────────────
    if subjects_str.strip().lower() == "all":
        tasks = ["mmlu"]
    else:
        requested = [s.strip() for s in subjects_str.split(",") if s.strip()]
        tasks = [f"mmlu_{s}" for s in requested]

    # ── Resolve device ──────────────────────────────────────────────────
    if device == "auto":
        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        except ImportError as e:
            from backend.block_sdk.exceptions import BlockDependencyError
            missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
            raise BlockDependencyError(
                missing,
                f"Required library not installed: {e}",
                install_hint="pip install torch",
            )

    ctx.log_message(f"MMLU Evaluation: {model_name}")
    ctx.log_message(f"Subjects: {subjects_str}, Few-shot: {num_fewshot}, Seed: {seed}")
    if limit:
        ctx.log_message(f"Sample limit: {limit}")

    # ── Import lm-eval ────────────────────────────────────────────────────
    try:
        import lm_eval
    except ImportError:
        raise ImportError("lm-eval not installed. Install with: pip install lm-eval")

    ctx.report_progress(0, 1)

    # ── Build model_args ───────────────────────────────────────────────
    model_args = f"pretrained={model_name}"
    if trust_remote:
        model_args += ",trust_remote_code=True"

    # ── Run evaluation ────────────────────────────────────────────────────
    eval_kwargs = dict(
        model="hf",
        model_args=model_args,
        tasks=tasks,
        num_fewshot=num_fewshot,
        batch_size=batch_size,
        limit=limit,
        device=device,
    )
    if seed is not None:
        eval_kwargs["random_seed"] = seed
        eval_kwargs["numpy_random_seed"] = seed
        eval_kwargs["torch_random_seed"] = seed

    results = lm_eval.simple_evaluate(**eval_kwargs)

    # ── Extract per-subject scores ────────────────────────────────────────
    subject_scores = {}
    raw_results = results.get("results", {})

    for task_name, task_metrics in raw_results.items():
        acc = task_metrics.get("acc,none", task_metrics.get("acc", None))
        if acc is None:
            continue
        subject = task_name[len("mmlu_"):] if task_name.startswith("mmlu_") else task_name
        subject_scores[subject] = round(acc, 4)
        ctx.log_metric(f"mmlu_{subject}_acc", round(acc, 4))

    # ── Aggregate by category ─────────────────────────────────────────────
    category_scores = {}
    for cat, subjects in CATEGORY_SUBJECTS.items():
        cat_accs = [subject_scores[s] for s in subjects if s in subject_scores]
        if cat_accs:
            category_scores[cat] = round(sum(cat_accs) / len(cat_accs), 4)

    # ── Overall average ───────────────────────────────────────────────────
    overall = (round(sum(subject_scores.values()) / len(subject_scores), 4)
               if subject_scores else 0.0)

    ctx.report_progress(1, 1)

    # ── Log summary ───────────────────────────────────────────────────────
    ctx.log_message(f"\nMMLU Results:")
    ctx.log_message(f"  Overall: {overall:.1%}")
    for cat, score in sorted(category_scores.items()):
        ctx.log_message(f"  {cat}: {score:.1%}")
    ctx.log_metric("mmlu_overall", overall)
    for cat, score in category_scores.items():
        ctx.log_metric(f"mmlu_{cat}", score)

    # ── Build output ──────────────────────────────────────────────────────
    metrics = {
        "mmlu_overall": overall,
        **{f"mmlu_{cat}": score for cat, score in category_scores.items()},
        "num_subjects": len(subject_scores),
        "num_fewshot": num_fewshot,
    }

    detailed = {
        "model": model_name,
        "overall": overall,
        "category_scores": category_scores,
        "subject_scores": subject_scores,
        "num_fewshot": num_fewshot,
    }
    results_path = os.path.join(ctx.run_dir, "mmlu_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(detailed, f, indent=2)
    ctx.save_artifact("mmlu_results", results_path)

    ctx.save_output("metrics", metrics)

    # ── Save per-subject dataset output ────────────────────────────────
    _subj_rows = []
    for _cat, _subjects in CATEGORY_SUBJECTS.items():
        for _s in _subjects:
            if _s in subject_scores:
                _subj_rows.append({"subject": _s, "category": _cat, "accuracy": round(subject_scores[_s], decimal_precision)})
    _ds_dir = os.path.join(ctx.run_dir, "dataset_out")
    os.makedirs(_ds_dir, exist_ok=True)
    if output_format == "csv" and _subj_rows:
        import csv as _csv
        with open(os.path.join(_ds_dir, "data.csv"), "w", newline="", encoding="utf-8") as _f:
            _w = _csv.DictWriter(_f, fieldnames=_subj_rows[0].keys())
            _w.writeheader()
            _w.writerows(_subj_rows)
    else:
        with open(os.path.join(_ds_dir, "data.json"), "w", encoding="utf-8") as _f:
            json.dump(_subj_rows, _f, indent=2)
    ctx.save_output("dataset", _ds_dir)

    ctx.save_output("results", results_path)
    ctx.log_message(f"MMLU complete: {len(subject_scores)} subjects, overall={overall:.1%}")
