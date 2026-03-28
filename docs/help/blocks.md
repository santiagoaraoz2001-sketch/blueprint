# Block Reference

## What is a Block?

A block is the fundamental unit of computation in Blueprint. Each block performs a single, well-defined operation — loading data, transforming features, training a model, evaluating results, etc. Blocks are connected together in a pipeline to form a complete ML workflow.

## Block Anatomy

Every block is a directory containing two key files:

```
my-block/
  block.yaml    # Metadata, ports, and parameter definitions
  run.py        # Execution logic
```

### block.yaml

The `block.yaml` file declares the block's identity, inputs, outputs, and configurable parameters.

```yaml
name: Train Test Split
description: Split a dataset into training and testing subsets.
category: data
icon: scissors

inputs:
  - name: dataset
    type: dataframe
    description: The full dataset to split.

outputs:
  - name: train
    type: dataframe
    description: Training subset.
  - name: test
    type: dataframe
    description: Testing subset.

params:
  - name: test_size
    type: float
    default: 0.2
    min: 0.01
    max: 0.99
    description: Fraction of data to use for testing.
  - name: random_seed
    type: int
    default: 42
    description: Random seed for reproducibility.
  - name: stratify
    type: bool
    default: false
    description: Whether to perform stratified splitting.
```

### run.py

The `run.py` file contains the execution logic. It receives inputs and parameters, performs computation, and returns outputs.

```python
def run(inputs, params):
    from sklearn.model_selection import train_test_split

    df = inputs["dataset"]
    test_size = params.get("test_size", 0.2)
    seed = params.get("random_seed", 42)
    stratify_col = df.iloc[:, -1] if params.get("stratify") else None

    train_df, test_df = train_test_split(
        df, test_size=test_size, random_state=seed, stratify=stratify_col
    )

    return {"train": train_df, "test": test_df}
```

The `run` function signature is always `run(inputs, params)` where:

- `inputs` is a dictionary mapping input port names to their values.
- `params` is a dictionary mapping parameter names to their configured values.
- The return value is a dictionary mapping output port names to their values.

## Port Types

Ports define what data flows into and out of blocks. Each port has a type that determines compatibility.

| Type        | Python Type         | Description                                    |
|-------------|---------------------|------------------------------------------------|
| dataframe   | pandas.DataFrame    | Tabular data                                   |
| tensor      | numpy.ndarray       | Numerical arrays, tensors                      |
| model       | object              | Trained model (sklearn, PyTorch, etc.)         |
| text        | str                 | Plain text or string data                      |
| number      | int or float        | Scalar numeric value                           |
| json        | dict or list        | Structured JSON-serializable data              |
| image       | PIL.Image           | Image data                                     |
| any         | object              | Accepts any type (use sparingly)               |

Connections are only allowed between compatible port types. The `any` type accepts all other types.

## Block Categories

Blocks are organized into categories in the block palette:

### Data

Blocks for loading, splitting, and sampling datasets. Examples: Dataset Loader, CSV Reader, Train/Test Split, Data Sampler.

### Transform

Data preprocessing and feature engineering blocks. Examples: Normalize, One-Hot Encode, Feature Selector, Text Tokenizer, Image Resize.

### Model

Training and inference blocks for various ML frameworks. Examples: Sklearn Classifier, PyTorch Trainer, XGBoost Regressor, LLM Inference.

### Evaluate

Metrics and evaluation blocks. Examples: Accuracy, F1 Score, Confusion Matrix, ROC Curve, Loss Plot.

### Export

Blocks for saving outputs. Examples: CSV Writer, Model Saver, Report Generator, Artifact Logger.

### Utility

General-purpose helper blocks. Examples: Python Script (custom code), Logger, Timer, Conditional Branch.

## Creating Custom Blocks

You can create custom blocks by adding a new directory under the custom blocks folder.

1. Create a directory: `~/.specific-labs/custom_blocks/my-block/`
2. Add `block.yaml` with your metadata, ports, and parameters.
3. Add `run.py` with your `run(inputs, params)` function.
4. Restart Blueprint or use the block registry refresh to detect the new block.

Custom blocks appear in the block palette alongside built-in blocks, with a badge indicating they are user-created.

## Block Dependencies

Blocks can import any Python package in their `run.py`. Blueprint scans imports and tracks dependency status. Check **System > Dependencies** to see which packages are installed and which are missing. You can install missing packages directly from the UI.

## Best Practices

- Keep blocks focused on a single task. Prefer many small blocks over a few large ones.
- Always declare proper port types for type safety and clear pipeline visualization.
- Provide meaningful default values for parameters so blocks work out of the box.
- Include a clear `description` in `block.yaml` so users understand the block without reading code.
- Use `random_seed` parameters wherever randomness is involved for reproducibility.
