"""Metrics Input — define metric key-value pairs for downstream blocks."""

import json


def run(ctx):
    fmt = ctx.config.get("format", "json")

    metrics = {}

    if fmt == "key_value":
        raw = ctx.config.get("key_value_text", "")
        for line in raw.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                ctx.log_message(f"Skipping invalid line (no colon): {line}")
                continue
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            # Try to parse as number
            try:
                val = int(val)
            except ValueError:
                try:
                    val = float(val)
                except ValueError:
                    pass  # keep as string
            metrics[key] = val
    else:
        raw = ctx.config.get("metrics_json", "{}")
        try:
            metrics = json.loads(raw)
            if not isinstance(metrics, dict):
                raise ValueError("Metrics JSON must be an object (dict), not a list or scalar")
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Invalid metrics JSON: {e}")

    ctx.log_message(f"Metrics input: {len(metrics)} entries")
    for key, val in metrics.items():
        if isinstance(val, (int, float)):
            ctx.log_metric(key, val)

    ctx.save_output("metrics", metrics)
    ctx.report_progress(1, 1)
