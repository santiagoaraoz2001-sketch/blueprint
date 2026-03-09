"""Checkpoint Gate — evaluate metrics against configurable thresholds to pass or block execution."""

import json
import os


def _resolve_input(raw):
    """Resolve an input value that might be a file path or directory to a Python object."""
    if raw is None:
        return None
    if isinstance(raw, str):
        if os.path.isfile(raw):
            with open(raw, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except (json.JSONDecodeError, ValueError):
                    return raw
        if os.path.isdir(raw):
            data_file = os.path.join(raw, "data.json")
            if os.path.isfile(data_file):
                with open(data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw
    return raw


_OPERATORS = {
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: abs(a - b) < 1e-9,
    "!=": lambda a, b: abs(a - b) >= 1e-9,
}


def _evaluate_condition(metric_value, operator, threshold):
    """Evaluate a single metric condition. Returns (passed: bool, description: str)."""
    fn = _OPERATORS.get(operator)
    if fn is None:
        return metric_value >= threshold, f"(unknown op '{operator}', used >=)"
    passed = fn(metric_value, threshold)
    return passed, f"{metric_value} {operator} {threshold} → {'PASS' if passed else 'FAIL'}"


def run(ctx):
    metric_name = ctx.config.get("metric_name", "accuracy")
    threshold = float(ctx.config.get("threshold", 0.8))
    operator = ctx.config.get("operator", ">=")
    on_fail = ctx.config.get("on_fail", "route_fail")
    additional_checks = ctx.config.get("additional_checks", "").strip()
    label = ctx.config.get("label", "checkpoint")
    match_mode = ctx.config.get("match_mode", "all").lower().strip()
    report_detail = ctx.config.get("report_detail", "detailed").lower().strip()

    ctx.log_message(f"Checkpoint Gate [{label}]: checking '{metric_name}' {operator} {threshold} (match_mode={match_mode})")
    ctx.report_progress(0, 3)

    # ---- Step 1: Load data and metrics ----
    ctx.report_progress(1, 3)

    # Load primary data (pass-through)
    raw_data = None
    try:
        raw_data = ctx.load_input("data")
    except (ValueError, Exception):
        pass
    data = _resolve_input(raw_data)

    # Load metrics — can come from dedicated port or be embedded in data
    raw_metrics = None
    try:
        raw_metrics = ctx.load_input("metrics")
    except (ValueError, Exception):
        pass
    metrics = _resolve_input(raw_metrics)

    # If no dedicated metrics input, try to extract from data
    if metrics is None and isinstance(data, dict):
        metrics = data
    if not isinstance(metrics, dict):
        metrics = {}

    ctx.log_message(f"Available metric keys: {list(metrics.keys())}")

    # ---- Step 2: Evaluate conditions ----
    ctx.report_progress(2, 3)

    results = []

    # Primary metric check
    metric_value = metrics.get(metric_name)
    if metric_value is None:
        ctx.log_message(f"WARNING: metric '{metric_name}' not found in input")
        results.append({
            "metric": metric_name, "value": None, "operator": operator,
            "threshold": threshold, "passed": False, "reason": "metric not found",
        })
    else:
        metric_value = float(metric_value)
        passed, desc = _evaluate_condition(metric_value, operator, threshold)
        ctx.log_message(f"  {metric_name}: {desc}")
        results.append({
            "metric": metric_name, "value": metric_value, "operator": operator,
            "threshold": threshold, "passed": passed,
        })
        ctx.log_metric(metric_name, metric_value)

    # Additional checks (format: "metric_name operator threshold" per line)
    if additional_checks:
        for line in additional_checks.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) != 3:
                ctx.log_message(f"  Skipping malformed check: '{line}' (expected: name operator threshold)")
                continue
            m_name, m_op, m_thresh = parts[0], parts[1], parts[2]
            try:
                m_thresh = float(m_thresh)
            except ValueError:
                ctx.log_message(f"  Skipping check '{m_name}': invalid threshold '{m_thresh}'")
                continue
            m_value = metrics.get(m_name)
            if m_value is None:
                ctx.log_message(f"  {m_name}: NOT FOUND → FAIL")
                results.append({
                    "metric": m_name, "value": None, "operator": m_op,
                    "threshold": m_thresh, "passed": False, "reason": "metric not found",
                })
            else:
                m_value = float(m_value)
                m_passed, m_desc = _evaluate_condition(m_value, m_op, m_thresh)
                ctx.log_message(f"  {m_name}: {m_desc}")
                results.append({
                    "metric": m_name, "value": m_value, "operator": m_op,
                    "threshold": m_thresh, "passed": m_passed,
                })
                ctx.log_metric(m_name, m_value)

    # Overall gate decision based on match_mode
    if match_mode == "any":
        gate_passed = any(r["passed"] for r in results)
    else:
        gate_passed = all(r["passed"] for r in results)

    # ---- Step 3: Route outputs ----
    ctx.report_progress(3, 3)

    gate_report = {
        "label": label,
        "gate_passed": gate_passed,
        "total_checks": len(results),
        "passed_checks": sum(1 for r in results if r["passed"]),
        "failed_checks": sum(1 for r in results if not r["passed"]),
    }
    if report_detail == "detailed":
        gate_report["checks"] = results
    else:
        # Summary mode: only include failed check names
        gate_report["failed_metrics"] = [r["metric"] for r in results if not r["passed"]]

    # Write gate report
    report_path = os.path.join(ctx.run_dir, "gate_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(gate_report, f, indent=2, default=str)

    if gate_passed:
        ctx.log_message(f"GATE PASSED [{label}]: all {len(results)} check(s) passed")
        ctx.save_output("passed", data if data is not None else metrics)
        ctx.save_output("rejected", None)
    else:
        failed = [r for r in results if not r["passed"]]
        ctx.log_message(
            f"GATE FAILED [{label}]: {len(failed)}/{len(results)} check(s) failed"
        )
        if on_fail == "route_fail":
            ctx.save_output("passed", None)
            ctx.save_output("rejected", data if data is not None else metrics)
        elif on_fail == "warn_continue":
            ctx.log_message("Action: WARNING only — passing data through 'passed' port anyway")
            ctx.save_output("passed", data if data is not None else metrics)
            ctx.save_output("rejected", None)
        elif on_fail == "stop_pipeline":
            ctx.save_output("passed", None)
            ctx.save_output("rejected", data if data is not None else metrics)
            raise RuntimeError(
                f"Checkpoint Gate [{label}] BLOCKED pipeline: "
                f"{len(failed)} check(s) failed — {', '.join(r['metric'] for r in failed)}"
            )

    ctx.save_output("report", gate_report)
    ctx.save_artifact("gate_report", report_path)
    ctx.log_metric("gate_passed", 1.0 if gate_passed else 0.0)
    ctx.log_metric("checks_total", len(results))
    ctx.log_metric("checks_passed", sum(1 for r in results if r["passed"]))
    ctx.log_message("Checkpoint Gate complete.")
