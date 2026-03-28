# Block Author's Cookbook

A comprehensive guide to creating custom blocks for Blueprint.

---

## 1. Quick Start

Every block is a directory with two files: `block.yaml` (metadata) and `run.py` (logic).

```
blocks/data/hello/
├── block.yaml
└── run.py
```

**block.yaml** — declares what the block is and what it accepts:

```yaml
name: Hello
type: hello
category: data
description: Emits a greeting
version: "1.0.0"
inputs: []
outputs:
  - id: text
    label: Text
    data_type: text
    description: "The greeting message"
config:
  name:
    type: string
    label: Name
    default: "World"
    description: "Who to greet"
```

**run.py** — implements the logic:

```python
import os

def run(ctx):
    name = ctx.config.get("name", "World")
    out = os.path.join(ctx.run_dir, "output.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"Hello, {name}!")
    ctx.save_output("text", out)
    ctx.report_progress(1, 1)
```

That's it. Place this under `blocks/data/hello/` and it will be auto-discovered by the block registry.

**Or use the scaffold tool:**

```bash
python scripts/scaffold_block.py --name "Hello" --category data --type hello
```

---

## 2. Block Anatomy

### 2.1 block.yaml Fields Reference

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Human-readable display name |
| `type` | Yes | Unique identifier (lowercase, underscores). Must match directory name |
| `category` | Yes | One of: `data`, `inference`, `training`, `evaluation`, `flow`, `agents`, `endpoints`, `merge`, `output` |
| `description` | Yes | One-line description shown in the UI |
| `version` | Yes | Semantic version string (e.g. `"2.0.0"`) |
| `inputs` | Yes | List of input port definitions (can be `[]`) |
| `outputs` | Yes | List of output port definitions |
| `config` | No | Map of configuration field definitions |

#### Input/Output Port Definition

```yaml
inputs:
  - id: dataset          # Unique port ID (used in run.py)
    label: Dataset       # UI label
    data_type: dataset   # Type constraint (see table below)
    required: true       # Whether connection is mandatory
    description: "Help text for the UI"
```

#### Supported Data Types

| Type | Description |
|------|-------------|
| `dataset` | Structured data (DataFrames, JSON lists, CSV files) |
| `data` | Generic data (alias for dataset in some contexts) |
| `text` | Raw text, prompts, documents |
| `model` | Model weights, checkpoints, HuggingFace model IDs |
| `config` | Configuration dicts, hyperparameters |
| `metrics` | Evaluation scores, loss values |
| `embedding` | Vector embeddings |
| `artifact` | Files, reports, packages |
| `agent` | Agent state objects |
| `any` | Accepts anything (generic pass-through) |

#### Config Field Definition

```yaml
config:
  field_name:
    type: string         # Field type (see table below)
    label: Field Label   # UI label
    description: "Help text"
    default: value       # Default value (applied if user doesn't set one)

    # For select/multiselect:
    options: [a, b, c]

    # For numeric types:
    min: 0
    max: 100

    # For conditional visibility:
    depends_on:
      field: other_field
      value: expected_value
```

#### Config Field Types

| Type | Description |
|------|-------------|
| `string` | Single-line text input |
| `text_area` | Multi-line text (code, templates, prompts) |
| `integer` | Whole number with optional `min`/`max` bounds |
| `float` | Decimal number with optional `min`/`max` bounds |
| `boolean` | True/false toggle |
| `select` | Dropdown (requires `options` list) |
| `multiselect` | Multi-choice (requires `options` list) |
| `file_path` | File picker |

#### Config-to-Input Port Mapping (Connected Input Satisfaction)

When an input port is connected, mandatory config fields that correspond to that
port are automatically satisfied — the executor skips the "required" check.
This means blocks like `lora_finetuning` can have `model_name` marked as
`mandatory: true` in the config schema, but if the `model` input port is
connected, the user does not need to fill in `model_name` manually.

The built-in mapping (in `schema_validator.py`) is:

| Config Field | Satisfied by Input Port |
|--------------|------------------------|
| `model_name` | `model` |
| `model_id` | `model` |
| `dataset_name` | `dataset` |
| `file_path` | `dataset` |
| `directory_path` | `dataset` |
| `teacher_model` | `teacher` |
| `student_model` | `student` |
| `reward_model` | `reward_model` |
| `checkpoint_dir` | `model` |
| `url` | `config` |

**Example:** A block with `mandatory: true` on `model_name`:

```yaml
config:
  model_name:
    type: string
    label: Model Name
    mandatory: true
```

If the block also has an input port with `id: model`, connecting that port
removes the need for the user to set `model_name` in the UI.

#### Input Port Type Checking and Multi-Input

Input ports support optional type family and cardinality declarations:

```yaml
inputs:
  - id: model
    label: Model
    data_type: model
    expected_type_family: dict    # dict | str | list | path | any (default: any)
    cardinality: scalar           # scalar | list | any (default: any)
    multi_input: error            # aggregate | last_write | error (default: aggregate)
```

- **`expected_type_family`** — In V1, mismatches produce a warning log (not an
  error), so existing blocks continue to work. Declare this when you want to
  catch wiring mistakes early.
- **`cardinality`** — `scalar` warns if a list arrives, `list` warns if a non-list
  arrives, `any` accepts both.
- **`multi_input`** — Controls behavior when multiple edges connect to the same
  input port: `aggregate` collects values into a list, `last_write` keeps only
  the last value, `error` rejects the pipeline.

### 2.2 run.py API Reference

Every `run.py` must export a single function:

```python
def run(ctx):
    """Entry point. ctx is a BlockContext instance."""
    pass
```

#### BlockContext API

| Method | Signature | Description |
|--------|-----------|-------------|
| **Inputs** | | |
| `ctx.config.get(key, default)` | `(str, Any) -> Any` | Read a config value |
| `ctx.inputs` | `dict[str, Any]` | Dict of connected input port values |
| `ctx.load_input(name)` | `(str) -> Any` | Load raw input data (raises `ValueError` if not connected) |
| `ctx.resolve_as_file_path(name)` | `(str) -> str` | Resolve input to a file path (serializes dicts/lists to temp files) |
| `ctx.resolve_as_data(name)` | `(str) -> list[dict]` | Resolve input to in-memory rows (loads files, wraps dicts/strings) |
| `ctx.resolve_as_text(name)` | `(str) -> str` | Resolve input to a plain string (reads files, serializes dicts) |
| `ctx.resolve_as_dict(name)` | `(str) -> dict` | Resolve input to a dict (loads JSON files, parses strings) |
| `ctx.resolve_model_info(name)` | `(str) -> dict` | Resolve model input to normalized model info dict |
| **Outputs** | | |
| `ctx.save_output(name, data_or_path)` | `(str, Any) -> None` | Save output for downstream blocks |
| `ctx.save_artifact(name, file_path)` | `(str, str) -> None` | Copy a file to run artifacts |
| **Logging** | | |
| `ctx.log_message(msg)` | `(str) -> None` | Log to the live log panel |
| `ctx.log_metric(name, value, step=None)` | `(str, float, int?) -> None` | Log a metric (forwarded to MLflow) |
| `ctx.report_progress(current, total)` | `(int, int) -> None` | Update progress bar and ETA |
| **Properties** | | |
| `ctx.run_dir` | `str` | Directory to write output files to |
| `ctx.block_dir` | `str` | Block's own source directory |
| `ctx.project_name` | `str` | Current project name |
| `ctx.experiment_name` | `str` | Current experiment name |

#### Exception Classes

Import from `backend.block_sdk.exceptions`:

| Exception | When to Use | Constructor |
|-----------|-------------|-------------|
| `BlockError` | Base class for all block errors | `(message, *, details="", recoverable=False)` |
| `BlockInputError` | Missing or invalid input data | `(message, *, details="", recoverable=False)` |
| `BlockConfigError` | Invalid configuration value | `(field, message, *, details="", recoverable=True)` |
| `BlockTimeoutError` | Execution exceeded time limit | `(timeout_seconds, message="")` |
| `BlockMemoryError` | Insufficient memory | `(message="Insufficient memory...")` |
| `BlockDependencyError` | Missing library or service | `(dependency, message="", install_hint="")` |
| `BlockDataError` | Data structurally valid but content is bad | `(message, *, details="", recoverable=False)` |

---

## 3. Common Patterns

### 3.1 Loading a HuggingFace Model

```python
def run(ctx):
    model_name = ctx.config.get("model_name", "bert-base-uncased")
    ctx.log_message(f"Loading model: {model_name}")

    try:
        from transformers import AutoModel, AutoTokenizer
    except ImportError:
        from backend.block_sdk.exceptions import BlockDependencyError
        raise BlockDependencyError(
            "transformers",
            install_hint="pip install transformers"
        )

    ctx.report_progress(1, 3)
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    ctx.report_progress(2, 3)
    model = AutoModel.from_pretrained(model_name)

    ctx.log_message(f"Loaded {model_name} ({sum(p.numel() for p in model.parameters())} params)")
    ctx.save_output("model", {"model": model, "tokenizer": tokenizer, "model_name": model_name})
    ctx.report_progress(3, 3)
```

### 3.2 Streaming Progress During Training Loops

```python
def run(ctx):
    epochs = int(ctx.config.get("epochs", 10))
    batch_size = int(ctx.config.get("batch_size", 32))

    dataset = ctx.load_input("dataset")
    num_batches = max(1, len(dataset) // batch_size)
    total_steps = epochs * num_batches
    step = 0

    for epoch in range(epochs):
        epoch_loss = 0.0
        for batch_idx in range(0, len(dataset), batch_size):
            batch = dataset[batch_idx:batch_idx + batch_size]

            # Your training logic here — this is a placeholder
            loss = your_train_step(model, batch)
            epoch_loss += loss

            step += 1
            ctx.report_progress(step, total_steps)
            ctx.log_metric("training/loss", loss, step=step)

        avg_loss = epoch_loss / num_batches
        ctx.log_message(f"Epoch {epoch+1}/{epochs} — avg loss: {avg_loss:.4f}")
        ctx.log_metric("training/epoch_loss", avg_loss, step=epoch)
```

### 3.3 Handling GPU/CPU Fallback

```python
from backend.block_sdk.exceptions import BlockDependencyError

def run(ctx):
    try:
        import torch
    except ImportError:
        raise BlockDependencyError("torch", install_hint="pip install torch")

    if torch.cuda.is_available():
        device = torch.device("cuda")
        ctx.log_message(f"Using GPU: {torch.cuda.get_device_name(0)}")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = torch.device("mps")
        ctx.log_message("Using Apple Silicon GPU (MPS)")
    else:
        device = torch.device("cpu")
        ctx.log_message("Using CPU (no GPU available)")

    ctx.log_metric("device", str(device))

    # ... load and move model to device ...
    model = model.to(device)
```

### 3.4 Reading Inputs (The Right Way)

Always use `resolve_*` methods instead of raw `load_input()`. They normalize
upstream output into the format your block expects, regardless of whether the
upstream block saved a file path, a directory, a dict, or a raw string.

| What you need | Method | Returns |
|--------------|--------|---------|
| A file path to read | `ctx.resolve_as_file_path("dataset")` | String path to a file |
| In-memory data rows | `ctx.resolve_as_data("dataset")` | `list[dict]` |
| Plain text content | `ctx.resolve_as_text("prompt")` | `str` |
| A config/settings dict | `ctx.resolve_as_dict("config")` | `dict` |
| Model connection info | `ctx.resolve_model_info("model")` | `dict` with model_name, source, etc. |

**Do NOT do this:**

```python
# BAD — will crash if upstream saves a file path
data = ctx.load_input("dataset")
for row in data:  # TypeError if data is a string path!
    print(row["text"])
```

**Do this instead:**

```python
# GOOD — works regardless of upstream format
data = ctx.resolve_as_data("dataset")
for row in data:
    print(row["text"])
```

**More examples:**

```python
def run(ctx):
    # Read a dataset as in-memory rows (handles file paths, dirs, dicts, lists)
    rows = ctx.resolve_as_data("dataset")
    ctx.log_message(f"Loaded {len(rows)} rows")

    # Read a prompt as plain text (handles file paths too)
    prompt = ctx.resolve_as_text("prompt")

    # Read model info with normalized keys
    model = ctx.resolve_model_info("model")
    ctx.log_message(f"Using model: {model['model_name']} via {model['source']}")

    # Get a file path (serializes dicts/lists to temp JSON if needed)
    path = ctx.resolve_as_file_path("dataset")
    with open(path) as f:
        raw = f.read()
```

### 3.5 Reading Upstream Dataset Outputs (Legacy)

> **Prefer `resolve_*` methods above.** The pattern below still works but
> requires manual format handling that `resolve_as_data()` does automatically.

```python
import json
import os

from backend.block_sdk.exceptions import BlockInputError

def run(ctx):
    raw = ctx.load_input("dataset")

    # Case 1: File path (most common for dataset outputs)
    if isinstance(raw, str) and os.path.isfile(raw):
        if raw.endswith(".json"):
            with open(raw, "r", encoding="utf-8") as f:
                data = json.load(f)
        elif raw.endswith(".csv"):
            import csv
            with open(raw, "r", encoding="utf-8") as f:
                data = list(csv.DictReader(f))
        else:
            with open(raw, "r", encoding="utf-8") as f:
                data = f.read()
        ctx.log_message(f"Loaded dataset from {os.path.basename(raw)}")

    # Case 2: In-memory data (dicts, lists)
    elif isinstance(raw, (dict, list)):
        data = raw
        ctx.log_message(f"Received in-memory data: {type(raw).__name__}")

    # Case 3: Raw string content (not a file path)
    elif isinstance(raw, str):
        data = raw
        ctx.log_message(f"Received text input: {len(raw)} chars")

    else:
        raise BlockInputError(f"Unexpected input type: {type(raw).__name__}")

    # ... process data ...
    ctx.save_output("result", data)
    ctx.report_progress(1, 1)
```

### 3.6 Emitting Metrics with Proper Aggregation

```python
def run(ctx):
    # Simple metrics (default aggregation: "last")
    ctx.log_metric("accuracy", 0.95)
    ctx.log_metric("f1_score", 0.88)

    # Stepped metrics (tracked over time)
    for epoch in range(10):
        loss = train_epoch()           # your training function
        ctx.log_metric("training/loss", loss, step=epoch)
        ctx.log_metric("training/lr", get_lr(), step=epoch)  # your LR scheduler

    # Namespaced metrics for organization
    ctx.log_metric("eval/bleu", 32.5)
    ctx.log_metric("eval/rouge_l", 0.41)
    ctx.log_metric("inference/latency_ms", 145)
    ctx.log_metric("inference/tokens_per_sec", 52.3)
```

Aggregation strategies (used by the metrics system):
- `"last"` — Use the final value (default)
- `"min"` — Use the minimum across all steps
- `"max"` — Use the maximum across all steps
- `"mean"` — Average across all steps

### 3.7 Error Handling with BlockError Subclasses

```python
from backend.block_sdk.exceptions import (
    BlockInputError,
    BlockConfigError,
    BlockDependencyError,
    BlockDataError,
)

def run(ctx):
    # Validate config
    lr = ctx.config.get("learning_rate")
    if lr is None:
        raise BlockConfigError("learning_rate", "Learning rate is required")

    # Validate inputs
    dataset = ctx.inputs.get("dataset")
    if not dataset:
        raise BlockInputError(
            "Dataset input is not connected",
            details="Connect a data source to the 'dataset' port."
        )

    data = ctx.load_input("dataset")

    # Validate data content
    if isinstance(data, list) and len(data) == 0:
        raise BlockDataError(
            "Dataset is empty",
            details="The upstream block produced an empty dataset."
        )

    # Check dependencies
    try:
        import torch
    except ImportError:
        raise BlockDependencyError(
            "torch",
            install_hint="pip install torch"
        )

    # ... block logic ...
```

### 3.8 Checkpoint Saving

Use `ctx.save_artifact()` for intermediate checkpoints and `ctx.save_output()` for the final result:

```python
import json
import os
import torch

def run(ctx):
    epochs = int(ctx.config.get("epochs", 10))
    checkpoint_every = int(ctx.config.get("checkpoint_every", 5))

    # ... load model, optimizer, dataset ...

    for epoch in range(epochs):
        # Your training logic here
        loss = train_one_epoch(model, optimizer, dataset)

        ctx.log_metric("training/loss", loss, step=epoch)
        ctx.report_progress(epoch + 1, epochs)

        # Save checkpoint periodically
        if (epoch + 1) % checkpoint_every == 0:
            ckpt_path = os.path.join(ctx.run_dir, f"checkpoint_epoch_{epoch+1}.pt")
            torch.save({
                "epoch": epoch + 1,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "loss": loss,
            }, ckpt_path)
            ctx.save_artifact(f"checkpoint_epoch_{epoch+1}", ckpt_path)
            ctx.log_message(f"Saved checkpoint at epoch {epoch+1}")

    # Save final model as the block output
    final_path = os.path.join(ctx.run_dir, "final_model.pt")
    torch.save(model.state_dict(), final_path)
    ctx.save_output("model", final_path)
    ctx.log_message("Training complete")
```

### 3.9 Writing Output Files

Always write to `ctx.run_dir` and pass the path to `ctx.save_output`:

```python
import csv
import json
import os

def run(ctx):
    results = {"accuracy": 0.95, "samples": 1000}

    # JSON output
    out_path = os.path.join(ctx.run_dir, "results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    ctx.save_output("metrics", out_path)

    # CSV output (use the csv module for proper escaping)
    csv_path = os.path.join(ctx.run_dir, "predictions.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "prediction", "confidence"])
        writer.writeheader()
        writer.writerows(predictions)
    ctx.save_output("dataset", csv_path)

    # In-memory output (dicts, lists — no file needed)
    ctx.save_output("summary", {"accuracy": 0.95, "count": 42})
```

---

## 4. LLM Prompt Templates

### 4.1 Generating a Block with an LLM

Copy the self-contained prompt from [`docs/BLOCK_LLM_PROMPT.md`](BLOCK_LLM_PROMPT.md) into any LLM (Claude, GPT, etc.) and append your requirements. The prompt includes the full SDK reference, schema, and examples.

**Quick usage:**

```
[Paste BLOCK_LLM_PROMPT.md contents]

## Your Task
Generate a complete block (block.yaml + run.py) that normalizes
text columns in a dataset: lowercasing, stripping whitespace,
and removing special characters. Accept a config field for which
columns to normalize.
```

**Recommended workflow:**

1. Scaffold the block structure first:
   ```bash
   python scripts/scaffold_block.py --name "Text Normalizer" --category data
   ```
2. Paste `BLOCK_LLM_PROMPT.md` into an LLM with your requirements
3. Replace the generated `block.yaml` and `run.py` in the scaffolded directory
4. Validate: `python -m backend.tests.block_runner blocks/data/text_normalizer`

### 4.2 Describing Your Block to an LLM

When asking an LLM to generate a block, include:

1. **What the block does** — one sentence
2. **Inputs** — what data it receives and the expected format
3. **Outputs** — what data it produces and how it should be saved
4. **Config** — what the user should be able to configure
5. **Dependencies** — any Python libraries needed (must be guarded with `BlockDependencyError`)
6. **Category** — which category it belongs to (determines where it lives in `blocks/`)

**Example prompt addendum:**

```
Generate a Blueprint block that:
- Takes a dataset input (JSON list of dicts) and a text column name (config)
- Computes TF-IDF vectors for the text column
- Outputs the vectors as a numpy array saved to a .npy file
- Also outputs summary metrics (vocab size, avg document length)
- Category: data
- Requires: scikit-learn (guard with BlockDependencyError)
```

---

## 5. Validation Checklist

Before publishing a block, verify:

- [ ] `block.yaml` has all required fields (`name`, `type`, `category`, `description`, `version`, `inputs`, `outputs`)
- [ ] `type` in `block.yaml` matches the directory name
- [ ] `category` in `block.yaml` matches the parent directory name
- [ ] `run.py` has a `def run(ctx)` entry point
- [ ] All required inputs are documented with `required: true`
- [ ] Config fields have sensible `default` values
- [ ] `select` fields have an `options` list
- [ ] Numeric fields have `min`/`max` bounds where appropriate
- [ ] Error handling uses `BlockError` subclasses (not bare `raise Exception`)
- [ ] Progress is reported via `ctx.report_progress()` for long operations
- [ ] Outputs are saved via `ctx.save_output()` for every declared output port
- [ ] Output files are written to `ctx.run_dir` (not temp dirs or absolute paths)
- [ ] External dependencies are guarded with try/except and `BlockDependencyError`
- [ ] Block runs without errors: `python -m backend.tests.block_runner blocks/category/my_block`

### Quick Validation Script

```bash
# Preview what will be created
python scripts/scaffold_block.py --name "My Block" --category data --dry-run

# Scaffold a new block (category-aware template)
python scripts/scaffold_block.py --name "My Block" --category data --type my_block

# Verify it runs
python -m backend.tests.block_runner blocks/data/my_block
```

---

## 6. Publishing

### Adding to the Built-in Blocks Directory

1. Create your block directory under `blocks/{category}/{block_type}/`
2. Ensure `block.yaml` and `run.py` are complete
3. Run the validation checklist above
4. The block registry auto-discovers blocks — no registration step needed

### Directory Structure Rules

```
blocks/
└── {category}/           # Must be a valid category
    └── {block_type}/     # Must match the `type` field in block.yaml
        ├── block.yaml    # Required
        ├── run.py        # Required — must export def run(ctx)
        └── utils.py      # Optional — helper modules
```

### Block Discovery

The block registry (`backend/engine/block_registry.py`) scans `blocks/` automatically:

- Iterates `blocks/{category}/{block_type}/`
- Requires `run.py` to exist
- Directories starting with `.` or `_` are ignored
- No manual registration needed

### Config Propagation

Certain config keys propagate automatically through pipelines:

**Global keys** (always propagate): `text_column`, `seed`, `trust_remote_code`

**Category-specific keys:**
- `inference`: `system_prompt`
- `training`: `training_format`, `prompt_template`

If your block reads any of these keys, it may receive values set by upstream blocks unless the user explicitly overrides them.

---

## Appendix: Complete Example — Text Normalizer Block

A full, working block that normalizes text columns in a dataset.

### `blocks/data/text_normalizer/block.yaml`

```yaml
name: Text Normalizer
type: text_normalizer
category: data
description: Normalize text columns — lowercase, strip whitespace, remove special characters
version: "1.0.0"

inputs:
  - id: dataset
    label: Dataset
    data_type: dataset
    required: true
    description: "JSON list of dicts with text columns"

outputs:
  - id: dataset
    label: Normalized Dataset
    data_type: dataset
    description: "Dataset with normalized text columns"
  - id: report
    label: Report
    data_type: metrics
    description: "Normalization summary metrics"

config:
  columns:
    type: string
    label: Columns
    description: "Comma-separated column names to normalize"
    default: "text"
  lowercase:
    type: boolean
    label: Lowercase
    default: true
  strip_whitespace:
    type: boolean
    label: Strip Whitespace
    default: true
  remove_special_chars:
    type: boolean
    label: Remove Special Characters
    default: false
```

### `blocks/data/text_normalizer/run.py`

```python
"""Text Normalizer — cleans text columns in a dataset."""

import json
import os
import re

from backend.block_sdk.exceptions import BlockInputError, BlockDataError


def run(ctx):
    # Load config
    columns = [c.strip() for c in ctx.config.get("columns", "text").split(",")]
    do_lower = ctx.config.get("lowercase", True)
    do_strip = ctx.config.get("strip_whitespace", True)
    do_remove_special = ctx.config.get("remove_special_chars", False)

    ctx.log_message(f"Normalizing columns: {columns}")

    # Load input
    raw = ctx.load_input("dataset")
    if isinstance(raw, str) and os.path.isfile(raw):
        with open(raw, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(raw, list):
        data = raw
    else:
        raise BlockInputError("Expected a JSON list or file path")

    if not data:
        raise BlockDataError("Dataset is empty")

    # Normalize
    modified = 0
    for i, row in enumerate(data):
        for col in columns:
            if col in row and isinstance(row[col], str):
                original = row[col]
                val = row[col]
                if do_strip:
                    val = val.strip()
                    val = re.sub(r"\s+", " ", val)
                if do_lower:
                    val = val.lower()
                if do_remove_special:
                    val = re.sub(r"[^a-zA-Z0-9\s]", "", val)
                row[col] = val
                if val != original:
                    modified += 1
        ctx.report_progress(i + 1, len(data))

    # Save outputs
    out_path = os.path.join(ctx.run_dir, "normalized.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    ctx.save_output("dataset", out_path)

    report = {"total_rows": len(data), "modified_cells": modified, "columns": columns}
    ctx.save_output("report", report)

    ctx.log_metric("total_rows", len(data))
    ctx.log_metric("modified_cells", modified)
    ctx.log_message(f"Done: {modified} cells modified across {len(data)} rows")
```
