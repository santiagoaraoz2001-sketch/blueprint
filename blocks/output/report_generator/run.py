"""Report Generator — generate a Markdown report from metrics and inputs."""

import json
import os
import time

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
    title = ctx.config.get("title", "Blueprint Report")
    include_timestamp = ctx.config.get("include_timestamp", True)
    include_charts = ctx.config.get("include_charts", False)
    sections_str = ctx.config.get("sections", "summary,metrics,details")

    sections = [s.strip() for s in sections_str.split(",") if s.strip()]

    # Collect all available inputs
    all_metrics = {}
    all_data = {}

    for input_name in ["metrics", "dataset", "input", "results", "model"]:
        try:
            data = ctx.load_input(input_name)
            if isinstance(data, str) and os.path.isdir(data):
                data_file = os.path.join(data, "data.json")
                if os.path.isfile(data_file):
                    with open(data_file, "r") as f:
                        data = json.load(f)
            elif isinstance(data, str) and os.path.isfile(data):
                with open(data, "r") as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        data = {"text": f.read()}

            if isinstance(data, dict):
                all_metrics.update(data)
            all_data[input_name] = data
        except (ValueError, Exception):
            pass

    # Validate required input
    if "metrics" not in all_data:
        raise BlockInputError(
            "Required input 'metrics' not connected or produced no data. "
            "Connect evaluation results to the 'Metrics' port.",
            recoverable=False,
        )

    ctx.log_message(f"Generating report: '{title}' with sections: {sections}")
    ctx.log_message(f"Data sources: {list(all_data.keys())}")

    # Build Markdown report
    lines = []
    lines.append(f"# {title}")
    lines.append("")

    if include_timestamp:
        lines.append(f"*Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("")

    if "summary" in sections:
        lines.append("## Summary")
        lines.append("")
        num_metrics = len([v for v in all_metrics.values() if isinstance(v, (int, float))])
        lines.append(f"This report contains **{num_metrics}** metrics from **{len(all_data)}** data sources.")
        lines.append("")

    if "metrics" in sections and all_metrics:
        lines.append("## Metrics")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for key, value in sorted(all_metrics.items()):
            if isinstance(value, (int, float, str, bool)):
                if isinstance(value, float):
                    display_val = f"{value:.4f}"
                else:
                    display_val = str(value)
                lines.append(f"| {key} | {display_val} |")
        lines.append("")

    if "details" in sections:
        lines.append("## Details")
        lines.append("")
        for source_name, data in all_data.items():
            lines.append(f"### {source_name}")
            lines.append("")
            if isinstance(data, list) and data:
                # Show first few rows as table
                sample = data[:5]
                if isinstance(sample[0], dict):
                    cols = list(sample[0].keys())[:6]
                    lines.append("| " + " | ".join(cols) + " |")
                    lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
                    for row in sample:
                        vals = [str(row.get(c, ""))[:30] for c in cols]
                        lines.append("| " + " | ".join(vals) + " |")
                    if len(data) > 5:
                        lines.append(f"\n*... and {len(data) - 5} more rows*")
                else:
                    for item in sample:
                        lines.append(f"- {str(item)[:100]}")
            elif isinstance(data, dict):
                for k, v in list(data.items())[:10]:
                    lines.append(f"- **{k}**: {str(v)[:100]}")
            lines.append("")

    if "config" in sections:
        lines.append("## Configuration")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(dict(ctx.config), indent=2, default=str))
        lines.append("```")
        lines.append("")

    lines.append("---")
    lines.append("*Report generated by Blueprint*")

    report_md = "\n".join(lines)

    # Save report
    out_dir = os.path.join(ctx.run_dir, "report")
    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, "report.md")
    with open(report_path, "w") as f:
        f.write(report_md)

    ctx.save_output("artifact", out_dir)
    ctx.save_output("report_file", report_path)
    ctx.log_metric("report_length", len(report_md))
    ctx.log_metric("num_sections", len(sections))
    ctx.log_message(f"Report generated: {len(report_md)} chars, {len(lines)} lines")
    ctx.report_progress(1, 1)
