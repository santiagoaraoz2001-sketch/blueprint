"""Model Card Writer — generate a model card in Markdown format."""

import json
import os
import time


def run(ctx):
    model_name = ctx.config.get("model_name", "My Fine-Tuned Model")
    base_model = ctx.config.get("base_model", "")
    language = ctx.config.get("language", "en")
    license_type = ctx.config.get("license", "apache-2.0")
    tags_str = ctx.config.get("tags", "text-generation,fine-tuned")
    description = ctx.config.get("description", "")
    output_format = ctx.config.get("format", "markdown")
    include_biases = ctx.config.get("include_biases", True)
    include_usage = ctx.config.get("include_usage", True)
    include_citation = ctx.config.get("include_citation", True)
    include_training_details = ctx.config.get("include_training_details", True)
    custom_sections = ctx.config.get("custom_sections", "").strip()

    tags = [t.strip() for t in tags_str.split(",") if t.strip()]

    # Collect info from inputs
    metrics = {}
    model_info = {}
    try:
        data = ctx.load_input("metrics")
        if isinstance(data, dict):
            metrics = data
        elif isinstance(data, str) and os.path.isfile(data):
            with open(data, "r") as f:
                metrics = json.load(f)
    except (ValueError, Exception):
        pass

    try:
        data = ctx.load_input("model")
        if isinstance(data, dict):
            model_info = data
            # Auto-populate base_model from upstream if user left it blank
            if not base_model:
                base_model = data.get("base_model", data.get("model_id", data.get("model_name", "")))
            # Auto-enrich tags based on upstream pipeline context
            upstream_method = data.get("method", data.get("source", ""))
            if upstream_method:
                method_tag_map = {
                    "slerp": "merge", "ties": "merge", "dare_ties": "merge",
                    "dare_linear": "merge", "linear": "merge", "passthrough": "merge",
                    "lora": "fine-tuned", "qlora": "fine-tuned",
                    "gptq": "quantized", "bitsandbytes": "quantized", "awq": "quantized",
                }
                auto_tag = method_tag_map.get(upstream_method, "")
                if auto_tag and auto_tag not in tags:
                    tags.append(auto_tag)
                    ctx.log_message(f"Auto-added tag '{auto_tag}' from upstream pipeline")
    except (ValueError, Exception):
        pass

    ctx.log_message(f"Generating model card for: {model_name}")

    # Build model card
    lines = []

    # YAML frontmatter
    lines.append("---")
    lines.append(f"language: {language}")
    lines.append(f"license: {license_type}")
    if tags:
        lines.append("tags:")
        for tag in tags:
            lines.append(f"  - {tag}")
    if base_model:
        lines.append(f"base_model: {base_model}")
    if metrics:
        lines.append("model-index:")
        lines.append(f"  - name: {model_name}")
        lines.append("    results:")
        for metric_name, metric_value in metrics.items():
            if isinstance(metric_value, (int, float)):
                lines.append(f"      - task:")
                lines.append(f"          type: text-generation")
                lines.append(f"        metrics:")
                lines.append(f"          - name: {metric_name}")
                lines.append(f"            type: {metric_name}")
                lines.append(f"            value: {metric_value}")
    lines.append("---")
    lines.append("")

    # Title
    lines.append(f"# {model_name}")
    lines.append("")

    # Description — auto-generate based on upstream pipeline context
    if description:
        lines.append(description)
    else:
        upstream_src = model_info.get("source", "") if model_info else ""
        upstream_meth = model_info.get("method", "") if model_info else ""
        if upstream_meth in ("slerp", "ties", "dare_ties", "dare_linear", "linear", "passthrough"):
            model_a = model_info.get("model_a", "")
            model_b = model_info.get("model_b", "")
            desc_parts = [f"This model was created by merging"]
            if model_a and model_b:
                desc_parts.append(f" [{model_a}](https://huggingface.co/{model_a}) and [{model_b}](https://huggingface.co/{model_b})")
            else:
                desc_parts.append(" two models")
            desc_parts.append(f" using the **{upstream_meth}** method.")
            lines.append("".join(desc_parts))
        elif upstream_src in ("gptq", "bitsandbytes", "awq"):
            bits = model_info.get("bits", "")
            lines.append(
                f"This is a {bits}-bit quantized version of "
                f"[{base_model}](https://huggingface.co/{base_model}) "
                f"using **{upstream_src}**."
                if base_model else
                f"A {bits}-bit quantized model using **{upstream_src}**."
            )
        elif base_model:
            lines.append(f"This model is a fine-tuned version of [{base_model}](https://huggingface.co/{base_model}) for text generation tasks.")
        else:
            lines.append("A model built with Blueprint.")
    lines.append("")

    # Model Details
    lines.append("## Model Details")
    lines.append("")
    lines.append(f"- **Model type:** Causal Language Model")
    lines.append(f"- **Language:** {language}")
    lines.append(f"- **License:** {license_type}")
    if base_model:
        lines.append(f"- **Base model:** [{base_model}](https://huggingface.co/{base_model})")
    if model_info:
        for key in ["method", "lora_r", "lora_alpha", "learning_rate", "epochs"]:
            if key in model_info:
                lines.append(f"- **{key.replace('_', ' ').title()}:** {model_info[key]}")
        # Auto-detect merge parameters from upstream
        if model_info.get("method") in ("slerp", "ties", "dare_ties", "dare_linear", "linear", "passthrough"):
            if "weight" in model_info:
                lines.append(f"- **Merge Weight:** {model_info['weight']}")
            if "density" in model_info:
                lines.append(f"- **Merge Density:** {model_info['density']}")
            if "model_a" in model_info:
                lines.append(f"- **Model A:** {model_info['model_a']}")
            if "model_b" in model_info:
                lines.append(f"- **Model B:** {model_info['model_b']}")
        # Auto-detect quantization parameters
        if model_info.get("bits"):
            lines.append(f"- **Quantization Bits:** {model_info['bits']}")
        if model_info.get("quantization") and model_info["quantization"] != "none":
            lines.append(f"- **Quantization:** {model_info['quantization']}")
    lines.append("")

    # Training/Merge/Quantize Details — auto-detect section title
    if include_training_details:
        upstream_method = model_info.get("method", "") if model_info else ""
        merge_methods = {"slerp", "ties", "dare_ties", "dare_linear", "linear", "passthrough"}
        quant_methods = {"gptq", "bitsandbytes", "awq"}
        if upstream_method in merge_methods:
            lines.append("## Merge Details")
        elif upstream_method in quant_methods:
            lines.append("## Quantization Details")
        else:
            lines.append("## Training Details")
        lines.append("")
        if model_info:
            section_label = "Parameters"
            if upstream_method in merge_methods:
                section_label = "Merge Configuration"
            elif upstream_method in quant_methods:
                section_label = "Quantization Configuration"
            else:
                section_label = "Training Hyperparameters"
            lines.append(f"### {section_label}")
            lines.append("")
            lines.append("| Parameter | Value |")
            lines.append("|-----------|-------|")
            skip_keys = {"path", "source", "demo_mode", "available_local_models", "files", "tags"}
            for key, value in model_info.items():
                if key not in skip_keys and isinstance(value, (int, float, str, bool)):
                    lines.append(f"| {key} | {value} |")
            lines.append("")

    # Evaluation
    if metrics:
        lines.append("## Evaluation Results")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for key, value in sorted(metrics.items()):
            if isinstance(value, float):
                lines.append(f"| {key} | {value:.4f} |")
            elif isinstance(value, int):
                lines.append(f"| {key} | {value} |")
        lines.append("")

    # Bias and Limitations
    if include_biases:
        lines.append("## Limitations and Biases")
        lines.append("")
        lines.append("This model may exhibit biases present in the training data. Users should:")
        lines.append("")
        lines.append("- Evaluate the model on their specific use case before deployment")
        lines.append("- Be aware of potential biases in generated text")
        lines.append("- Not use the model for high-stakes decisions without human oversight")
        lines.append("- Consider fairness and representation when interpreting outputs")
        lines.append("")

    # Usage
    if include_usage:
        lines.append("## Usage")
        lines.append("")
        lines.append("```python")
        lines.append(f"from transformers import AutoModelForCausalLM, AutoTokenizer")
        lines.append(f"")
        lines.append(f'model = AutoModelForCausalLM.from_pretrained("{model_name}")')
        lines.append(f'tokenizer = AutoTokenizer.from_pretrained("{model_name}")')
        lines.append(f"")
        lines.append(f'inputs = tokenizer("Hello, ", return_tensors="pt")')
        lines.append(f"outputs = model.generate(**inputs, max_new_tokens=100)")
        lines.append(f"print(tokenizer.decode(outputs[0]))")
        lines.append("```")
        lines.append("")

    # Custom Sections
    if custom_sections:
        lines.append(custom_sections)
        lines.append("")

    # Citation
    if include_citation:
        lines.append("## Citation")
        lines.append("")
        lines.append("If you use this model, please cite:")
        lines.append("")
        lines.append("```bibtex")
        lines.append(f"@misc{{{model_name.replace('/', '_').replace('-', '_')},")
        lines.append(f"  title={{{model_name}}},")
        lines.append(f"  year={{{time.strftime('%Y')}}},")
        lines.append(f"  publisher={{Blueprint}}")
        lines.append(f"}}")
        lines.append("```")
        lines.append("")
    lines.append("---")
    lines.append("*Generated by Blueprint Model Card Writer*")

    model_card_md = "\n".join(lines)

    # Convert to HTML if requested
    if output_format == "html":
        model_card_html = _markdown_to_html(model_card_md, model_name)
        out_dir = os.path.join(ctx.run_dir, "model_card")
        os.makedirs(out_dir, exist_ok=True)
        html_path = os.path.join(out_dir, "model_card.html")
        with open(html_path, "w") as f:
            f.write(model_card_html)
        # Also save the markdown version
        card_path = os.path.join(out_dir, "README.md")
        with open(card_path, "w") as f:
            f.write(model_card_md)
        # Branch: output_format == "html"
        ctx.save_output("artifact", out_dir)
        # Branch: output_format == "html"
        ctx.save_output("text", html_path)
    else:
        out_dir = os.path.join(ctx.run_dir, "model_card")
        os.makedirs(out_dir, exist_ok=True)
        card_path = os.path.join(out_dir, "README.md")
        with open(card_path, "w") as f:
            f.write(model_card_md)
        # Branch: output_format == "markdown"
        ctx.save_output("artifact", out_dir)
        # Branch: output_format == "markdown"
        ctx.save_output("text", card_path)

    ctx.log_metric("card_length", len(model_card_md))
    ctx.log_message(f"Model card generated ({output_format}): {len(model_card_md)} chars")
    ctx.report_progress(1, 1)


def _markdown_to_html(md_content, title="Model Card"):
    """Convert markdown to a simple HTML document."""
    # Try using markdown library if available
    try:
        import markdown
        html_body = markdown.markdown(md_content, extensions=["tables", "fenced_code"])
    except ImportError:
        # Basic fallback: wrap in <pre> tags
        import html
        html_body = f"<pre>{html.escape(md_content)}</pre>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 800px; margin: 40px auto; padding: 0 20px; line-height: 1.6; color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
        th {{ background-color: #f5f5f5; }}
        code {{ background-color: #f5f5f5; padding: 2px 6px; border-radius: 3px; }}
        pre {{ background-color: #f5f5f5; padding: 16px; border-radius: 6px; overflow-x: auto; }}
        pre code {{ padding: 0; }}
        h1 {{ border-bottom: 2px solid #eee; padding-bottom: 8px; }}
        h2 {{ border-bottom: 1px solid #eee; padding-bottom: 4px; margin-top: 32px; }}
    </style>
</head>
<body>
{html_body}
</body>
</html>"""
