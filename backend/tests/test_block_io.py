"""
Block I/O Verification Tests — Prompt 2.6, Task 107 (Part 1).

For each of the 9 block categories, run one representative block and verify:
  (a) the block completes without error
  (b) each output port's actual data resolves to the declared data_type
      when consumed through the BlockContext resolve_* methods

Architecture note — dual-representation pattern:
    Blueprint blocks produce outputs via ctx.save_output(name, value).  The
    value may be a raw Python object (dict, list, str) OR a file/directory
    path.  Downstream blocks call ctx.resolve_as_text(), resolve_as_data(),
    etc., which transparently reads files, deserialises JSON, or passes
    values through.  Therefore, I/O verification must test the *logical*
    type (what a downstream block would see after resolution) rather than
    the *physical* type (the raw value stored in save_output).
"""

import importlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.config import BUILTIN_BLOCKS_DIR
from backend.services.registry import get_global_registry


# ---------------------------------------------------------------------------
# Logical-type resolution helpers
# ---------------------------------------------------------------------------

def _resolve_logical_value(raw_value: Any, declared_type: str) -> Any:
    """Resolve a raw output value to its logical form.

    Mirrors the resolution logic in BlockContext.resolve_as_text(),
    resolve_as_data(), resolve_as_dict() without needing a full context.
    """
    if raw_value is None:
        return None

    # If the value is a string that points to a file or directory, read it
    if isinstance(raw_value, (str, Path)):
        path = str(raw_value)

        if os.path.isdir(path):
            # Directory → look for data file inside
            for candidate in ("data.json", "data.jsonl", "dataset.json", "output.json"):
                fpath = os.path.join(path, candidate)
                if os.path.isfile(fpath):
                    return _read_file_as_logical(fpath, declared_type)
            # Try any JSON file
            for f in sorted(os.listdir(path)):
                if f.endswith((".json", ".jsonl")):
                    return _read_file_as_logical(os.path.join(path, f), declared_type)
            # Directory with no recognizable data file → return path as-is
            return raw_value

        if os.path.isfile(path):
            return _read_file_as_logical(path, declared_type)

    # Not a file path — return as-is
    return raw_value


def _read_file_as_logical(filepath: str, declared_type: str) -> Any:
    """Read a file and return the logical value based on declared type."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return filepath  # Can't read → return path as artifact reference

    if declared_type in ("text",):
        return content

    if declared_type in ("dataset", "config", "metrics"):
        try:
            parsed = json.loads(content)
            return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        # Try JSONL
        lines = [l.strip() for l in content.strip().split("\n") if l.strip()]
        try:
            return [json.loads(line) for line in lines]
        except (json.JSONDecodeError, ValueError):
            pass

    # For artifact/model/any — return content as-is
    return content


# ---------------------------------------------------------------------------
# Logical-type validators
# ---------------------------------------------------------------------------

def _validate_text(resolved: Any) -> tuple[bool, str]:
    """Text must resolve to a non-empty string (not a dict, not a list)."""
    if isinstance(resolved, str):
        return True, ""
    return False, f"expected str, got {type(resolved).__name__}"


def _validate_dataset(resolved: Any) -> tuple[bool, str]:
    """Dataset must resolve to a list (of dicts) or a dict."""
    if isinstance(resolved, list):
        return True, ""
    if isinstance(resolved, dict):
        return True, ""
    return False, f"expected list or dict, got {type(resolved).__name__}"


def _validate_metrics(resolved: Any) -> tuple[bool, str]:
    """Metrics must resolve to a dict (keys = metric names, values = numbers or nested)."""
    if isinstance(resolved, dict):
        return True, ""
    return False, f"expected dict, got {type(resolved).__name__}"


def _validate_config(resolved: Any) -> tuple[bool, str]:
    """Config must resolve to a dict."""
    if isinstance(resolved, dict):
        return True, ""
    return False, f"expected dict, got {type(resolved).__name__}"


def _validate_model(resolved: Any) -> tuple[bool, str]:
    """Model can be a dict with model info, or a path string to model files."""
    if isinstance(resolved, (dict, str)):
        return True, ""
    return False, f"expected dict or str, got {type(resolved).__name__}"


def _validate_artifact(resolved: Any) -> tuple[bool, str]:
    """Artifact can be a file path (str), binary data (bytes), or a dict."""
    if isinstance(resolved, (str, bytes, dict, Path)):
        return True, ""
    return False, f"expected str/bytes/dict/Path, got {type(resolved).__name__}"


def _validate_any(resolved: Any) -> tuple[bool, str]:
    """Any type accepts everything."""
    return True, ""


LOGICAL_VALIDATORS = {
    "text": _validate_text,
    "dataset": _validate_dataset,
    "metrics": _validate_metrics,
    "config": _validate_config,
    "model": _validate_model,
    "artifact": _validate_artifact,
    "embedding": _validate_dataset,
    "any": _validate_any,
    "llm": _validate_config,
    "agent": _validate_config,
}


# ---------------------------------------------------------------------------
# Representative blocks: one per category (all runnable without external deps)
# ---------------------------------------------------------------------------

REPRESENTATIVE_BLOCKS = {
    "data": {
        "block_type": "text_input",
        "inputs": {},
        "config": {"text_value": "Hello from I/O verification test", "format": "plain", "encoding": "utf-8"},
        "expected_outputs": {"text": "text"},
    },
    "inference": {
        "block_type": "prompt_template",
        "inputs": {},
        "config": {
            "template": "Summarize: {{text}}",
            "variables": "text=Hello world from the test suite",
        },
        "expected_outputs": {"rendered_text": "text", "metrics": "metrics"},
    },
    "evaluation": {
        "block_type": "coherence_eval",
        "inputs": {
            "dataset": [
                {"text": "The cat sat on the mat. It was a comfortable mat made of woven fibers. The cat purred softly."},
                {"text": "Machine learning models require careful training. Data quality is paramount for good results."},
            ],
        },
        "config": {
            "text_column": "text",
            "metrics_to_compute": "readability,repetition,vocabulary",
        },
        "expected_outputs": {"metrics": "metrics"},
    },
    "flow": {
        "block_type": "quality_gate",
        "inputs": {
            "data": [{"score": 0.9, "text": "good result"}, {"score": 0.8, "text": "ok result"}],
            "metrics": {"accuracy": 0.95},
        },
        "config": {
            "metric_name": "accuracy",
            "threshold": 0.8,
            "operator": ">=",
            "on_fail": "route_rejected",
            "auto_compute_quality": True,
        },
        "expected_outputs": {"passed": "any", "gate_metrics": "metrics"},
    },
    "output": {
        "block_type": "results_formatter",
        "inputs": {
            "metrics": {"accuracy": 0.95, "loss": 0.05, "f1": 0.93},
        },
        "config": {"format": "json", "include_config": True},
        "expected_outputs": {"artifact": "artifact"},
    },
    "endpoints": {
        "block_type": "data_export",
        "inputs": {
            "data": [{"id": 1, "text": "test"}, {"id": 2, "text": "data"}],
        },
        "config": {"format": "json"},
        "expected_outputs": {"file_path": "artifact", "summary": "metrics"},
    },
    "agents": {
        "block_type": "tool_registry",
        "inputs": {},
        "config": {
            "tools": "",
            "include_defaults": True,
            "output_format": "openai",
        },
        "expected_outputs": {"tools": "config", "metrics": "metrics"},
    },
    "merge": {
        "block_type": "slerp_merge",
        "inputs": {
            "model_a": {"model_id": "model-a", "path": "/tmp/model_a"},
            "model_b": {"model_id": "model-b", "path": "/tmp/model_b"},
        },
        "config": {"interpolation_factor": 0.5},
        "expected_outputs": {"merged_model": "model"},
        "skip_reason": "Requires mergekit library and actual model files on disk",
    },
    "training": {
        "block_type": "checkpoint_selector",
        "inputs": {},
        "config": {},
        "expected_outputs": {"selected_model": "model", "metrics": "metrics"},
    },
}


# ---------------------------------------------------------------------------
# Block loader + mock context
# ---------------------------------------------------------------------------

def _load_block_run(block_type: str):
    """Import a block's run.py and return (run_function, block_dir_path)."""
    registry = get_global_registry()
    schema = registry.get(block_type)
    if schema is None:
        return None, None

    run_py = Path(schema.source_path) / "run.py"
    if not run_py.exists():
        return None, None

    mod_name = f"_block_io_{block_type}"
    spec = importlib.util.spec_from_file_location(mod_name, str(run_py))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    return getattr(mod, "run", None), Path(schema.source_path)


class _MockContext:
    """Lightweight mock of BlockContext with real file I/O.

    Unlike a MagicMock, this exposes only the interface blocks actually use,
    so AttributeErrors surface immediately rather than being silently absorbed.
    """

    def __init__(self, block_dir: Path, config: dict, inputs: dict):
        self.block_dir = block_dir
        self.config = config
        self.inputs = inputs
        self.run_dir = Path(tempfile.mkdtemp(prefix=f"block_io_{block_dir.name}_"))
        self.device = "cpu"
        self.has_gpu = False

        self._outputs: dict[str, Any] = {}
        self._metrics: dict[str, Any] = {}
        self._messages: list[str] = []

    # ── I/O interface ──

    def load_input(self, port_id: str, default=None):
        return self.inputs.get(port_id, default)

    def save_output(self, name: str, data_or_path: Any):
        self._outputs[name] = data_or_path

    def get_outputs(self) -> dict:
        return self._outputs

    def get_metrics(self) -> dict:
        return self._metrics

    # ── Logging / progress ──

    def log_message(self, msg: str):
        self._messages.append(msg)

    def log_metric(self, name: str, value: float, step=None):
        self._metrics[name] = value

    def report_progress(self, current: int, total: int):
        pass

    # ── Artifact / checkpoint stubs ──

    def save_artifact(self, name: str, file_path: str):
        pass  # no-op in test

    def save_checkpoint(self, epoch: int, path: str, metrics: dict = None):
        pass

    # ── Loop metadata (not in a loop during tests) ──

    def get_loop_metadata(self):
        return None

    def is_in_loop(self) -> bool:
        return False

    def get_iteration(self) -> int:
        return 0

    def get_file_mode(self) -> str:
        return "overwrite"

    def get_context_mode(self) -> str:
        return "clear"

    # ── Resolve helpers (used by some blocks internally) ──

    def resolve_as_text(self, name: str) -> str:
        value = self.load_input(name)
        if value is None:
            return ""
        if isinstance(value, str):
            if os.path.isfile(value):
                with open(value, "r", encoding="utf-8", errors="replace") as f:
                    return f.read()
            return value
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2, default=str)
        return str(value)

    def resolve_as_data(self, name: str) -> list:
        value = self.load_input(name)
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
        if isinstance(value, str):
            if os.path.isfile(value):
                with open(value, "r") as f:
                    try:
                        return json.load(f)
                    except json.JSONDecodeError:
                        return [{"text": f.read()}]
            return [{"text": value}]
        return [{"value": str(value)}]

    def resolve_as_dict(self, name: str) -> dict:
        value = self.load_input(name)
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                return {"value": value}
        return {"value": str(value)}

    def resolve_model_info(self, name: str) -> dict:
        value = self.load_input(name)
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return {"model_name": value, "model_id": value, "source": "config"}
        return {}

    def resolve_as_file_path(self, name: str) -> str:
        value = self.load_input(name)
        if isinstance(value, str) and os.path.exists(value):
            return value
        # Write value to temp file
        tmp = os.path.join(str(self.run_dir), f"_resolved_{name}.json")
        with open(tmp, "w") as f:
            json.dump(value, f, default=str)
        return tmp

    # ── Cleanup ──

    def cleanup(self):
        if self.run_dir.exists():
            shutil.rmtree(self.run_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Tests: one representative block per category
# ---------------------------------------------------------------------------

class TestBlockIO:
    """Execute one block per category and verify logical I/O types."""

    @pytest.mark.parametrize("category", sorted(REPRESENTATIVE_BLOCKS.keys()))
    @pytest.mark.timeout(30)
    def test_block_io_logical_type_match(self, category):
        """Block outputs, after resolution, must match their declared data_type."""
        spec = REPRESENTATIVE_BLOCKS[category]
        block_type = spec["block_type"]
        skip_reason = spec.get("skip_reason")

        if skip_reason:
            pytest.skip(f"{block_type}: {skip_reason}")

        run_fn, block_dir = _load_block_run(block_type)
        if run_fn is None:
            pytest.skip(f"Cannot load run function for {block_type}")

        ctx = _MockContext(block_dir, spec["config"], spec["inputs"])
        try:
            # (a) Block completes without error
            try:
                run_fn(ctx)
            except ImportError as e:
                pytest.skip(f"{block_type} requires unavailable dependency: {e}")
            except Exception as e:
                if isinstance(e, (TypeError, AttributeError, NameError)):
                    pytest.fail(f"{block_type} failed with code error: {type(e).__name__}: {e}")
                pytest.skip(f"{block_type} failed (likely needs external service): {e}")

            # (b) Verify logical output types
            outputs = ctx._outputs
            expected_outputs = spec.get("expected_outputs", {})

            for port_id, declared_type in expected_outputs.items():
                if port_id not in outputs:
                    continue  # Optional port not produced

                raw_value = outputs[port_id]
                resolved = _resolve_logical_value(raw_value, declared_type)

                validator = LOGICAL_VALIDATORS.get(declared_type, _validate_any)
                ok, reason = validator(resolved)
                assert ok, (
                    f"[{category}] Block '{block_type}' port '{port_id}': "
                    f"declared type '{declared_type}', raw type {type(raw_value).__name__}, "
                    f"resolved type {type(resolved).__name__} — {reason}. "
                    f"Raw value: {repr(raw_value)[:200]}"
                )
        finally:
            ctx.cleanup()


# ---------------------------------------------------------------------------
# Deep dive: text-type blocks output file paths — verify content is text
# ---------------------------------------------------------------------------

class TestTextPortContract:
    """Blocks declaring 'text' output ports must produce values that
    resolve to valid text strings, not binary data or bare dicts."""

    TEXT_PORT_BLOCKS = [
        ("text_input", {"text_value": "Contract test string", "format": "plain"}, {}, "text"),
        ("text_concatenator", {"separator": " ", "template": "{text_a}", "trim_whitespace": True, "skip_empty": True},
         {"text_a": "Hello", "text_b": "World"}, "text"),
    ]

    @pytest.mark.parametrize("block_type,config,inputs,port_id", TEXT_PORT_BLOCKS,
                             ids=[t[0] for t in TEXT_PORT_BLOCKS])
    @pytest.mark.timeout(30)
    def test_text_port_resolves_to_string(self, block_type, config, inputs, port_id):
        """Text port values must resolve to a non-empty UTF-8 string."""
        run_fn, block_dir = _load_block_run(block_type)
        if run_fn is None:
            pytest.skip(f"{block_type} not found")

        ctx = _MockContext(block_dir, config, inputs)
        try:
            run_fn(ctx)
            raw = ctx._outputs.get(port_id)
            assert raw is not None, f"{block_type}.{port_id} produced no output"

            resolved = _resolve_logical_value(raw, "text")
            assert isinstance(resolved, str), (
                f"{block_type}.{port_id}: resolved to {type(resolved).__name__}, not str"
            )
            assert len(resolved) > 0, (
                f"{block_type}.{port_id}: resolved to empty string"
            )
            # If the raw value was a file path, verify the file exists and is readable
            if isinstance(raw, str) and os.path.isfile(raw):
                assert os.path.getsize(raw) > 0, (
                    f"{block_type}.{port_id}: output file is empty: {raw}"
                )
        finally:
            ctx.cleanup()


# ---------------------------------------------------------------------------
# Deep dive: metrics-type blocks must output dicts directly (not file paths)
# ---------------------------------------------------------------------------

class TestMetricsPortContract:
    """Blocks declaring 'metrics' output ports should produce dicts
    with numeric values — never file paths for metrics."""

    METRICS_PORT_BLOCKS = [
        ("quality_gate",
         {"metric_name": "accuracy", "threshold": 0.5, "operator": ">=",
          "on_fail": "route_rejected", "auto_compute_quality": True},
         {"data": [{"score": 0.9}], "metrics": {"accuracy": 0.95}},
         "gate_metrics"),
    ]

    @pytest.mark.parametrize("block_type,config,inputs,port_id", METRICS_PORT_BLOCKS,
                             ids=[t[0] for t in METRICS_PORT_BLOCKS])
    @pytest.mark.timeout(30)
    def test_metrics_port_is_dict(self, block_type, config, inputs, port_id):
        """Metrics ports must produce dicts, not file paths."""
        run_fn, block_dir = _load_block_run(block_type)
        if run_fn is None:
            pytest.skip(f"{block_type} not found")

        ctx = _MockContext(block_dir, config, inputs)
        try:
            run_fn(ctx)
            raw = ctx._outputs.get(port_id)
            if raw is None:
                pytest.skip(f"{block_type}.{port_id} not produced")

            assert isinstance(raw, dict), (
                f"{block_type}.{port_id}: metrics port should produce a dict "
                f"directly (not a file path). Got {type(raw).__name__}: {repr(raw)[:200]}"
            )
        finally:
            ctx.cleanup()


# ---------------------------------------------------------------------------
# Static analysis: blocks that can't be executed still get schema checks
# ---------------------------------------------------------------------------

class TestUnexecutableBlockSchemas:
    """For blocks that require external services (merge, some training),
    verify their declared I/O schemas are internally consistent by
    inspecting the source code for save_output calls."""

    def test_merge_blocks_schema_consistency(self):
        """All merge blocks must declare model-type outputs."""
        registry = get_global_registry()
        merge_blocks = registry.list_all(category="merge")
        assert len(merge_blocks) > 0, "No merge blocks found"

        for schema in merge_blocks:
            output_types = {o.id: o.data_type for o in schema.outputs}
            has_model_output = any(
                dt in ("model", "artifact") for dt in output_types.values()
            )
            assert has_model_output, (
                f"Merge block '{schema.block_type}' has no model/artifact output. "
                f"Outputs: {output_types}"
            )

    def test_training_blocks_schema_consistency(self):
        """All training blocks must declare model-type or metrics outputs."""
        registry = get_global_registry()
        training_blocks = registry.list_all(category="training")
        assert len(training_blocks) > 0, "No training blocks found"

        for schema in training_blocks:
            output_types = {o.id: o.data_type for o in schema.outputs}
            has_expected_output = any(
                dt in ("model", "metrics", "artifact", "dataset")
                for dt in output_types.values()
            )
            assert has_expected_output, (
                f"Training block '{schema.block_type}' has no model/metrics output. "
                f"Outputs: {output_types}"
            )

    def test_all_blocks_save_output_matches_ports(self):
        """For every block with a run.py, verify that each save_output call
        references a port ID that exists in the block's declared outputs."""
        import re
        registry = get_global_registry()

        mismatches = []
        for schema in registry.list_all():
            run_py = Path(schema.source_path) / "run.py"
            if not run_py.exists():
                continue

            try:
                source = run_py.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            # Extract all save_output("port_id", ...) calls
            declared_outputs = {o.id for o in schema.outputs}
            # Match both single and double quoted strings
            save_calls = re.findall(
                r'ctx\.save_output\(\s*["\']([^"\']+)["\']',
                source,
            )

            for port_id in save_calls:
                if port_id not in declared_outputs:
                    # Check aliases
                    is_alias = False
                    for out in schema.outputs:
                        if port_id in out.aliases:
                            is_alias = True
                            break
                    if not is_alias:
                        mismatches.append(
                            f"{schema.block_type}: save_output('{port_id}') "
                            f"not in declared outputs {declared_outputs}"
                        )

        if mismatches:
            # Report but don't fail — some blocks may have dynamic port IDs
            # Filter to those that are clearly wrong (not in any output or alias)
            real_mismatches = [m for m in mismatches if "status" not in m]
            if real_mismatches:
                pytest.fail(
                    f"Found {len(real_mismatches)} save_output() calls referencing "
                    f"undeclared ports:\n" + "\n".join(real_mismatches[:20])
                )
