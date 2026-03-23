#!/usr/bin/env python3
"""
Scaffold a new Blueprint block from a template.

Usage:
    python scripts/scaffold_block.py --name "My Custom Block" --category training --type my_custom_block
    python scripts/scaffold_block.py --name "Text Cleaner" --category data
    python scripts/scaffold_block.py --name "BLEU Score" --category evaluation --description "Compute BLEU score"

Creates:
    blocks/{category}/{type}/
        block.yaml    (pre-filled template)
        run.py        (category-aware skeleton with def run(ctx))
"""

import argparse
import keyword
import os
import re
import sys

try:
    import yaml
except ImportError:
    yaml = None  # Fallback to manual YAML generation


VALID_CATEGORIES = [
    "agents", "data", "endpoints", "evaluation",
    "flow", "inference", "merge", "output", "training",
]

# Maximum length for block type identifiers
MAX_TYPE_LENGTH = 64

# Regex for valid block type: lowercase letters, digits, underscores only; no leading digits
VALID_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


# ── Category-specific templates ──────────────────────────────────────────────

def _make_block_yaml(name: str, block_type: str, category: str, description: str) -> str:
    """Generate block.yaml content with proper YAML escaping."""
    schema = _get_schema_for_category(name, block_type, category, description)

    if yaml is not None:
        return yaml.dump(schema, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # Fallback: manual YAML generation for environments without PyYAML
    return _schema_to_yaml_manual(schema)


def _get_schema_for_category(name: str, block_type: str, category: str, description: str) -> dict:
    """Return a block.yaml schema dict tailored to the block category."""
    base = {
        "name": name,
        "type": block_type,
        "category": category,
        "description": description,
        "version": "1.0.0",
    }

    if category == "training":
        base["inputs"] = [
            {"id": "dataset", "label": "Training Dataset", "data_type": "dataset",
             "required": True, "description": "Training data (JSON list or CSV file)"},
            {"id": "model", "label": "Base Model", "data_type": "model",
             "required": False, "description": "Pre-trained model to fine-tune"},
        ]
        base["outputs"] = [
            {"id": "model", "label": "Trained Model", "data_type": "model",
             "description": "Model weights after training"},
            {"id": "metrics", "label": "Training Metrics", "data_type": "metrics",
             "description": "Loss, accuracy, and other training metrics"},
        ]
        base["config"] = {
            "epochs": {"type": "integer", "label": "Epochs", "default": 3, "min": 1, "max": 100,
                       "description": "Number of training epochs"},
            "learning_rate": {"type": "float", "label": "Learning Rate", "default": 0.0001,
                              "min": 0.0, "max": 1.0, "description": "Optimizer learning rate"},
            "batch_size": {"type": "integer", "label": "Batch Size", "default": 8, "min": 1, "max": 512,
                           "description": "Training batch size"},
        }

    elif category == "evaluation":
        base["inputs"] = [
            {"id": "model_output", "label": "Model Output", "data_type": "dataset",
             "required": True, "description": "Model predictions to evaluate"},
            {"id": "reference", "label": "Reference Data", "data_type": "dataset",
             "required": False, "description": "Ground truth labels for comparison"},
        ]
        base["outputs"] = [
            {"id": "scores", "label": "Scores", "data_type": "metrics",
             "description": "Evaluation scores and summary statistics"},
            {"id": "report", "label": "Detailed Report", "data_type": "artifact",
             "description": "Per-sample evaluation report"},
        ]
        base["config"] = {
            "metric_name": {"type": "string", "label": "Metric Name", "default": "score",
                            "description": "Name for the primary evaluation metric"},
        }

    elif category == "inference":
        base["inputs"] = [
            {"id": "model", "label": "Model", "data_type": "model",
             "required": False, "description": "Model to run inference with"},
            {"id": "prompt", "label": "Prompt", "data_type": "text",
             "required": True, "description": "Input prompt or data for inference"},
        ]
        base["outputs"] = [
            {"id": "response", "label": "Response", "data_type": "text",
             "description": "Model output or predictions"},
            {"id": "metadata", "label": "Metadata", "data_type": "metrics",
             "description": "Inference metadata (latency, tokens, etc.)"},
        ]
        base["config"] = {
            "max_tokens": {"type": "integer", "label": "Max Tokens", "default": 512,
                           "min": 1, "max": 32768, "description": "Maximum tokens to generate"},
            "temperature": {"type": "float", "label": "Temperature", "default": 0.7,
                            "min": 0.0, "max": 2.0, "description": "Sampling temperature"},
        }

    elif category == "flow":
        base["inputs"] = [
            {"id": "input", "label": "Input", "data_type": "any",
             "required": True, "description": "Data to process"},
        ]
        base["outputs"] = [
            {"id": "output", "label": "Output", "data_type": "any",
             "description": "Processed data"},
        ]
        base["config"] = {
            "condition": {"type": "string", "label": "Condition", "default": "",
                          "description": "Condition or configuration for flow control"},
        }

    else:
        # Generic template for: data, agents, endpoints, merge, output
        base["inputs"] = [
            {"id": "input_data", "label": "Input Data", "data_type": "any",
             "required": True, "description": "Input data to process"},
        ]
        base["outputs"] = [
            {"id": "result", "label": "Result", "data_type": "any",
             "description": "Processed output"},
        ]
        base["config"] = {
            "example_option": {"type": "string", "label": "Example Option",
                               "description": "Replace with your configuration fields",
                               "default": "default_value"},
        }

    return base


def _schema_to_yaml_manual(schema: dict) -> str:
    """Manually render a block schema dict to YAML without the yaml library."""
    def quote_if_needed(val):
        """Quote a string value if it contains YAML-special characters."""
        if not isinstance(val, str):
            return val
        needs_quoting = (
            val == "" or
            val.startswith(("{", "[", "*", "&", "!", "%", "@", "`", "'", '"')) or
            ":" in val or
            "#" in val or
            "\n" in val or
            val.lower() in ("true", "false", "null", "yes", "no", "on", "off") or
            val != val.strip()
        )
        if needs_quoting:
            escaped = (
                val.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t")
            )
            return f'"{escaped}"'
        return val

    lines = []
    for key in ("name", "type", "category", "description", "version"):
        if key in schema:
            lines.append(f"{key}: {quote_if_needed(schema[key])}")

    lines.append("")
    lines.append("inputs:")
    for inp in schema.get("inputs", []):
        lines.append(f"  - id: {inp['id']}")
        lines.append(f"    label: {quote_if_needed(inp['label'])}")
        lines.append(f"    data_type: {inp['data_type']}")
        lines.append(f"    required: {'true' if inp.get('required') else 'false'}")
        if inp.get("description"):
            lines.append(f"    description: {quote_if_needed(inp['description'])}")

    lines.append("")
    lines.append("outputs:")
    for out in schema.get("outputs", []):
        lines.append(f"  - id: {out['id']}")
        lines.append(f"    label: {quote_if_needed(out['label'])}")
        lines.append(f"    data_type: {out['data_type']}")
        if out.get("description"):
            lines.append(f"    description: {quote_if_needed(out['description'])}")

    config = schema.get("config", {})
    if config:
        lines.append("")
        lines.append("config:")
        for field_name, field_def in config.items():
            lines.append(f"  {field_name}:")
            for fk, fv in field_def.items():
                if isinstance(fv, bool):
                    lines.append(f"    {fk}: {'true' if fv else 'false'}")
                elif isinstance(fv, (int, float)):
                    lines.append(f"    {fk}: {fv}")
                elif isinstance(fv, list):
                    items = ", ".join(str(x) for x in fv)
                    lines.append(f"    {fk}: [{items}]")
                else:
                    lines.append(f"    {fk}: {quote_if_needed(str(fv))}")

    lines.append("")
    return "\n".join(lines)


# ── Category-specific run.py templates ───────────────────────────────────────
#
# Templates use __BLOCK_NAME__ as a placeholder for the block name.
# This avoids conflicts with Python's str.format() and curly braces in
# f-strings, dict literals, and user-provided names containing { or }.

_NAME = "__BLOCK_NAME__"

_RUN_PY_TEMPLATES = {
    "training": f'''\
"""{_NAME} — TODO: add a description."""

import json
import os

from backend.block_sdk.exceptions import BlockInputError, BlockDataError


def run(ctx):
    # ── Load config ──────────────────────────────────────────────────────
    epochs = int(ctx.config.get("epochs", 3))
    learning_rate = float(ctx.config.get("learning_rate", 1e-4))
    batch_size = int(ctx.config.get("batch_size", 8))

    ctx.log_message(
        f"Starting {_NAME}: epochs={{epochs}}, lr={{learning_rate}}, batch_size={{batch_size}}"
    )

    # ── Load inputs ──────────────────────────────────────────────────────
    raw = ctx.load_input("dataset")
    if isinstance(raw, str) and os.path.isfile(raw):
        with open(raw, "r", encoding="utf-8") as f:
            dataset = json.load(f)
    elif isinstance(raw, list):
        dataset = raw
    else:
        raise BlockInputError(
            f"Expected a JSON list or file path, got {{type(raw).__name__}}"
        )

    if not dataset:
        raise BlockDataError("Training dataset is empty")

    ctx.log_message(f"Loaded {{len(dataset)}} training samples")

    # ── Training loop ────────────────────────────────────────────────────
    # TODO: Replace with your training logic
    total_steps = epochs * max(1, len(dataset) // batch_size)
    step = 0
    for epoch in range(epochs):
        epoch_loss = 0.0
        num_batches = max(1, len(dataset) // batch_size)
        for batch_idx in range(num_batches):
            # TODO: Implement batch training
            batch_loss = 1.0 / (step + 1)  # Placeholder
            epoch_loss += batch_loss

            step += 1
            ctx.report_progress(step, total_steps)
            ctx.log_metric("training/loss", batch_loss, step=step)

        avg_loss = epoch_loss / num_batches
        ctx.log_message(f"Epoch {{epoch + 1}}/{{epochs}} — avg loss: {{avg_loss:.4f}}")
        ctx.log_metric("training/epoch_loss", avg_loss, step=epoch)

    # ── Save outputs ─────────────────────────────────────────────────────
    model_path = os.path.join(ctx.run_dir, "model.json")
    with open(model_path, "w", encoding="utf-8") as f:
        json.dump({{"status": "trained", "epochs": epochs}}, f, indent=2)
    ctx.save_output("model", model_path)

    metrics = {{"final_loss": avg_loss, "total_steps": step, "samples": len(dataset)}}
    ctx.save_output("metrics", metrics)

    ctx.log_metric("training/final_loss", avg_loss)
    ctx.log_message("{_NAME} complete")
''',

    "evaluation": f'''\
"""{_NAME} — TODO: add a description."""

import json
import os

from backend.block_sdk.exceptions import BlockInputError, BlockDataError


def _load_data(raw):
    """Load data from a file path or in-memory object."""
    if isinstance(raw, str) and os.path.isfile(raw):
        with open(raw, "r", encoding="utf-8") as f:
            return json.load(f)
    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw
    raise BlockInputError(f"Cannot load data of type {{type(raw).__name__}}")


def run(ctx):
    # ── Load config ──────────────────────────────────────────────────────
    metric_name = ctx.config.get("metric_name", "score")
    ctx.log_message(f"Running {_NAME} (metric: {{metric_name}})")

    # ── Load inputs ──────────────────────────────────────────────────────
    predictions = _load_data(ctx.load_input("model_output"))
    if not isinstance(predictions, list):
        predictions = [predictions]

    references = []
    if ctx.inputs.get("reference"):
        references = _load_data(ctx.load_input("reference"))
        if not isinstance(references, list):
            references = [references]

    if not predictions:
        raise BlockDataError("No predictions to evaluate")

    ctx.log_message(f"Evaluating {{len(predictions)}} samples")

    # ── Evaluate ─────────────────────────────────────────────────────────
    scores = []
    for i, pred in enumerate(predictions):
        ref = references[i] if i < len(references) else None

        # TODO: Replace with your evaluation logic
        sample_score = 1.0 if pred == ref else 0.0
        scores.append({{"index": i, metric_name: sample_score}})

        ctx.report_progress(i + 1, len(predictions))

    # ── Aggregate ────────────────────────────────────────────────────────
    values = [s[metric_name] for s in scores]
    aggregate = {{
        metric_name: sum(values) / len(values) if values else 0.0,
        "total_samples": len(scores),
    }}

    ctx.log_metric(metric_name, aggregate[metric_name])
    ctx.log_message(f"{{metric_name}}: {{aggregate[metric_name]:.4f}}")

    # ── Save outputs ─────────────────────────────────────────────────────
    ctx.save_output("scores", aggregate)

    report_path = os.path.join(ctx.run_dir, "eval_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({{"summary": aggregate, "per_sample": scores}}, f, indent=2)
    ctx.save_output("report", report_path)

    ctx.log_message("{_NAME} complete")
''',

    "inference": f'''\
"""{_NAME} — TODO: add a description."""

import json
import os
import time

from backend.block_sdk.exceptions import BlockInputError


def run(ctx):
    # ── Load config ──────────────────────────────────────────────────────
    max_tokens = int(ctx.config.get("max_tokens", 512))
    temperature = float(ctx.config.get("temperature", 0.7))

    ctx.log_message(f"Running {_NAME} (max_tokens={{max_tokens}}, temp={{temperature}})")

    # ── Load inputs ──────────────────────────────────────────────────────
    raw_prompt = ctx.load_input("prompt")
    if isinstance(raw_prompt, str) and os.path.isfile(raw_prompt):
        with open(raw_prompt, "r", encoding="utf-8") as f:
            prompt = f.read()
    elif isinstance(raw_prompt, str):
        prompt = raw_prompt
    else:
        raise BlockInputError(f"Expected text prompt, got {{type(raw_prompt).__name__}}")

    ctx.log_message(f"Prompt length: {{len(prompt)}} chars")
    ctx.report_progress(1, 3)

    # ── Run inference ────────────────────────────────────────────────────
    start = time.time()

    # TODO: Replace with your inference logic
    response_text = f"Response to: {{prompt[:100]}}"

    latency_ms = (time.time() - start) * 1000
    ctx.report_progress(2, 3)

    # ── Save outputs ─────────────────────────────────────────────────────
    out_path = os.path.join(ctx.run_dir, "response.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(response_text)
    ctx.save_output("response", out_path)

    metadata = {{
        "latency_ms": latency_ms,
        "prompt_length": len(prompt),
        "response_length": len(response_text),
    }}
    ctx.save_output("metadata", metadata)

    ctx.log_metric("inference/latency_ms", latency_ms)
    ctx.log_metric("response_length", len(response_text))
    ctx.report_progress(3, 3)
    ctx.log_message("{_NAME} complete")
''',

    "flow": f'''\
"""{_NAME} — TODO: add a description."""

import json
import os

from backend.block_sdk.exceptions import BlockInputError


def run(ctx):
    # ── Load config ──────────────────────────────────────────────────────
    condition = ctx.config.get("condition", "")
    ctx.log_message(f"Running {_NAME}")

    # ── Load inputs ──────────────────────────────────────────────────────
    raw = ctx.load_input("input")
    if isinstance(raw, str) and os.path.isfile(raw):
        with open(raw, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(raw, (dict, list)):
        data = raw
    elif isinstance(raw, str):
        data = raw
    else:
        raise BlockInputError(f"Unexpected input type: {{type(raw).__name__}}")

    # ── Process ──────────────────────────────────────────────────────────
    # TODO: Implement your flow control logic here
    result = data

    # ── Save outputs ─────────────────────────────────────────────────────
    if isinstance(result, str) and not os.path.isfile(result):
        out_path = os.path.join(ctx.run_dir, "output.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(result)
        ctx.save_output("output", out_path)
    elif isinstance(result, (dict, list)):
        out_path = os.path.join(ctx.run_dir, "output.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        ctx.save_output("output", out_path)
    else:
        ctx.save_output("output", result)

    ctx.report_progress(1, 1)
    ctx.log_message("{_NAME} complete")
''',
}

# Default template for categories without a specific one (data, agents, endpoints, merge, output)
_RUN_PY_DEFAULT = f'''\
"""{_NAME} — TODO: add a description."""

import json
import os

from backend.block_sdk.exceptions import BlockInputError


def run(ctx):
    # ── Load config ──────────────────────────────────────────────────────
    example_option = ctx.config.get("example_option", "default_value")
    ctx.log_message(f"Running {_NAME} (example_option={{example_option}})")

    # ── Load inputs ──────────────────────────────────────────────────────
    raw = ctx.load_input("input_data")

    # Handle file path or in-memory data
    if isinstance(raw, str) and os.path.isfile(raw):
        with open(raw, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(raw, (dict, list)):
        data = raw
    elif isinstance(raw, str):
        data = raw
    else:
        raise BlockInputError(f"Unexpected input type: {{type(raw).__name__}}")

    # ── Process ──────────────────────────────────────────────────────────
    # TODO: Implement your block logic here
    result = data

    # ── Save outputs ─────────────────────────────────────────────────────
    out_path = os.path.join(ctx.run_dir, "result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    ctx.save_output("result", out_path)

    ctx.log_metric("output_size", os.path.getsize(out_path))
    ctx.report_progress(1, 1)
    ctx.log_message("{_NAME} complete")
'''


# ── Validation helpers ───────────────────────────────────────────────────────

def slugify(name: str) -> str:
    """Convert a human-readable name to a valid block type slug.

    Examples:
        "My Custom Block" -> "my_custom_block"
        "TF-IDF Vectorizer" -> "tf_idf_vectorizer"
        "  Spaces  " -> "spaces"
    """
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")

    # Ensure it doesn't start with a digit
    if slug and slug[0].isdigit():
        slug = f"block_{slug}"

    return slug


def validate_block_type(block_type: str) -> str | None:
    """Validate a block type identifier. Returns an error message or None if valid."""
    if not block_type:
        return "Block type cannot be empty"

    if len(block_type) > MAX_TYPE_LENGTH:
        return f"Block type must be <= {MAX_TYPE_LENGTH} characters, got {len(block_type)}"

    if not VALID_TYPE_PATTERN.match(block_type):
        return (
            f"Block type '{block_type}' is invalid. "
            f"Must be lowercase letters, digits, and underscores only, starting with a letter"
        )

    if keyword.iskeyword(block_type):
        return f"Block type '{block_type}' is a Python reserved keyword"

    if block_type.startswith("_"):
        return "Block type cannot start with an underscore (ignored by registry)"

    return None


def validate_generated_yaml(yaml_path: str) -> str | None:
    """Validate that a generated block.yaml is syntactically valid. Returns error or None."""
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            content = f.read()

        if yaml is not None:
            schema = yaml.safe_load(content)
        else:
            # Without PyYAML, do basic structural checks
            schema = None
            if "name:" not in content:
                return "Missing 'name' field"
            if "type:" not in content:
                return "Missing 'type' field"
            return None

        if not isinstance(schema, dict):
            return "block.yaml did not parse as a YAML mapping"

        required_fields = ["name", "type", "category", "description", "version"]
        for field in required_fields:
            if field not in schema:
                return f"Missing required field: {field}"

        if not isinstance(schema.get("inputs"), list):
            return "'inputs' must be a list"

        if not isinstance(schema.get("outputs"), list):
            return "'outputs' must be a list"

        return None
    except Exception as e:
        return f"Failed to parse block.yaml: {e}"


def validate_generated_run_py(run_path: str) -> str | None:
    """Validate that a generated run.py is syntactically valid Python. Returns error or None."""
    try:
        with open(run_path, "r", encoding="utf-8") as f:
            source = f.read()

        compile(source, run_path, "exec")

        if "def run(" not in source:
            return "run.py does not contain a 'def run(' function"

        return None
    except SyntaxError as e:
        return f"Syntax error in run.py at line {e.lineno}: {e.msg}"


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scaffold a new Blueprint block from a template.",
        epilog=(
            "Examples:\n"
            "  python scripts/scaffold_block.py --name 'Text Normalizer' --category data\n"
            "  python scripts/scaffold_block.py --name 'LoRA Trainer' --category training --type lora_trainer\n"
            "  python scripts/scaffold_block.py --name 'BLEU Score' --category evaluation --description 'Compute BLEU'"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--name", required=True,
        help="Human-readable block name (e.g. 'My Custom Block')",
    )
    parser.add_argument(
        "--category", required=True, choices=VALID_CATEGORIES,
        help="Block category",
    )
    parser.add_argument(
        "--type", dest="block_type", default=None,
        help="Block type ID (lowercase_with_underscores). Auto-derived from --name if omitted",
    )
    parser.add_argument(
        "--description", default=None,
        help="One-line block description. Auto-generated if omitted",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing block files",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be created without writing files",
    )

    args = parser.parse_args()

    # ── Derive and validate block type ───────────────────────────────────
    block_type = args.block_type or slugify(args.name)

    if not block_type:
        print(f"Error: Could not derive a valid block type from name '{args.name}'")
        print("Please provide an explicit --type argument")
        sys.exit(1)

    error = validate_block_type(block_type)
    if error:
        print(f"Error: {error}")
        if args.block_type:
            suggested = slugify(args.name)
            if suggested and validate_block_type(suggested) is None:
                print(f"Suggestion: --type {suggested}")
        sys.exit(1)

    name = args.name.strip()
    description = args.description or f"TODO: describe what {name} does"

    # ── Resolve paths ────────────────────────────────────────────────────
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    blocks_root = os.path.join(project_root, "blocks")
    block_dir = os.path.join(blocks_root, args.category, block_type)
    yaml_path = os.path.join(block_dir, "block.yaml")
    run_path = os.path.join(block_dir, "run.py")

    # Verify blocks/ directory exists
    if not os.path.isdir(blocks_root):
        print(f"Error: blocks/ directory not found at {blocks_root}")
        print("Are you running this from the Blueprint project root?")
        sys.exit(1)

    # ── Dry run ──────────────────────────────────────────────────────────
    if args.dry_run:
        print(f"Would create: {block_dir}/")
        print(f"  block.yaml  — {args.category} block schema for '{name}'")
        print(f"  run.py      — {args.category}-specific execution skeleton")
        if os.path.exists(block_dir):
            existing = []
            if os.path.exists(yaml_path):
                existing.append("block.yaml")
            if os.path.exists(run_path):
                existing.append("run.py")
            if existing:
                print(f"  WARNING: Would overwrite: {', '.join(existing)}")
        return

    # ── Check for existing block ─────────────────────────────────────────
    if os.path.exists(block_dir) and not args.force:
        existing = []
        if os.path.exists(yaml_path):
            existing.append("block.yaml")
        if os.path.exists(run_path):
            existing.append("run.py")
        if existing:
            print(f"Error: Block already exists at {block_dir}")
            print(f"  Existing files: {', '.join(existing)}")
            print("  Use --force to overwrite, or --dry-run to preview")
            sys.exit(1)

    # ── Generate content ─────────────────────────────────────────────────
    yaml_content = _make_block_yaml(name, block_type, args.category, description)

    template = _RUN_PY_TEMPLATES.get(args.category, _RUN_PY_DEFAULT)
    run_content = template.replace(_NAME, name)

    # ── Write files ──────────────────────────────────────────────────────
    os.makedirs(block_dir, exist_ok=True)

    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(yaml_content)

    with open(run_path, "w", encoding="utf-8") as f:
        f.write(run_content)

    # ── Post-generation validation ───────────────────────────────────────
    yaml_error = validate_generated_yaml(yaml_path)
    if yaml_error:
        print(f"WARNING: Generated block.yaml has issues: {yaml_error}")
        print("  The block was still created, but you should fix this before use.")

    run_error = validate_generated_run_py(run_path)
    if run_error:
        print(f"WARNING: Generated run.py has issues: {run_error}")
        print("  The block was still created, but you should fix this before use.")

    # ── Success output ───────────────────────────────────────────────────
    rel_dir = os.path.relpath(block_dir, project_root)
    print(f"Created block: {rel_dir}/")
    print(f"  block.yaml  — {args.category} block schema")
    print(f"  run.py      — {args.category}-specific execution skeleton")
    print()
    print("Next steps:")
    print(f"  1. Edit block.yaml to define your inputs, outputs, and config")
    print(f"  2. Implement your logic in run.py")
    print(f"  3. Test: python -m backend.tests.block_runner {rel_dir}")

    if not yaml_error and not run_error:
        sys.exit(0)
    else:
        sys.exit(2)  # Created but with warnings


if __name__ == "__main__":
    main()
