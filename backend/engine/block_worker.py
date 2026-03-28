"""Subprocess entry point for isolated block execution.

Accepts CLI args:
  --block-type       Block type identifier (e.g. 'llm_inference')
  --config           JSON string of block configuration
  --input-dir        Path to directory containing serialized inputs
  --output-dir       Path to directory for serialized outputs
  --progress-file    Path for JSON-lines progress updates

Loads the block via _find_block_module, creates a BlockContext with the
config and deserialized inputs, calls block.run(ctx), serializes outputs
to output-dir.  Writes progress updates to progress-file.

Data fingerprints are written to output-dir/fingerprints.json so the
parent process (SubprocessBlockRunner) can recover them.

This file is the execution boundary that makes timeout/cancel enforceable
via proc.kill().
"""

import argparse
import importlib.util
import json
import os
import sys
import time
import traceback
from pathlib import Path

# Ensure the repo root is on sys.path so blocks can do cross-block imports
_this_dir = Path(__file__).resolve().parent
_backend_dir = _this_dir.parent
_repo_root = _backend_dir.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend.config import BUILTIN_BLOCKS_DIR, BLOCKS_DIR, CUSTOM_BLOCKS_DIR
from backend.block_sdk.context import BlockContext
from backend.engine.block_aliases import SAFE_BLOCK_TYPE, BLOCK_ALIASES
from backend.engine.data_serializer import serialize_outputs, deserialize_inputs


def _find_block_module(block_type: str) -> Path | None:
    """Find the run.py directory for a given block type."""
    block_type = BLOCK_ALIASES.get(block_type, block_type)
    if not SAFE_BLOCK_TYPE.match(block_type):
        raise ValueError(f"Invalid block type: {block_type!r}")
    for base_dir in [BUILTIN_BLOCKS_DIR, BLOCKS_DIR]:
        if not base_dir.exists():
            continue
        for cat_dir in base_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            block_dir = cat_dir / block_type
            run_py = block_dir / "run.py"
            if run_py.exists():
                return block_dir
    if CUSTOM_BLOCKS_DIR.exists():
        block_dir = CUSTOM_BLOCKS_DIR / block_type
        run_py = block_dir / "run.py"
        if run_py.exists():
            return block_dir
    return None


def _write_progress(progress_file: str, percent: float, message: str):
    """Append a JSON-lines progress entry."""
    entry = {
        "percent": percent,
        "message": message,
        "timestamp": time.time(),
    }
    with open(progress_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Blueprint block worker subprocess")
    parser.add_argument("--block-type", required=True, help="Block type identifier")
    parser.add_argument("--config", required=True, help="JSON string of block config")
    parser.add_argument("--input-dir", required=True, help="Path to serialized inputs")
    parser.add_argument("--output-dir", required=True, help="Path for serialized outputs")
    parser.add_argument("--progress-file", required=True, help="Path for progress updates")
    args = parser.parse_args()

    block_type = args.block_type
    config = json.loads(args.config)
    input_dir = args.input_dir
    output_dir = args.output_dir
    progress_file = args.progress_file

    os.makedirs(output_dir, exist_ok=True)

    # Write initial progress
    _write_progress(progress_file, 0.0, "Starting block execution")

    # Find block
    block_dir = _find_block_module(block_type)
    if block_dir is None:
        print(f"ERROR: Block type '{block_type}' not found", file=sys.stderr)
        sys.exit(1)

    # Ensure blocks parent is on sys.path for cross-block imports
    blocks_parent = str(BUILTIN_BLOCKS_DIR.parent)
    if blocks_parent not in sys.path:
        sys.path.insert(0, blocks_parent)

    # Load block module
    run_py = block_dir / "run.py"
    spec = importlib.util.spec_from_file_location(f"block_{block_type}", str(run_py))
    if spec is None or spec.loader is None:
        print(f"ERROR: Cannot load block module from {run_py}", file=sys.stderr)
        sys.exit(1)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "run"):
        print(f"ERROR: Block {block_dir.name} missing run() function", file=sys.stderr)
        sys.exit(1)

    # Deserialize inputs (handles numpy, torch, pandas, pickle formats)
    inputs = deserialize_inputs(input_dir)

    # Create callbacks that write to progress file
    def progress_callback(current, total):
        percent = current / total if total > 0 else 0
        _write_progress(progress_file, percent, f"Progress: {current}/{total}")

    def message_callback(msg):
        _write_progress(progress_file, -1, msg)

    def metric_callback(name, value, step):
        entry = {
            "percent": -1,
            "message": f"metric:{name}={value}",
            "metric_name": name,
            "metric_value": value,
            "metric_step": step,
            "timestamp": time.time(),
        }
        with open(progress_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    # Create context and run
    run_dir = output_dir
    ctx = BlockContext(
        run_dir=run_dir,
        block_dir=str(block_dir),
        config=config,
        inputs=inputs,
        progress_callback=progress_callback,
        message_callback=message_callback,
        metric_callback=metric_callback,
    )

    try:
        module.run(ctx)
    except Exception as e:
        tb = traceback.format_exc()
        _write_progress(progress_file, -1, f"ERROR: {e}")
        print(f"BLOCK_ERROR:{type(e).__name__}:{e}", file=sys.stderr)
        print(tb, file=sys.stderr)
        sys.exit(2)

    # Serialize outputs (handles numpy, torch, pandas, pickle formats)
    outputs = ctx.get_outputs()
    serialize_outputs(outputs, output_dir)

    # Write data fingerprints so the parent process can recover them
    fingerprints = ctx.get_data_fingerprints()
    if fingerprints:
        fp_path = os.path.join(output_dir, "fingerprints.json")
        with open(fp_path, "w") as f:
            json.dump(fingerprints, f, indent=2, default=str)

    # Write completion progress
    _write_progress(progress_file, 1.0, "Block execution complete")

    # Write metrics to a separate file for the runner
    metrics = ctx.get_metrics()
    if metrics:
        metrics_path = os.path.join(output_dir, "metrics.json")
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)


if __name__ == "__main__":
    main()
