"""Results Formatter — format and export results."""

import csv
import json
import os


def run(ctx):
    metrics = ctx.load_input("metrics")
    fmt = ctx.config.get("format", "csv")
    include_config = ctx.config.get("include_config", True)

    ctx.log_message(f"Formatting results as {fmt}")
    ctx.report_progress(1, 2)

    output_data = {}
    if include_config:
        output_data["config"] = ctx.config
    if isinstance(metrics, dict):
        output_data["metrics"] = metrics
    else:
        output_data["metrics"] = str(metrics)

    if fmt == "json":
        out_file = os.path.join(ctx.run_dir, "results.json")
        with open(out_file, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
    elif fmt == "csv":
        out_file = os.path.join(ctx.run_dir, "results.csv")
        flat = {}
        if isinstance(metrics, dict):
            for k, v in metrics.items():
                if isinstance(v, dict):
                    for k2, v2 in v.items():
                        flat[f"{k}.{k2}"] = v2
                else:
                    flat[k] = v
        with open(out_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["metric", "value"])
            for k, v in flat.items():
                writer.writerow([k, v])
    elif fmt == "markdown":
        out_file = os.path.join(ctx.run_dir, "results.md")
        lines = ["# Results\n"]
        if isinstance(metrics, dict):
            lines.append("| Metric | Value |")
            lines.append("|--------|-------|")
            for k, v in metrics.items():
                if not isinstance(v, dict):
                    lines.append(f"| {k} | {v} |")
        with open(out_file, "w") as f:
            f.write("\n".join(lines))
    else:
        out_file = os.path.join(ctx.run_dir, "results.json")
        with open(out_file, "w") as f:
            json.dump(output_data, f, indent=2, default=str)

    ctx.log_message(f"Results saved to {out_file}")
    ctx.report_progress(2, 2)
    ctx.save_output("artifact", out_file)
    ctx.save_artifact("results", out_file)
