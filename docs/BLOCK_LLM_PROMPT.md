# Blueprint Block Generator Prompt

You are generating a block for Blueprint, an ML experiment workbench. A block is a self-contained processing unit in a visual pipeline.

## Block SDK API

Every block is a directory with two files:

### block.yaml

Declares metadata, inputs, outputs, and config. Full schema:

```yaml
name: Human-Readable Name        # Required. Display name in the UI
type: block_type_id               # Required. Unique ID (lowercase, underscores). Must match directory name
category: category_name           # Required. One of: data, inference, training, evaluation, flow, agents, endpoints, merge, output
description: One-line description # Required. Shown in block palette
version: "1.0.0"                  # Required. Semantic version

inputs:                           # Required (can be empty list [])
  - id: port_id                   # Unique port identifier (used in run.py)
    label: Display Label          # UI label
    data_type: dataset            # One of: dataset, data, text, model, config, metrics, embedding, artifact, agent, any
    required: true                # Whether a connection is mandatory
    description: "Help text"      # Tooltip in the UI

outputs:                          # Required
  - id: port_id
    label: Display Label
    data_type: text
    description: "Help text"

config:                           # Optional. Map of user-configurable fields
  field_name:
    type: string                  # One of: string, text_area, integer, float, boolean, select, multiselect, file_path
    label: Field Label            # UI label
    description: "Help text"
    default: value                # Default value (applied automatically if user doesn't set one)

    # For select/multiselect only:
    options: [option1, option2, option3]

    # For integer/float only:
    min: 0
    max: 100

    # For conditional visibility (optional):
    depends_on:
      field: other_field_name
      value: expected_value
```

**Data type reference:**

| Type | Use For |
|------|---------|
| `dataset` | Structured data: DataFrames, JSON lists, CSV files |
| `data` | Generic data (alias for dataset in some contexts) |
| `text` | Raw text, prompts, documents |
| `model` | Model weights, checkpoints, HuggingFace IDs |
| `config` | Configuration dicts, hyperparameters |
| `metrics` | Scores, loss values, evaluation results |
| `embedding` | Vector embeddings |
| `artifact` | Files, reports, packages |
| `agent` | Agent state objects |
| `any` | Generic pass-through |

**Config field type reference:**

| Type | Description |
|------|-------------|
| `string` | Single-line text |
| `text_area` | Multi-line text (code, templates) |
| `integer` | Whole number (optional `min`/`max`) |
| `float` | Decimal number (optional `min`/`max`) |
| `boolean` | True/false toggle |
| `select` | Single-choice dropdown (requires `options`) |
| `multiselect` | Multi-choice (requires `options`) |
| `file_path` | File picker |

### run.py

Contains the block's execution logic. Must export a single function:

```python
def run(ctx):
    """Entry point. ctx is a BlockContext instance."""
    pass
```

**BlockContext API:**

```python
# ── Reading config and inputs ────────────────────────────────────────
ctx.config.get("key", default)    # Read a config value
ctx.inputs                        # Dict of connected input port values {port_id: data}
ctx.load_input("port_id")        # Load input data (raises ValueError if not connected)
                                  # Auto-fingerprints datasets for reproducibility

# ── Saving outputs ───────────────────────────────────────────────────
ctx.save_output("port_id", data)  # Save output for downstream blocks
                                  # data can be a file path (str) or in-memory object
ctx.save_artifact("name", path)   # Copy a file to run artifacts

# ── Logging and progress ────────────────────────────────────────────
ctx.log_message("text")           # Log to the live log panel in the UI
ctx.log_metric("name", value)     # Log a metric (forwarded to MLflow)
ctx.log_metric("name", val, step) # Log with step number for time series
ctx.report_progress(current, total)  # Update progress bar (e.g., 50, 100 = 50%)

# ── Properties ───────────────────────────────────────────────────────
ctx.run_dir          # str — Directory to write output files to
ctx.block_dir        # str — Block's own source directory
ctx.project_name     # str — Current project name
ctx.experiment_name  # str — Current experiment name
```

**Exception classes** (import from `backend.block_sdk.exceptions`):

```python
class BlockError(Exception):
    """Base. Args: message, *, details="", recoverable=False"""

class BlockInputError(BlockError):
    """Missing or invalid input data. Args: message, *, details="", recoverable=False"""

class BlockConfigError(BlockError):
    """Invalid config value. Args: field, message, *, details="", recoverable=True"""

class BlockTimeoutError(BlockError):
    """Exceeded time limit. Args: timeout_seconds, message=""."""

class BlockMemoryError(BlockError):
    """Out of memory. Args: message="Insufficient memory..."."""

class BlockDependencyError(BlockError):
    """Missing library. Args: dependency, message="", install_hint=""."""

class BlockDataError(BlockError):
    """Valid structure, bad content. Args: message, *, details="", recoverable=False"""
```

### Example: Complete Working Block

**`blocks/data/text_input/block.yaml`:**

```yaml
name: Text Input
type: text_input
category: data
description: Provide raw text or prompt input with format hints for downstream blocks
version: "2.0.0"

inputs: []

outputs:
  - id: text
    label: Text Output
    data_type: text
    description: "Plain text file with specified encoding"

config:
  text_value:
    type: text_area
    label: Text Value
    description: Raw text to be used as input for other blocks
    default: "Enter your text here..."
  format:
    type: select
    label: Format
    options: [plain, markdown, json, csv]
    default: plain
  encoding:
    type: select
    label: Encoding
    options: [utf-8, ascii, latin-1]
    default: utf-8
```

**`blocks/data/text_input/run.py`:**

```python
"""Text Input — simple block that passes a configured text payload downstream."""

import json
import os


def run(ctx):
    text_value = ctx.config.get("text_value", "")
    fmt = ctx.config.get("format", "plain")
    encoding = ctx.config.get("encoding", "utf-8")

    ctx.log_message(f"Text input: {len(text_value)} chars (format={fmt})")

    # Validate format-specific content
    if fmt == "json":
        try:
            json.loads(text_value)
            ctx.log_message("JSON syntax is valid")
        except (json.JSONDecodeError, ValueError) as e:
            ctx.log_message(f"WARNING: Text marked as JSON but is not valid: {e}")

    # Write text output
    out_path = os.path.join(ctx.run_dir, "text_input.txt")
    with open(out_path, "w", encoding=encoding) as f:
        f.write(text_value)

    # Write metadata sidecar
    metadata = {
        "format": fmt,
        "encoding": encoding,
        "char_count": len(text_value),
        "line_count": len(text_value.splitlines()),
    }
    meta_path = os.path.join(ctx.run_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    ctx.log_metric("char_count", len(text_value))
    ctx.log_metric("line_count", len(text_value.splitlines()))
    ctx.report_progress(1, 1)
    ctx.save_output("text", out_path)
```

### Example: Block with Inputs, Error Handling, and Iteration

**`blocks/evaluation/simple_scorer/block.yaml`:**

```yaml
name: Simple Scorer
type: simple_scorer
category: evaluation
description: Score model outputs against reference data with a configurable metric
version: "1.0.0"

inputs:
  - id: predictions
    label: Predictions
    data_type: dataset
    required: true
    description: "Model predictions (JSON list)"
  - id: references
    label: References
    data_type: dataset
    required: false
    description: "Ground truth labels (JSON list, same length as predictions)"

outputs:
  - id: scores
    label: Scores
    data_type: metrics
    description: "Aggregate evaluation scores"
  - id: report
    label: Report
    data_type: artifact
    description: "Per-sample scoring report"

config:
  metric:
    type: select
    label: Metric
    options: [exact_match, contains, length_ratio]
    default: exact_match
    description: "Scoring method to use"
  error_handling:
    type: select
    label: Error Handling
    options: [skip_errors, fail_fast]
    default: skip_errors
```

**`blocks/evaluation/simple_scorer/run.py`:**

```python
"""Simple Scorer — compare predictions against references."""

import json
import os

from backend.block_sdk.exceptions import BlockConfigError, BlockDataError, BlockInputError


def _load_as_list(raw):
    """Normalize input to a list, loading from file if needed."""
    if isinstance(raw, str) and os.path.isfile(raw):
        with open(raw, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(raw, (list, dict)):
        data = raw
    elif isinstance(raw, str):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            data = [raw]
    else:
        raise BlockInputError(f"Cannot load data of type {type(raw).__name__}")
    return data if isinstance(data, list) else [data]


def _score_sample(pred, ref, metric):
    """Score a single prediction against a reference."""
    pred_str = str(pred)
    ref_str = str(ref) if ref is not None else ""

    if metric == "exact_match":
        return 1.0 if pred_str.strip() == ref_str.strip() else 0.0
    elif metric == "contains":
        return 1.0 if ref_str.strip() in pred_str else 0.0
    elif metric == "length_ratio":
        if not ref_str:
            return 1.0
        return min(len(pred_str) / max(len(ref_str), 1), 2.0)
    else:
        raise BlockConfigError("metric", f"Unknown metric: {metric}")


def run(ctx):
    metric = ctx.config.get("metric", "exact_match")
    error_handling = ctx.config.get("error_handling", "skip_errors")

    ctx.log_message(f"Scoring with metric: {metric}")

    # Load inputs
    predictions = _load_as_list(ctx.load_input("predictions"))
    references = []
    if ctx.inputs.get("references"):
        references = _load_as_list(ctx.load_input("references"))

    if not predictions:
        raise BlockDataError("No predictions to evaluate")

    ctx.log_message(f"Evaluating {len(predictions)} samples")

    # Score each sample
    scores = []
    errors = 0
    for i, pred in enumerate(predictions):
        ref = references[i] if i < len(references) else None
        try:
            score = _score_sample(pred, ref, metric)
            scores.append({"index": i, metric: score})
        except Exception as e:
            errors += 1
            ctx.log_message(f"Scoring error at index {i}: {e}")
            if error_handling == "fail_fast":
                raise
        ctx.report_progress(i + 1, len(predictions))

    # Aggregate
    values = [s[metric] for s in scores]
    avg_score = sum(values) / len(values) if values else 0.0
    aggregate = {metric: avg_score, "total": len(predictions), "errors": errors}

    ctx.log_metric(metric, avg_score)
    ctx.log_message(f"{metric}: {avg_score:.4f} ({len(scores)}/{len(predictions)} scored)")

    # Save outputs
    ctx.save_output("scores", aggregate)

    report_path = os.path.join(ctx.run_dir, "eval_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"summary": aggregate, "per_sample": scores}, f, indent=2)
    ctx.save_output("report", report_path)
```

## Rules

1. Every output file MUST be written to `ctx.run_dir`
2. Every declared output port MUST have a corresponding `ctx.save_output()` call
3. Always call `ctx.report_progress()` for operations over 1 second
4. Use `BlockError` subclasses for errors, not bare `Exception`
5. Guard external imports with try/except and raise `BlockDependencyError`
6. Config fields should have sensible defaults
7. The `type` field in block.yaml must match the directory name exactly

## Your Task

Generate a complete block (`block.yaml` + `run.py`) for the following:

[USER: DESCRIBE YOUR BLOCK REQUIREMENTS HERE]
