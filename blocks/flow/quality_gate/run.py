"""Quality Gate — auto-check data and metrics against configurable thresholds."""

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
}


def _compute_data_quality_metrics(data):
    """Compute basic data quality metrics from the data itself."""
    metrics = {}

    if isinstance(data, list):
        metrics["row_count"] = len(data)
        if data and isinstance(data[0], dict):
            metrics["column_count"] = len(data[0].keys())
            # Compute null ratio across all fields
            total_cells = 0
            null_cells = 0
            for row in data:
                if isinstance(row, dict):
                    for v in row.values():
                        total_cells += 1
                        if v is None or v == "" or v == "null":
                            null_cells += 1
            metrics["null_ratio"] = null_cells / max(total_cells, 1)
            metrics["total_cells"] = total_cells

            # Check for duplicate rows (by string repr)
            seen = set()
            dupes = 0
            for row in data:
                key = json.dumps(row, sort_keys=True, default=str)
                if key in seen:
                    dupes += 1
                seen.add(key)
            metrics["duplicate_count"] = dupes
            metrics["duplicate_ratio"] = dupes / max(len(data), 1)

    elif isinstance(data, dict):
        metrics["key_count"] = len(data)
        null_count = sum(1 for v in data.values() if v is None or v == "" or v == "null")
        metrics["null_ratio"] = null_count / max(len(data), 1)

    elif isinstance(data, str):
        metrics["char_count"] = len(data)
        metrics["word_count"] = len(data.split())
        metrics["line_count"] = data.count("\n") + 1

    return metrics


def run(ctx):
    metric_name = ctx.config.get("metric_name", "accuracy")
    threshold = float(ctx.config.get("threshold", 0.8))
    operator = ctx.config.get("operator", ">=")
    on_fail = ctx.config.get("on_fail", "route_rejected")
    auto_compute_quality = ctx.config.get("auto_compute_quality", True)
    additional_checks = ctx.config.get("additional_checks", "").strip()
    match_mode = ctx.config.get("match_mode", "all").lower().strip()
    required_columns = ctx.config.get("required_columns", "").strip()
    report_detail = ctx.config.get("report_detail", "detailed").lower().strip()

    ctx.log_message(f"Quality Gate: checking '{metric_name}' {operator} {threshold}")
    ctx.report_progress(0, 3)

    # ---- Step 1: Load inputs ----
    ctx.report_progress(1, 3)
    raw_data = ctx.load_input("data")
    if raw_data is None:
        raise ValueError("No data provided. Connect a 'data' input.")
    data = _resolve_input(raw_data)

    # Load optional metrics input
    raw_metrics = None
    try:
        raw_metrics = ctx.load_input("metrics")
    except (ValueError, Exception):
        pass
    metrics = _resolve_input(raw_metrics)
    if not isinstance(metrics, dict):
        metrics = {}

    # Auto-compute data quality metrics
    if auto_compute_quality:
        computed = _compute_data_quality_metrics(data)
        ctx.log_message(f"Auto-computed quality metrics: {list(computed.keys())}")
        # Computed metrics have lower priority than provided metrics
        for k, v in computed.items():
            if k not in metrics:
                metrics[k] = v

    # If data is a dict, merge its numeric fields as available metrics
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (int, float)) and k not in metrics:
                metrics[k] = v

    ctx.log_message(f"Available metrics: {list(metrics.keys())}")

    # ---- Step 2: Evaluate checks ----
    ctx.report_progress(2, 3)
    results = []

    # Schema validation: required columns check
    if required_columns and isinstance(data, list) and data and isinstance(data[0], dict):
        req_cols = [c.strip() for c in required_columns.split(",") if c.strip()]
        actual_cols = set(data[0].keys())
        missing_cols = [c for c in req_cols if c not in actual_cols]
        if missing_cols:
            ctx.log_message(f"  required_columns: MISSING {missing_cols} → FAIL")
            results.append({
                "metric": "required_columns", "value": None,
                "operator": "present", "threshold": req_cols,
                "passed": False, "reason": f"missing columns: {missing_cols}",
            })
        else:
            ctx.log_message(f"  required_columns: all {len(req_cols)} present → PASS")
            results.append({
                "metric": "required_columns", "value": len(req_cols),
                "operator": "present", "threshold": req_cols, "passed": True,
            })

    # Primary check
    metric_value = metrics.get(metric_name)
    if metric_value is not None:
        metric_value = float(metric_value)
        op_fn = _OPERATORS.get(operator, _OPERATORS[">="])
        passed = op_fn(metric_value, threshold)
        ctx.log_message(f"  {metric_name}: {metric_value} {operator} {threshold} → {'PASS' if passed else 'FAIL'}")
        results.append({
            "metric": metric_name, "value": metric_value,
            "operator": operator, "threshold": threshold, "passed": passed,
        })
        ctx.log_metric(metric_name, metric_value)
    else:
        ctx.log_message(f"  WARNING: metric '{metric_name}' not found — FAIL")
        results.append({
            "metric": metric_name, "value": None,
            "operator": operator, "threshold": threshold,
            "passed": False, "reason": "metric not found",
        })

    # Additional checks (format: "metric_name operator threshold" per line)
    if additional_checks:
        for line in additional_checks.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) != 3:
                ctx.log_message(f"  Skipping malformed check: '{line}'")
                continue
            m_name, m_op, m_thresh = parts[0], parts[1], parts[2]
            try:
                m_thresh = float(m_thresh)
            except ValueError:
                continue
            m_value = metrics.get(m_name)
            if m_value is not None:
                m_value = float(m_value)
                m_fn = _OPERATORS.get(m_op, _OPERATORS[">="])
                m_passed = m_fn(m_value, m_thresh)
                ctx.log_message(f"  {m_name}: {m_value} {m_op} {m_thresh} → {'PASS' if m_passed else 'FAIL'}")
                results.append({
                    "metric": m_name, "value": m_value,
                    "operator": m_op, "threshold": m_thresh, "passed": m_passed,
                })
                ctx.log_metric(m_name, m_value)
            else:
                ctx.log_message(f"  {m_name}: NOT FOUND → FAIL")
                results.append({
                    "metric": m_name, "value": None,
                    "operator": m_op, "threshold": m_thresh,
                    "passed": False, "reason": "metric not found",
                })

    if match_mode == "any":
        gate_passed = any(r["passed"] for r in results)
    else:
        gate_passed = all(r["passed"] for r in results)

    # ---- Step 3: Route outputs ----
    ctx.report_progress(3, 3)

    report = {
        "gate_passed": gate_passed,
        "total_checks": len(results),
        "passed_checks": sum(1 for r in results if r["passed"]),
        "failed_checks": sum(1 for r in results if not r["passed"]),
    }
    if report_detail == "detailed":
        report["checks"] = results
        report["all_metrics"] = {k: v for k, v in metrics.items() if isinstance(v, (int, float))}
    else:
        report["failed_metrics"] = [r["metric"] for r in results if not r["passed"]]

    report_path = os.path.join(ctx.run_dir, "quality_gate_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    if gate_passed:
        ctx.log_message(f"QUALITY GATE PASSED: {report['passed_checks']}/{report['total_checks']} checks passed")
        ctx.save_output("passed", data)
        ctx.save_output("rejected", None)
    else:
        failed_names = [r["metric"] for r in results if not r["passed"]]
        ctx.log_message(f"QUALITY GATE FAILED: {', '.join(failed_names)}")

        if on_fail == "route_rejected":
            ctx.save_output("passed", None)
            ctx.save_output("rejected", data)
        elif on_fail == "warn_continue":
            ctx.log_message("Action: WARNING only — data passed through")
            ctx.save_output("passed", data)
            ctx.save_output("rejected", None)
        elif on_fail == "stop_pipeline":
            ctx.save_output("passed", None)
            ctx.save_output("rejected", data)
            raise RuntimeError(f"Quality Gate BLOCKED pipeline: failed checks — {', '.join(failed_names)}")

    ctx.save_output("gate_metrics", report)
    ctx.save_artifact("quality_gate_report", report_path)
    ctx.log_metric("gate_passed", 1.0 if gate_passed else 0.0)
    ctx.log_message("Quality Gate complete.")
