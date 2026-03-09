"""Prompt Template — string template engine with {variable} substitution.

Workflows:
  1. Prompt engineering: template + variables -> rendered prompt for LLM
  2. Batch templating: template + dataset -> per-row prompts
  3. Multi-source assembly: context + text + variables -> combined prompt
  4. System prompt builder: template pieces -> assembled system prompt
  5. Report generation: data variables -> formatted text report
"""

import json
import os
import re


def run(ctx):
    template = ctx.config.get("template", "{input}")
    variables_str = ctx.config.get("variables", "{}")
    output_format = ctx.config.get("output_format", "text")

    ctx.log_message(f"Template length: {len(template)} chars")

    # Collect variables from config
    try:
        config_vars = json.loads(variables_str) if variables_str.strip() else {}
    except json.JSONDecodeError:
        config_vars = {}
        ctx.log_message("Warning: could not parse variables JSON")

    # Collect variables from inputs
    input_vars = {}
    for input_id in ["text", "context", "dataset", "variables"]:
        if not ctx.inputs.get(input_id):
            continue
        try:
            data = ctx.load_input(input_id)
            if isinstance(data, str):
                if os.path.isfile(data):
                    with open(data, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict):
                            input_vars.update(parsed)
                        else:
                            input_vars[input_id] = content
                    except json.JSONDecodeError:
                        input_vars[input_id] = content
                else:
                    input_vars[input_id] = data
            elif isinstance(data, dict):
                input_vars.update(data)
            elif isinstance(data, list):
                input_vars[input_id] = json.dumps(data, indent=2)
            elif data is not None:
                input_vars[input_id] = str(data)
        except (ValueError, Exception):
            pass

    # Map common aliases
    if "text" in input_vars and "input" not in input_vars:
        input_vars["input"] = input_vars["text"]

    # Merge all variables (config overrides inputs)
    all_vars = {**input_vars, **config_vars}
    ctx.log_message(f"Available variables: {list(all_vars.keys())}")

    # Perform substitution
    result = template
    placeholders_found = re.findall(r"\{(\w+)\}", template)

    for placeholder in placeholders_found:
        if placeholder in all_vars:
            value = all_vars[placeholder]
            if isinstance(value, (dict, list)):
                value = json.dumps(value, indent=2)
            result = result.replace("{" + placeholder + "}", str(value))

    # Check for unresolved placeholders
    unresolved = re.findall(r"\{(\w+)\}", result)
    if unresolved:
        ctx.log_message(f"Warning: unresolved placeholders: {unresolved}")

    # Apply output format
    if output_format == "json":
        output_data = {
            "rendered": result,
            "variables": {k: str(v) for k, v in all_vars.items()},
            "unresolved": unresolved,
        }
        result = json.dumps(output_data, indent=2)

    ctx.log_message(f"Rendered template: {len(result)} chars (format={output_format})")

    # Save output
    ext = "json" if output_format == "json" else "txt"
    out_path = os.path.join(ctx.run_dir, f"prompt.{ext}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result)
    ctx.save_output("text", out_path)

    # Save metrics
    ctx.save_output("metrics", {
        "template_length": len(template),
        "output_length": len(result),
        "variables_used": len(placeholders_found) - len(unresolved),
        "variables_available": len(all_vars),
        "unresolved": unresolved,
    })
    ctx.log_metric("template_length", len(template))
    ctx.log_metric("output_length", len(result))
    ctx.log_metric("variables_used", len(placeholders_found) - len(unresolved))
    ctx.report_progress(1, 1)
