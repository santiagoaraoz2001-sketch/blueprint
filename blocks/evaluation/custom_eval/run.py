"""Custom Eval — user-defined scoring function for model outputs.

Accepts model outputs (and optional reference data), applies a
user-written scoring function, aggregates results, and produces
both a metrics summary and a detailed per-sample report.
"""

import json
import math
import os
import statistics


# Safe builtins for sandboxed execution
SAFE_BUILTINS = {
    'abs': abs, 'all': all, 'any': any, 'bool': bool,
    'dict': dict, 'enumerate': enumerate, 'float': float,
    'int': int, 'isinstance': isinstance, 'len': len,
    'list': list, 'map': map, 'max': max, 'min': min,
    'print': print, 'range': range, 'reversed': reversed,
    'round': round, 'set': set, 'sorted': sorted,
    'str': str, 'sum': sum, 'tuple': tuple, 'type': type,
    'zip': zip, 'True': True, 'False': False, 'None': None,
}

# Additional safe modules available in sandboxed mode
SAFE_MODULES = {}
try:
    import re as _re
    import math as _math
    SAFE_MODULES['re'] = _re
    SAFE_MODULES['math'] = _math
except ImportError:
    pass


def run(ctx):
    # ── Configuration ─────────────────────────────────────────────────────
    model_output = ctx.inputs.get('predictions')
    reference = ctx.inputs.get('reference')
    scoring_code = ctx.config.get('scoring_function', '')
    aggregate_method = ctx.config.get('aggregate', 'mean')
    trust_level = ctx.config.get('trust_level', 'trusted')
    error_handling = ctx.config.get('error_handling', 'skip_errors')
    max_samples = int(ctx.config.get('max_samples', 0))

    # ── Output format config ───────────────────────────────────────────────
    output_format = ctx.config.get("output_format", "json")
    decimal_precision = int(ctx.config.get("decimal_precision", 4))

    if not scoring_code.strip():
        raise ValueError(
            "scoring_function is required. Define a function like:\n"
            "def score(output, reference, idx):\n"
            "    return {'accuracy': 1.0 if output == reference else 0.0}"
        )

    # ── Compile scoring function ──────────────────────────────────────────
    local_ns = {}
    if trust_level == 'trusted':
        exec(scoring_code, {}, local_ns)
    else:
        sandbox_globals = {'__builtins__': SAFE_BUILTINS, **SAFE_MODULES}
        exec(scoring_code, sandbox_globals, local_ns)

    score_fn = local_ns.get('score')
    if not callable(score_fn):
        raise ValueError("Scoring code must define a callable 'score(output, reference, idx)'")

    # ── Load and normalize inputs ─────────────────────────────────────────
    outputs = _load_data(model_output)
    references = _load_data(reference) if reference else []

    if max_samples > 0:
        outputs = outputs[:max_samples]
        references = references[:max_samples]

    # Pad references to match outputs length
    if references and len(references) < len(outputs):
        references.extend([None] * (len(outputs) - len(references)))

    if not outputs:
        ctx.log_message("No outputs to score.")
        # Branch: no outputs to score — return early
        ctx.save_output('scores', {})
        # Branch: no outputs to score — return early
        ctx.save_output('report', os.path.join(ctx.run_dir, "eval_report.json"))
        return

    ctx.log_message(f"Scoring {len(outputs)} outputs with {len(references)} references")

    # ── Score each output ─────────────────────────────────────────────────
    all_scores = []
    detailed_report = []
    error_count = 0

    for i, output in enumerate(outputs):
        ref = references[i] if i < len(references) else None
        try:
            scores = score_fn(
                output=str(output),
                reference=str(ref) if ref is not None else None,
                idx=i,
            )
            if not isinstance(scores, dict):
                scores = {'score': float(scores)}
            all_scores.append(scores)
            detailed_report.append({
                'index': i,
                'output_preview': str(output)[:200],
                'reference_preview': str(ref)[:200] if ref is not None else None,
                'scores': scores,
            })
        except Exception as e:
            error_count += 1
            ctx.log_message(f'Scoring error at index {i}: {e}')
            if error_handling == 'fail_fast':
                raise
            all_scores.append({})
            detailed_report.append({'index': i, 'error': str(e)})

        ctx.report_progress(i + 1, len(outputs))

    # ── Aggregate ─────────────────────────────────────────────────────────
    metric_keys = set()
    for s in all_scores:
        metric_keys.update(s.keys())

    agg_fns = {
        'mean': statistics.mean,
        'median': statistics.median,
        'min': min,
        'max': max,
        'sum': sum,
    }
    agg_fn = agg_fns.get(aggregate_method, statistics.mean)

    aggregated = {}
    for key in sorted(metric_keys):
        values = [
            s.get(key) for s in all_scores
            if key in s and isinstance(s[key], (int, float)) and not math.isnan(s[key])
        ]
        if values:
            aggregated[key] = round(agg_fn(values), 4)

    # ── Apply decimal precision ────────────────────────────────────────────
    for _k, _v in aggregated.items():
        if isinstance(_v, float):
            aggregated[_k] = round(_v, decimal_precision)

    # ── Save dataset output ────────────────────────────────────────────────
    _ds_dir = os.path.join(ctx.run_dir, "dataset_out")
    os.makedirs(_ds_dir, exist_ok=True)
    _ds_rows = detailed_report
    for _r in _ds_rows:
        if isinstance(_r, dict):
            if "scores" in _r and isinstance(_r["scores"], dict):
                for _sk, _sv in _r["scores"].items():
                    if isinstance(_sv, float):
                        _r["scores"][_sk] = round(_sv, decimal_precision)
    if output_format == "csv" and _ds_rows:
        import csv as _csv
        _flat = []
        for _r in _ds_rows:
            _row = dict(_r)
            if "scores" in _row and isinstance(_row["scores"], dict):
                _row.update({f"score_{k}": v for k, v in _row.pop("scores").items()})
            _flat.append(_row)
        with open(os.path.join(_ds_dir, "data.csv"), "w", newline="", encoding="utf-8") as _f:
            _w = _csv.DictWriter(_f, fieldnames=_flat[0].keys())
            _w.writeheader()
            _w.writerows(_flat)
    else:
        with open(os.path.join(_ds_dir, "data.json"), "w", encoding="utf-8") as _f:
            json.dump(_ds_rows, _f, indent=2, default=str)
    ctx.save_output("dataset", _ds_dir)

    # ── Save outputs ──────────────────────────────────────────────────────
    # Branch: normal execution — scoring complete
    ctx.save_output('scores', aggregated)

    report = {
        'aggregate_method': aggregate_method,
        'total_samples': len(outputs),
        'error_count': error_count,
        'aggregated_scores': aggregated,
        'detailed': detailed_report,
    }
    report_path = os.path.join(ctx.run_dir, "eval_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    # Branch: normal execution — scoring complete
    ctx.save_output('report', report_path)
    ctx.save_artifact("eval_report", report_path)

    for key, val in aggregated.items():
        ctx.log_metric(key, val)

    ctx.log_message(f'Scored {len(outputs)} samples ({error_count} errors). Aggregated: {aggregated}')


def _load_data(source):
    """Normalize various input formats to a list."""
    if source is None:
        return []
    if isinstance(source, list):
        return source
    if isinstance(source, str):
        if os.path.isdir(source):
            data_file = os.path.join(source, "data.json")
            if os.path.isfile(data_file):
                source = data_file
            else:
                return [source]
        if os.path.isfile(source):
            with open(source, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            try:
                parsed = json.loads(content)
                return parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError:
                return [content]
        return [source]
    if isinstance(source, dict) and 'items' in source:
        return source['items']
    return [str(source)]
