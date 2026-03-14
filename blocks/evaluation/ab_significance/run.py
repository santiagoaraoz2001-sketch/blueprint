"""A/B Significance Test — computes statistical significance between two model variants."""

import json
import os
import math


def run(ctx):
    try:
        from scipy import stats
        import numpy as np
    except ImportError as e:
        from backend.block_sdk.exceptions import BlockDependencyError
        missing = str(e).split("'")[-2] if "'" in str(e) else str(e)
        raise BlockDependencyError(
            missing,
            f"A/B significance testing requires scipy and numpy: {e}",
            install_hint="pip install scipy numpy",
        )

    metrics_a_path = ctx.load_input("metrics_a")
    metrics_b_path = ctx.load_input("metrics_b")
    metric_name = ctx.config.get("metric_name", "accuracy")
    alpha = ctx.config.get("significance_level", 0.05)
    test_type = ctx.config.get("test_type", "welch_t")
    min_samples = ctx.config.get("min_samples", 30)

    ctx.report_progress(0, 4)

    # ── 1. Load metric values ────────────────────────────────────────────
    values_a = _load_metric_values(metrics_a_path, metric_name)
    values_b = _load_metric_values(metrics_b_path, metric_name)

    # Convert to numpy float arrays — filter out any non-numeric values
    values_a = _to_numeric_array(values_a, "Branch A")
    values_b = _to_numeric_array(values_b, "Branch B")

    n_a, n_b = len(values_a), len(values_b)

    # Hard minimum: need at least 2 samples per group for std calculation
    if n_a < 2 or n_b < 2:
        raise ValueError(
            f"Need at least 2 numeric samples per group. "
            f"Got A={n_a}, B={n_b} for metric '{metric_name}'."
        )

    ctx.report_progress(1, 4)
    ctx.log_message(f"Loaded {n_a} samples (A) and {n_b} samples (B) for metric '{metric_name}'")

    # Sample size warning
    power_note = ""
    if n_a < min_samples or n_b < min_samples:
        power_note = f"Need at least {min_samples} samples per group for reliable results."
        ctx.log_message(f"WARNING: Insufficient samples. A={n_a}, B={n_b}, minimum={min_samples}")

    # ── 2. Descriptive statistics ────────────────────────────────────────
    mean_a, mean_b = float(np.mean(values_a)), float(np.mean(values_b))
    std_a, std_b = float(np.std(values_a, ddof=1)), float(np.std(values_b, ddof=1))

    ctx.report_progress(2, 4)

    # ── 3. Statistical test ──────────────────────────────────────────────
    test_stat = None

    if test_type == "welch_t":
        t_stat, p_value = stats.ttest_ind(values_a, values_b, equal_var=False)
        test_stat = float(t_stat)
        p_value = float(p_value)
    elif test_type == "mann_whitney":
        try:
            u_stat, p_value = stats.mannwhitneyu(
                values_a, values_b, alternative="two-sided"
            )
            test_stat = float(u_stat)
            p_value = float(p_value)
        except ValueError:
            # mannwhitneyu fails when all values are identical
            test_stat = 0.0
            p_value = 1.0
    elif test_type == "bootstrap":
        p_value = _bootstrap_test(values_a, values_b, n_bootstrap=10000)
    else:
        t_stat, p_value = stats.ttest_ind(values_a, values_b, equal_var=False)
        test_stat = float(t_stat)
        p_value = float(p_value)

    # Guard against NaN p-values (e.g. both groups have zero variance)
    if math.isnan(p_value):
        p_value = 1.0
        ctx.log_message("WARNING: p-value is NaN (likely zero variance in both groups). Treating as non-significant.")

    # ── 4. Effect size & confidence interval ─────────────────────────────
    # Cohen's d with pooled standard deviation
    denom = n_a + n_b - 2
    if denom > 0:
        pooled_var = ((n_a - 1) * std_a**2 + (n_b - 1) * std_b**2) / denom
        pooled_std = math.sqrt(pooled_var)
    else:
        pooled_std = 0.0

    cohens_d = (mean_a - mean_b) / pooled_std if pooled_std > 0 else 0.0

    # Welch–Satterthwaite degrees of freedom for the CI
    var_a = std_a**2 / n_a if n_a > 0 else 0
    var_b = std_b**2 / n_b if n_b > 0 else 0
    se_diff = math.sqrt(var_a + var_b)

    if se_diff > 0 and var_a + var_b > 0:
        df_num = (var_a + var_b) ** 2
        df_den_a = (var_a**2 / (n_a - 1)) if n_a > 1 else 0
        df_den_b = (var_b**2 / (n_b - 1)) if n_b > 1 else 0
        df_den = df_den_a + df_den_b
        df = df_num / df_den if df_den > 0 else max(n_a, n_b) - 1
        t_crit = stats.t.ppf(1 - alpha / 2, df)
    else:
        t_crit = 1.96  # fallback when se is zero (identical values)

    mean_diff = mean_a - mean_b
    ci_lower = mean_diff - t_crit * se_diff
    ci_upper = mean_diff + t_crit * se_diff

    ctx.report_progress(3, 4)

    # ── 5. Verdict ───────────────────────────────────────────────────────
    significant = p_value < alpha
    if significant:
        winner = "A" if mean_a > mean_b else "B"
        verdict = (
            f"Branch {winner} is significantly better "
            f"(p={p_value:.4f}, d={abs(cohens_d):.3f})"
        )
    else:
        verdict = (
            f"No significant difference (p={p_value:.4f}). "
            f"Need more samples or effect is too small."
        )

    if power_note:
        verdict += f" Note: {power_note}"

    # Effect size interpretation (Cohen's conventions)
    abs_d = abs(cohens_d)
    if abs_d < 0.2:
        effect_label = "negligible"
    elif abs_d < 0.5:
        effect_label = "small"
    elif abs_d < 0.8:
        effect_label = "medium"
    else:
        effect_label = "large"

    # ── 6. Build & save report ───────────────────────────────────────────
    report = {
        "metric": metric_name,
        "test_type": test_type,
        "alpha": alpha,
        "branch_a": {
            "n": n_a,
            "mean": round(mean_a, 6),
            "std": round(std_a, 6),
        },
        "branch_b": {
            "n": n_b,
            "mean": round(mean_b, 6),
            "std": round(std_b, 6),
        },
        "test_statistic": round(test_stat, 6) if test_stat is not None else None,
        "p_value": round(p_value, 6),
        "cohens_d": round(cohens_d, 4),
        "effect_size": effect_label,
        "significant": significant,
        "confidence_interval_95": [round(ci_lower, 6), round(ci_upper, 6)],
        "verdict": verdict,
    }

    report_path = os.path.join(ctx.run_dir, "ab_significance_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Emit live metrics
    ctx.log_metric("p_value", p_value)
    ctx.log_metric("cohens_d", abs(cohens_d))
    ctx.log_metric("significant", 1.0 if significant else 0.0)
    ctx.log_metric("mean_diff", mean_diff)

    ctx.save_output("report", report_path)
    ctx.save_output("verdict", verdict)
    ctx.report_progress(4, 4)
    ctx.log_message(verdict)


# ── Helpers ──────────────────────────────────────────────────────────────


def _to_numeric_array(values, label):
    """Convert a list of values to a numpy float64 array, filtering non-numeric entries."""
    import numpy as np
    numeric = []
    skipped = 0
    for v in values:
        if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)):
            numeric.append(float(v))
        else:
            skipped += 1
    if skipped > 0 and len(numeric) > 0:
        # Log but don't fail — partial data is still usable
        pass
    if not numeric:
        raise ValueError(
            f"{label}: No valid numeric values found. "
            f"Got {len(values)} entries but none were numeric."
        )
    return np.array(numeric, dtype=np.float64)


def _load_metric_values(source, metric_name):
    """Load metric values from a JSON/JSONL file, list, or dict.

    Supported formats:
      - Python list of numbers: [0.85, 0.87, ...]
      - Python list of dicts: [{"accuracy": 0.85}, ...]
      - Python dict with metric key: {"accuracy": [0.85, 0.87]}
      - JSON file containing any of the above
      - JSONL file (one JSON object per line)
      - Directory containing data.json
    """
    if isinstance(source, list):
        return _extract_from_list(source, metric_name)

    if isinstance(source, dict):
        return _extract_from_dict(source, metric_name)

    if isinstance(source, str):
        return _load_from_path(source, metric_name)

    raise ValueError(
        f"Unsupported input type: {type(source).__name__}. "
        f"Expected list, dict, or file path string."
    )


def _extract_from_list(data, metric_name):
    """Extract metric values from a list of dicts or scalars."""
    return [d.get(metric_name, d) if isinstance(d, dict) else d for d in data]


def _extract_from_dict(data, metric_name):
    """Extract metric values from a dict — look for the metric key."""
    if metric_name in data:
        val = data[metric_name]
        return val if isinstance(val, list) else [val]
    # If the metric key isn't present, check if values are numeric lists
    for key, val in data.items():
        if isinstance(val, list) and val and isinstance(val[0], (int, float)):
            return val
    # Last resort: single dict with no matching key
    return list(data.values())


def _load_from_path(path, metric_name):
    """Load metric values from a file path or directory."""
    if os.path.isdir(path):
        data_file = os.path.join(path, "data.json")
        if os.path.isfile(data_file):
            path = data_file
        else:
            # Try any .json file in the directory
            json_files = [f for f in os.listdir(path) if f.endswith(".json")]
            if json_files:
                path = os.path.join(path, json_files[0])
            else:
                raise FileNotFoundError(
                    f"No JSON files found in directory: {path}"
                )

    if not os.path.isfile(path):
        raise FileNotFoundError(f"Metrics file not found: {path}")

    # Try JSONL first (one JSON object per line)
    if path.endswith(".jsonl"):
        return _load_jsonl(path, metric_name)

    with open(path) as f:
        content = f.read().strip()

    # Detect JSONL: multiple lines that each start with { or [
    lines = content.split("\n")
    if len(lines) > 1 and all(ln.strip().startswith(("{", "[")) for ln in lines if ln.strip()):
        return _load_jsonl_content(lines, metric_name)

    data = json.loads(content)
    if isinstance(data, list):
        return _extract_from_list(data, metric_name)
    if isinstance(data, dict):
        return _extract_from_dict(data, metric_name)
    return [data]


def _load_jsonl(path, metric_name):
    """Load metric values from a JSONL file."""
    with open(path) as f:
        lines = f.readlines()
    return _load_jsonl_content(lines, metric_name)


def _load_jsonl_content(lines, metric_name):
    """Parse JSONL lines into metric values."""
    values = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if isinstance(obj, dict):
            values.append(obj.get(metric_name, obj))
        else:
            values.append(obj)
    return values


def _bootstrap_test(a, b, n_bootstrap=10000):
    """Bootstrap permutation test for difference in means.

    Uses vectorized operations for performance. Deterministic via fixed seed.
    """
    import numpy as np
    rng = np.random.default_rng(42)
    observed_diff = abs(float(np.mean(a) - np.mean(b)))
    combined = np.concatenate([a, b])
    n_total = len(combined)
    n_a = len(a)

    # Vectorized: generate all permutation indices at once
    indices = np.array([rng.permutation(n_total) for _ in range(n_bootstrap)])
    perm_a_means = np.mean(combined[indices[:, :n_a]], axis=1)
    perm_b_means = np.mean(combined[indices[:, n_a:]], axis=1)
    perm_diffs = np.abs(perm_a_means - perm_b_means)

    count = int(np.sum(perm_diffs >= observed_diff))
    return count / n_bootstrap
