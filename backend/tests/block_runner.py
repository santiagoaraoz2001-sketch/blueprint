"""Block Test Runner — test a single block in isolation.

Usage:
    python -m backend.tests.block_runner <block_dir> [--fixture small|medium|realistic]
                                                     [--fixture-path /path/to/data.jsonl]
                                                     [--config key=value ...]
                                                     [--verbose] [--timeout SECONDS]

Examples:
    python -m backend.tests.block_runner blocks/data/text_input --config text_value="Hello World"
    python -m backend.tests.block_runner blocks/training/lora_finetuning --fixture small --config model_name=gpt2
    python -m backend.tests.block_runner blocks/training/ballast_training --fixture-path my_data.jsonl --verbose
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import shutil
import signal
import sys
import tempfile
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print(
        "Error: PyYAML is required but not installed.\n"
        "Install it with:  pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)

# Resolve project root (two levels up from backend/tests/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Add project root to path so block imports work
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.block_sdk.config_validator import validate_and_apply_defaults
from backend.block_sdk.context import BlockContext
from backend.block_sdk.exceptions import BlockError

# ── Fixtures ──────────────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

FIXTURE_SIZES = {
    "small": 10,
    "medium": 1000,
    "realistic": 10000,
}


def _load_fixture(name: str) -> str:
    """Load a named fixture file and return its path.

    Args:
        name: One of "small", "medium", "realistic".

    Returns:
        Absolute path to the fixture JSONL file.

    Raises:
        FileNotFoundError: If the named fixture does not exist and cannot
            be auto-generated.
    """
    fixture_path = FIXTURES_DIR / f"{name}.jsonl"
    if fixture_path.exists():
        return str(fixture_path)

    # Auto-generate for 'realistic' if not on disk
    if name == "realistic":
        return _generate_fixture(FIXTURE_SIZES["realistic"])

    raise FileNotFoundError(f"Fixture '{name}' not found at {fixture_path}")


def _load_fixture_path(path: str) -> str:
    """Validate and return an absolute path to a user-provided fixture file.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    fixture_path = Path(path)
    if not fixture_path.is_absolute():
        fixture_path = Path.cwd() / fixture_path
    if not fixture_path.is_file():
        raise FileNotFoundError(f"Fixture file not found: {fixture_path}")
    return str(fixture_path)


def _generate_fixture(num_rows: int) -> str:
    """Auto-generate a JSONL fixture with the given number of rows.

    Uses a fixed random seed for reproducibility.  The generated file is
    placed in the fixtures directory so subsequent runs can reuse it.

    Returns:
        Absolute path to the generated JSONL file.
    """
    import hashlib
    import random

    random.seed(42)

    topics = [
        "machine learning", "deep learning", "natural language processing",
        "computer vision", "reinforcement learning", "generative AI",
        "data science", "neural networks", "optimization", "transformers",
        "model evaluation", "transfer learning", "attention mechanisms",
        "backpropagation", "gradient descent", "fine-tuning",
    ]
    templates = [
        "A study on {topic} shows promising results in recent benchmarks.",
        "Researchers have found that {topic} can be applied to many problems.",
        "New advances in {topic} were presented at the latest conference.",
        "Understanding {topic} is essential for modern AI practitioners.",
        "Recent work in {topic} has been driven by increased compute power.",
        "Open-source tools have democratized access to {topic} techniques.",
        "The fundamentals of {topic} build on decades of mathematical work.",
        "Practitioners of {topic} must balance accuracy with efficiency.",
    ]
    labels = ["positive", "negative", "neutral"]

    # Write to fixtures dir so it persists across runs
    out_path = FIXTURES_DIR / "realistic.jsonl"
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        for _ in range(num_rows):
            topic = random.choice(topics)
            template = random.choice(templates)
            row = {
                "text": template.format(topic=topic),
                "label": random.choice(labels),
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return str(out_path)


# ── Auto-generate test inputs ────────────────────────────────────────────────


def _generate_input_for_type(
    data_type: str,
    input_id: str,
    fixture_path: str | None,
    run_dir: str,
    config: dict,
) -> Any:
    """Generate a mock input value for the given data_type.

    The generated value matches what upstream blocks typically produce for
    each port type.

    Args:
        data_type:    Port data_type from block.yaml (dataset, model, etc.).
        input_id:     Port ID, used for unique file naming.
        fixture_path: Optional path to a JSONL fixture file.
        run_dir:      Temporary run directory for writing files.
        config:       Block config dict, consulted for context (e.g. model_name).

    Returns:
        A value appropriate for the data type — typically a file path (str)
        or a dict.
    """
    if data_type == "dataset":
        return _generate_dataset_input(input_id, fixture_path, run_dir)

    if data_type == "text":
        text_path = os.path.join(run_dir, f"input_{input_id}.txt")
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(f"Sample test input for port '{input_id}'.")
        return text_path

    if data_type == "model":
        # Derive model_name from config when available so the mock is consistent
        model_name = config.get("model_name") or config.get("model_id", "")
        return {
            "model_name": model_name,
            "model_id": model_name,
            "source": "test_harness",
        }

    if data_type == "config":
        return {}

    if data_type == "metrics":
        return {}

    if data_type == "embedding":
        # Return a small list of mock embedding vectors
        return [[0.1 * i for i in range(8)] for _ in range(4)]

    if data_type == "artifact":
        artifact_path = os.path.join(run_dir, f"input_{input_id}")
        os.makedirs(artifact_path, exist_ok=True)
        return artifact_path

    if data_type == "data":
        return {}

    # "any" or unknown — return an empty dict as the safest default
    return {}


def _generate_dataset_input(
    input_id: str, fixture_path: str | None, run_dir: str,
) -> str:
    """Generate a dataset file from a fixture or from scratch.

    Blocks expect datasets as a path to a JSON file containing a list
    of dicts, or a directory containing ``data.json``.

    Returns:
        Path to the generated JSON data file.
    """
    data_json_path = os.path.join(run_dir, f"input_{input_id}.json")

    if fixture_path:
        # Convert JSONL fixture to JSON list
        rows: list[dict] = []
        with open(fixture_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    # Skip malformed rows — fixture may be intentionally bad
                    continue
        with open(data_json_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
        return data_json_path

    # No fixture — generate a minimal dataset that matches common schemas
    rows = [
        {"text": f"Auto-generated test sample {i}.", "label": "test"}
        for i in range(FIXTURE_SIZES["small"])
    ]
    with open(data_json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    return data_json_path


# ── Output formatting ────────────────────────────────────────────────────────

BOX_WIDTH = 60


def _box_top() -> str:
    return f"\u2554{'═' * BOX_WIDTH}\u2557"


def _box_bottom() -> str:
    return f"\u255a{'═' * BOX_WIDTH}\u255d"


def _box_sep() -> str:
    return f"\u2560{'═' * BOX_WIDTH}\u2563"


def _box_line(text: str) -> str:
    # Truncate to fit inside box (account for "║ " and " ║")
    display = text[: BOX_WIDTH - 2]
    return f"\u2551 {display:<{BOX_WIDTH - 2}} \u2551"


def _box_empty() -> str:
    return _box_line("")


def _format_bytes(n: int) -> str:
    """Format a byte count into a human-readable string."""
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


# ── Memory measurement ────────────────────────────────────────────────────────


def _get_peak_memory_mb() -> float:
    """Get peak resident set size in MB.

    Uses ``resource.getrusage`` on UNIX and ``psutil`` as a fallback.
    Returns 0 if measurement is unavailable (e.g. unsupported platform
    without psutil).
    """
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        if sys.platform == "darwin":
            # macOS reports ru_maxrss in bytes
            return usage.ru_maxrss / (1024 * 1024)
        # Linux reports ru_maxrss in kilobytes
        return usage.ru_maxrss / 1024
    except (ImportError, AttributeError):
        pass

    # Fallback for Windows or environments without resource module
    try:
        import psutil

        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)
    except ImportError:
        return 0.0


# ── Timeout support ───────────────────────────────────────────────────────────


class BlockTimeoutError(Exception):
    """Raised when a block exceeds its execution time limit."""


@contextmanager
def _timeout_context(seconds: int | None):
    """Context manager that raises ``BlockTimeoutError`` after *seconds*.

    On platforms that do not support ``signal.SIGALRM`` (e.g. Windows),
    this is a no-op — blocks run without a time limit.
    """
    if seconds is None or not hasattr(signal, "SIGALRM"):
        yield
        return

    def _handler(signum, frame):
        raise BlockTimeoutError(
            f"Block execution exceeded {seconds}s time limit"
        )

    old_handler = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


# ── Main runner ───────────────────────────────────────────────────────────────


def run_block_test(
    block_dir: str,
    fixture_name: str | None = None,
    fixture_path_override: str | None = None,
    config_overrides: dict[str, str] | None = None,
    verbose: bool = False,
    timeout: int | None = None,
) -> int:
    """Run a single block in isolation and report results.

    Args:
        block_dir:            Path to the block directory (absolute or
                              relative to project root).
        fixture_name:         Named fixture: "small", "medium", "realistic".
        fixture_path_override: Absolute or relative path to a custom JSONL
                              fixture file.  Overrides ``fixture_name``.
        config_overrides:     Dict of config key=value overrides from CLI.
        verbose:              If True, print block stdout and log messages.
        timeout:              Maximum execution time in seconds (None = no limit).

    Returns:
        0 on success, 1 on failure.
    """
    output_lines: list[str] = []

    def emit(line: str) -> None:
        output_lines.append(line)

    block_path = Path(block_dir)
    if not block_path.is_absolute():
        block_path = PROJECT_ROOT / block_path

    # ── Locate block files ────────────────────────────────────────────────
    block_yaml_path = block_path / "block.yaml"
    run_py_path = block_path / "run.py"

    if not block_yaml_path.exists():
        print(f"Error: block.yaml not found at {block_yaml_path}", file=sys.stderr)
        return 1
    if not run_py_path.exists():
        print(f"Error: run.py not found at {run_py_path}", file=sys.stderr)
        return 1

    # ── Parse block.yaml ──────────────────────────────────────────────────
    with open(block_yaml_path, "r", encoding="utf-8") as f:
        block_spec = yaml.safe_load(f)

    if not isinstance(block_spec, dict):
        print(f"Error: block.yaml is not a valid YAML mapping", file=sys.stderr)
        return 1

    block_name = block_spec.get("name", block_path.name)
    block_type = block_spec.get("type", block_path.name)
    inputs_spec = block_spec.get("inputs") or []
    config_schema = block_spec.get("config") or {}

    emit(_box_top())
    emit(_box_line(f"Block Test: {block_name}"))
    emit(_box_line(f"Path: {block_dir}"))
    emit(_box_sep())

    # ── Build config ──────────────────────────────────────────────────────
    config: dict[str, Any] = {}
    for key, spec in config_schema.items():
        if isinstance(spec, dict) and "default" in spec:
            config[key] = spec["default"]

    if config_overrides:
        for key, value in config_overrides.items():
            spec = config_schema.get(key, {})
            field_type = spec.get("type", "string") if isinstance(spec, dict) else "string"
            config[key] = _coerce_value(value, field_type)

    # ── Validation ────────────────────────────────────────────────────────
    try:
        config = validate_and_apply_defaults(config, config_schema)
        emit(_box_line("Validation .......... PASS"))
    except BlockError as e:
        emit(_box_line("Validation .......... FAIL"))
        emit(_box_empty())
        emit(_box_line(f"{type(e).__name__}: {e}"))
        if getattr(e, "field", None):
            emit(_box_line(f"Field: {e.field}"))
        emit(_box_line(f"Recoverable: {'Yes' if e.recoverable else 'No'}"))
        emit(_box_bottom())
        print("\n".join(output_lines))
        return 1

    # ── Set up execution environment ──────────────────────────────────────
    run_dir = tempfile.mkdtemp(prefix="block_test_")

    try:
        return _execute_block(
            block_path=block_path,
            block_name=block_name,
            block_type=block_type,
            run_py_path=run_py_path,
            inputs_spec=inputs_spec,
            config=config,
            run_dir=run_dir,
            fixture_name=fixture_name,
            fixture_path_override=fixture_path_override,
            verbose=verbose,
            timeout=timeout,
            output_lines=output_lines,
            emit=emit,
        )
    finally:
        # Clean up temporary run directory
        shutil.rmtree(run_dir, ignore_errors=True)


def _execute_block(
    *,
    block_path: Path,
    block_name: str,
    block_type: str,
    run_py_path: Path,
    inputs_spec: list[dict],
    config: dict,
    run_dir: str,
    fixture_name: str | None,
    fixture_path_override: str | None,
    verbose: bool,
    timeout: int | None,
    output_lines: list[str],
    emit,
) -> int:
    """Execute the block and produce the report.  Separated from
    ``run_block_test`` so that cleanup always runs in the ``finally``.
    """
    # ── Resolve fixture ───────────────────────────────────────────────────
    fixture_path: str | None = None
    if fixture_path_override:
        try:
            fixture_path = _load_fixture_path(fixture_path_override)
        except FileNotFoundError as e:
            emit(_box_line(f"Fixture ............. FAIL"))
            emit(_box_line(f"  {e}"))
            emit(_box_bottom())
            print("\n".join(output_lines))
            return 1
    elif fixture_name:
        try:
            fixture_path = _load_fixture(fixture_name)
        except FileNotFoundError as e:
            emit(_box_line(f"Fixture ............. FAIL"))
            emit(_box_line(f"  {e}"))
            emit(_box_bottom())
            print("\n".join(output_lines))
            return 1

    # ── Build inputs ──────────────────────────────────────────────────────
    inputs: dict[str, Any] = {}
    for inp in inputs_spec:
        inp_id = inp.get("id", "")
        inp_type = inp.get("data_type", "any")
        inp_required = inp.get("required", False)

        generated = _generate_input_for_type(
            data_type=inp_type,
            input_id=inp_id,
            fixture_path=fixture_path,
            run_dir=run_dir,
            config=config,
        )
        if generated is not None:
            inputs[inp_id] = generated
        elif inp_required:
            emit(_box_line(f"Input '{inp_id}' ....... MISSING (required)"))
            emit(_box_bottom())
            print("\n".join(output_lines))
            return 1

    # ── Mocked callbacks ──────────────────────────────────────────────────
    messages: list[str] = []
    metrics: dict[str, Any] = {}
    progress_state = {"current": 0, "total": 0}

    def progress_cb(current: int, total: int) -> None:
        progress_state["current"] = current
        progress_state["total"] = total

    def message_cb(msg: str) -> None:
        messages.append(msg)

    def metric_cb(name: str, value: float, step: int | None = None) -> None:
        metrics[name] = value

    ctx = BlockContext(
        run_dir=run_dir,
        block_dir=str(block_path),
        config=config,
        inputs=inputs,
        project_name="block_test",
        experiment_name="block_test",
        progress_callback=progress_cb,
        message_callback=message_cb,
        metric_callback=metric_cb,
    )

    # ── Execute ───────────────────────────────────────────────────────────
    start_time = time.perf_counter()

    try:
        # Load block module
        mod_spec = importlib.util.spec_from_file_location(
            f"block_{block_type}", str(run_py_path),
        )
        if mod_spec is None or mod_spec.loader is None:
            emit(_box_line("Execution ........... FAIL"))
            emit(_box_sep())
            emit(_box_line(f"Could not load module: {run_py_path}"))
            emit(_box_bottom())
            print("\n".join(output_lines))
            return 1

        module = importlib.util.module_from_spec(mod_spec)

        # Suppress direct stdout from block (e.g. BlockContext.log_message
        # calls print()).  Messages are captured via message_cb instead.
        captured_stdout = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured_stdout
        try:
            with _timeout_context(timeout):
                mod_spec.loader.exec_module(module)
                module.run(ctx)
        finally:
            sys.stdout = old_stdout
            stdout_text = captured_stdout.getvalue()

        elapsed = time.perf_counter() - start_time
        peak_mem = _get_peak_memory_mb()

        emit(_box_line(f"Execution ........... PASS ({elapsed:.1f}s)"))
        if peak_mem > 0:
            emit(_box_line(f"Peak Memory ......... {peak_mem:.0f} MB"))
        emit(_box_sep())

        # ── Report outputs ────────────────────────────────────────────────
        outputs = ctx.get_outputs()
        if outputs:
            emit(_box_line("Outputs:"))
            for name, value in outputs.items():
                display_val = str(value)
                if len(display_val) > 36:
                    display_val = display_val[:33] + "..."
                emit(_box_line(f"  {name:<16} {display_val}"))

        # ── Report metrics ────────────────────────────────────────────────
        all_metrics = {**ctx.get_metrics(), **metrics}
        if all_metrics:
            emit(_box_line("Metrics:"))
            for name, value in all_metrics.items():
                if isinstance(value, float):
                    emit(_box_line(f"  {name:<16} {value:.4g}"))
                else:
                    emit(_box_line(f"  {name:<16} {value}"))

        # ── Report artifacts ──────────────────────────────────────────────
        artifacts_dir = os.path.join(run_dir, "artifacts")
        if os.path.isdir(artifacts_dir):
            artifact_files: list[str] = []
            total_size = 0
            for root, _dirs, files in os.walk(artifacts_dir):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    try:
                        total_size += os.path.getsize(fpath)
                    except OSError:
                        pass
                    artifact_files.append(fname)
            if artifact_files:
                emit(_box_line(
                    f"Artifacts: {len(artifact_files)} file(s) "
                    f"({_format_bytes(total_size)})"
                ))

        emit(_box_bottom())
        print("\n".join(output_lines))
        _print_verbose(verbose, messages, stdout_text)

        return 0

    except BlockTimeoutError as e:
        elapsed = time.perf_counter() - start_time
        emit(_box_line(f"Execution ........... TIMEOUT ({elapsed:.1f}s)"))
        emit(_box_sep())
        emit(_box_line(str(e)))
        emit(_box_bottom())
        print("\n".join(output_lines))
        _print_verbose(verbose, messages, stdout_text)
        return 1

    except BlockError as e:
        elapsed = time.perf_counter() - start_time
        emit(_box_line(f"Execution ........... FAIL ({elapsed:.1f}s)"))
        emit(_box_sep())
        emit(_box_line(f"{type(e).__name__}: {e}"))
        if getattr(e, "field", None):
            emit(_box_line(f"Field: {e.field}"))
        emit(_box_line(f"Recoverable: {'Yes' if e.recoverable else 'No'}"))
        emit(_box_bottom())
        print("\n".join(output_lines))
        _print_verbose(verbose, messages, stdout_text)
        return 1

    except Exception as e:
        elapsed = time.perf_counter() - start_time
        emit(_box_line(f"Execution ........... FAIL ({elapsed:.1f}s)"))
        emit(_box_sep())
        emit(_box_line(f"{type(e).__name__}: {e}"))
        tb_lines = traceback.format_exc().strip().split("\n")
        for line in tb_lines[-6:]:
            emit(_box_line(line[: BOX_WIDTH - 2]))
        emit(_box_bottom())
        print("\n".join(output_lines))
        _print_verbose(verbose, messages, stdout_text)
        return 1


def _print_verbose(
    verbose: bool, messages: list[str], stdout_text: str,
) -> None:
    """Print verbose output (messages and captured stdout) if enabled."""
    if not verbose:
        return
    if messages:
        print("\n--- Block Messages ---")
        for msg in messages:
            print(f"  {msg}")
    if stdout_text.strip():
        print("\n--- Captured Stdout ---")
        print(stdout_text.rstrip())


def _coerce_value(value: str, field_type: str) -> Any:
    """Coerce a CLI string value to the appropriate Python type.

    CLI arguments are always strings.  This function converts them to the
    type declared in block.yaml so that the validator and block receive
    correctly-typed values.
    """
    if field_type == "integer":
        try:
            return int(value)
        except ValueError:
            return value  # Let the validator catch it
    if field_type == "float":
        try:
            return float(value)
        except ValueError:
            return value
    if field_type == "boolean":
        return value.lower() in ("true", "1", "yes")
    return value


# ── CLI entrypoint ────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Block Test Runner — test a single block in isolation.",
        usage="python -m backend.tests.block_runner <block_dir> [options]",
    )
    parser.add_argument(
        "block_dir",
        help="Path to the block directory (e.g., blocks/data/text_input)",
    )
    parser.add_argument(
        "--fixture",
        choices=["small", "medium", "realistic"],
        default=None,
        help="Named fixture: small (10 rows), medium (1000), realistic (10K)",
    )
    parser.add_argument(
        "--fixture-path",
        default=None,
        metavar="PATH",
        help="Path to a custom JSONL fixture file (overrides --fixture)",
    )
    parser.add_argument(
        "--config",
        nargs="*",
        default=[],
        metavar="KEY=VALUE",
        help="Config overrides as key=value pairs",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show block log messages and captured stdout",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        metavar="SECONDS",
        help="Maximum execution time in seconds",
    )

    args = parser.parse_args()

    # Parse config overrides
    config_overrides: dict[str, str] = {}
    for item in args.config:
        if "=" in item:
            key, _, value = item.partition("=")
            config_overrides[key] = value
        else:
            print(
                f"Warning: ignoring config arg without '=': {item}",
                file=sys.stderr,
            )

    exit_code = run_block_test(
        block_dir=args.block_dir,
        fixture_name=args.fixture,
        fixture_path_override=args.fixture_path,
        config_overrides=config_overrides,
        verbose=args.verbose,
        timeout=args.timeout,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
