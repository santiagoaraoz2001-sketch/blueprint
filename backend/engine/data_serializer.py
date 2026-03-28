"""Cross-process data serialization for subprocess block execution.

Handles serialization and deserialization of arbitrary Python values across
the process boundary between the main executor and subprocess block workers.

Supported formats (auto-detected by type):
  json     — dict, list, str, int, float, bool, None
  numpy    — numpy.ndarray  → .npy file
  torch    — torch.Tensor   → .pt file (CPU)
  pandas   — pandas.DataFrame / Series → .parquet file
  bytes    — raw bytes → .bin file
  path     — file-path string passthrough (the file itself is NOT copied)
  pickle   — fallback for any type not covered above

Design constraints:
  - No heavy imports at module level (numpy, torch, pandas are lazy-imported)
  - Must be importable from both the main process and the subprocess worker
  - Deterministic: same value always serializes to the same format choice
  - Size-aware: logs warnings for large serializations (>100 MB)
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

_logger = logging.getLogger("blueprint.data_serializer")

# Size threshold for warning about large serializations (100 MB)
_LARGE_THRESHOLD = 100 * 1024 * 1024


def _safe_filename(name: str) -> str:
    """Sanitize a port/input name for use as a filename."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name) or "value"


# ---------------------------------------------------------------------------
# Type detection (lazy imports to avoid loading ML libraries eagerly)
# ---------------------------------------------------------------------------

def _is_numpy_array(value: Any) -> bool:
    try:
        import numpy as np
        return isinstance(value, np.ndarray)
    except ImportError:
        return False


def _is_torch_tensor(value: Any) -> bool:
    try:
        import torch
        return isinstance(value, torch.Tensor)
    except ImportError:
        return False


def _is_pandas_dataframe(value: Any) -> bool:
    try:
        import pandas as pd
        return isinstance(value, (pd.DataFrame, pd.Series))
    except ImportError:
        return False


def _is_file_path(value: Any) -> bool:
    """Check if a string is an existing file or directory path."""
    return isinstance(value, str) and (os.path.isfile(value) or os.path.isdir(value))


def _is_json_serializable(value: Any) -> bool:
    """Quick check whether a value round-trips through JSON."""
    try:
        json.dumps(value)
        return True
    except (TypeError, ValueError, OverflowError):
        return False


# ---------------------------------------------------------------------------
# Single-value serialization
# ---------------------------------------------------------------------------

def _detect_format(value: Any) -> str:
    """Determine the best serialization format for a value."""
    if value is None:
        return "json"
    if isinstance(value, bytes):
        return "bytes"
    if isinstance(value, (bool, int, float)):
        return "json"
    if isinstance(value, str):
        if _is_file_path(value):
            return "path"
        return "json"
    if isinstance(value, Path):
        return "path"
    if _is_numpy_array(value):
        return "numpy"
    if _is_torch_tensor(value):
        return "torch"
    if _is_pandas_dataframe(value):
        return "pandas"
    if isinstance(value, (dict, list, tuple)):
        if _is_json_serializable(value):
            return "json"
        # Dict/list that contains non-serializable objects — pickle
        return "pickle"
    # Unknown type — pickle fallback
    return "pickle"


def serialize_value(name: str, value: Any, directory: str) -> dict:
    """Serialize a single value to a file inside *directory*.

    Returns a manifest entry dict:
      { "filename": ..., "format": ..., "original_type": ..., ... }
    """
    safe = _safe_filename(name)
    fmt = _detect_format(value)
    meta: dict[str, Any] = {
        "format": fmt,
        "original_type": type(value).__module__ + "." + type(value).__qualname__,
    }

    if fmt == "json":
        filename = f"{safe}.json"
        filepath = os.path.join(directory, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, default=str)

    elif fmt == "path":
        filename = f"{safe}.path"
        filepath = os.path.join(directory, filename)
        path_str = str(value)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(path_str)
        meta["referenced_path"] = path_str

    elif fmt == "bytes":
        filename = f"{safe}.bin"
        filepath = os.path.join(directory, filename)
        with open(filepath, "wb") as f:
            f.write(value)
        meta["size_bytes"] = len(value)

    elif fmt == "numpy":
        import numpy as np
        filename = f"{safe}.npy"
        filepath = os.path.join(directory, filename)
        np.save(filepath, value)
        meta["dtype"] = str(value.dtype)
        meta["shape"] = list(value.shape)
        meta["size_bytes"] = int(value.nbytes)
        if value.nbytes > _LARGE_THRESHOLD:
            _logger.warning(
                "Large numpy array serialized for '%s': %.1f MB (%s, %s)",
                name, value.nbytes / (1024 * 1024), value.dtype, value.shape,
            )

    elif fmt == "torch":
        import torch
        filename = f"{safe}.pt"
        filepath = os.path.join(directory, filename)
        # Always save on CPU to avoid GPU memory issues in the worker
        torch.save(value.detach().cpu(), filepath)
        meta["dtype"] = str(value.dtype)
        meta["shape"] = list(value.shape)
        meta["size_bytes"] = int(value.nelement() * value.element_size())
        if meta["size_bytes"] > _LARGE_THRESHOLD:
            _logger.warning(
                "Large torch tensor serialized for '%s': %.1f MB (%s, %s)",
                name, meta["size_bytes"] / (1024 * 1024), value.dtype, list(value.shape),
            )

    elif fmt == "pandas":
        import pandas as pd
        filename = f"{safe}.parquet"
        filepath = os.path.join(directory, filename)
        if isinstance(value, pd.Series):
            value = value.to_frame(name=name)
        value.to_parquet(filepath, engine="pyarrow" if _has_pyarrow() else "fastparquet")
        meta["shape"] = list(value.shape)
        meta["columns"] = list(value.columns) if hasattr(value, "columns") else []

    elif fmt == "pickle":
        import pickle
        filename = f"{safe}.pkl"
        filepath = os.path.join(directory, filename)
        try:
            with open(filepath, "wb") as f:
                pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)
        except (pickle.PicklingError, AttributeError, TypeError) as exc:
            # Object is not picklable — fall back to JSON string representation
            _logger.warning(
                "Pickle failed for '%s' (type=%s): %s. "
                "Falling back to string representation.",
                name, type(value).__name__, exc,
            )
            filename = f"{safe}_fallback.json"
            filepath = os.path.join(directory, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(str(value), f)
            meta["format"] = "json"
            meta["fallback"] = True
            meta["fallback_reason"] = str(exc)
            meta["filename"] = filename
            return meta

        file_size = os.path.getsize(filepath)
        meta["size_bytes"] = file_size
        _logger.info(
            "Pickle fallback used for '%s' (type=%s, %.1f KB). "
            "Consider adding native serialization support for this type.",
            name, type(value).__name__, file_size / 1024,
        )
        if file_size > _LARGE_THRESHOLD:
            _logger.warning(
                "Large pickle serialized for '%s': %.1f MB",
                name, file_size / (1024 * 1024),
            )
    else:
        raise ValueError(f"Unknown serialization format: {fmt}")

    meta["filename"] = filename
    return meta


def deserialize_value(meta: dict, directory: str) -> Any:
    """Deserialize a value from a file described by a manifest entry."""
    fmt = meta["format"]
    filename = meta["filename"]
    filepath = os.path.join(directory, filename)

    if not os.path.exists(filepath):
        _logger.warning("Serialized file missing: %s", filepath)
        return None

    if fmt == "json":
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    elif fmt == "path":
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read().strip()

    elif fmt == "bytes":
        with open(filepath, "rb") as f:
            return f.read()

    elif fmt == "numpy":
        import numpy as np
        return np.load(filepath, allow_pickle=False)

    elif fmt == "torch":
        import torch
        # weights_only=True for safety (prevents arbitrary code execution)
        return torch.load(filepath, map_location="cpu", weights_only=True)

    elif fmt == "pandas":
        import pandas as pd
        return pd.read_parquet(filepath)

    elif fmt == "pickle":
        import pickle
        with open(filepath, "rb") as f:
            return pickle.load(f)  # noqa: S301 — trusted source (our own worker)

    else:
        _logger.warning("Unknown format '%s' for file %s, attempting JSON", fmt, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)


# ---------------------------------------------------------------------------
# Bulk serialization (full input/output dicts)
# ---------------------------------------------------------------------------

def serialize_inputs(inputs: dict[str, Any], input_dir: str) -> None:
    """Serialize all block inputs to a directory with a manifest file."""
    os.makedirs(input_dir, exist_ok=True)
    manifest: dict[str, dict] = {}

    for name, value in inputs.items():
        try:
            manifest[name] = serialize_value(name, value, input_dir)
        except Exception as exc:
            _logger.error("Failed to serialize input '%s': %s", name, exc)
            # Last resort: stringify and save as JSON
            safe = _safe_filename(name)
            filename = f"{safe}_fallback.json"
            filepath = os.path.join(input_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(str(value), f)
            manifest[name] = {
                "filename": filename,
                "format": "json",
                "original_type": type(value).__module__ + "." + type(value).__qualname__,
                "fallback": True,
                "fallback_reason": str(exc),
            }

    manifest_path = os.path.join(input_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


def deserialize_inputs(input_dir: str) -> dict[str, Any]:
    """Deserialize all block inputs from a directory."""
    manifest_path = os.path.join(input_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return {}

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    inputs: dict[str, Any] = {}
    for name, meta in manifest.items():
        try:
            inputs[name] = deserialize_value(meta, input_dir)
        except Exception as exc:
            _logger.error("Failed to deserialize input '%s': %s", name, exc)
            inputs[name] = None

    return inputs


def serialize_outputs(outputs: dict[str, Any], output_dir: str) -> None:
    """Serialize all block outputs to a directory with a manifest file."""
    os.makedirs(output_dir, exist_ok=True)
    manifest: dict[str, dict] = {}

    for name, value in outputs.items():
        try:
            manifest[name] = serialize_value(name, value, output_dir)
        except Exception as exc:
            _logger.error("Failed to serialize output '%s': %s", name, exc)
            safe = _safe_filename(name)
            filename = f"{safe}_fallback.json"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(str(value), f)
            manifest[name] = {
                "filename": filename,
                "format": "json",
                "original_type": type(value).__module__ + "." + type(value).__qualname__,
                "fallback": True,
                "fallback_reason": str(exc),
            }

    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


def deserialize_outputs(output_dir: str) -> dict[str, Any]:
    """Deserialize all block outputs from a directory."""
    manifest_path = os.path.join(output_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return {}

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    outputs: dict[str, Any] = {}
    for name, meta in manifest.items():
        try:
            outputs[name] = deserialize_value(meta, output_dir)
        except Exception as exc:
            _logger.error("Failed to deserialize output '%s': %s", name, exc)
            outputs[name] = None

    return outputs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_pyarrow() -> bool:
    """Check if pyarrow is available for Parquet I/O."""
    try:
        import pyarrow
        return True
    except ImportError:
        return False
