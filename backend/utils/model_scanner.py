"""Local model directory scanner — detect downloaded models on disk.

No external dependencies: uses only ``os``, ``pathlib``, and ``json``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class LocalModelInfo(TypedDict):
    name: str
    path: str
    format: str
    size_bytes: int
    detected_quant: str | None


# ---------------------------------------------------------------------------
# Default scan paths
# ---------------------------------------------------------------------------

DEFAULT_SCAN_PATHS: list[str] = [
    os.path.expanduser("~/.specific-labs/models/"),
    os.path.expanduser("~/.ollama/models/"),
    os.path.expanduser("~/.cache/huggingface/hub/"),
]

# ---------------------------------------------------------------------------
# Quant parsing
# ---------------------------------------------------------------------------

# Common GGUF quantisation tokens
_QUANT_PATTERN = re.compile(
    r"(Q[0-9]+_K_[A-Z]+|Q[0-9]+_K|Q[0-9]+_[0-9]|Q[0-9]+|F16|F32|IQ[0-9]+_[A-Z]+|IQ[0-9]+)",
    re.IGNORECASE,
)


def _detect_quant_from_filename(filename: str) -> str | None:
    """Try to extract a quantisation type from a filename, e.g. Q4_K_M."""
    match = _QUANT_PATTERN.search(filename)
    return match.group(1).upper() if match else None


# ---------------------------------------------------------------------------
# File-level detection
# ---------------------------------------------------------------------------

def _file_size(path: Path) -> int:
    """Return the file size in bytes, or 0 on error."""
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _dir_total_size(directory: Path, extensions: set[str]) -> int:
    """Sum sizes of files with matching extensions in *directory*."""
    total = 0
    try:
        for entry in directory.iterdir():
            if entry.is_file() and entry.suffix in extensions:
                total += _file_size(entry)
    except OSError:
        pass
    return total


# ---------------------------------------------------------------------------
# Directory scanners
# ---------------------------------------------------------------------------

def _scan_gguf_files(root: Path) -> list[LocalModelInfo]:
    """Find all .gguf files recursively under *root*."""
    models: list[LocalModelInfo] = []
    try:
        for gguf_path in root.rglob("*.gguf"):
            if not gguf_path.is_file():
                continue
            name = gguf_path.stem
            quant = _detect_quant_from_filename(name)
            models.append(LocalModelInfo(
                name=name,
                path=str(gguf_path),
                format="gguf",
                size_bytes=_file_size(gguf_path),
                detected_quant=quant,
            ))
    except OSError as exc:
        logger.debug("GGUF scan error in %s: %s", root, exc)
    return models


def _resolve_hf_name(directory: Path) -> str:
    """Resolve a human-readable model name from a HuggingFace hub cache directory.

    HF hub cache layout:
        ~/.cache/huggingface/hub/
            models--org--name/
                snapshots/
                    <40-char-hash>/   ← safetensors live here
    We traverse upward until we escape the 'snapshots'/'blobs'/'refs' and
    hash directories, then convert the ``models--org--name`` folder name to
    ``org/name`` notation.
    """
    name = directory.name
    current = directory

    # Walk up past hash dirs and well-known HF intermediate dirs (up to 3 levels)
    for _ in range(3):
        if len(name) == 40 or name in ("snapshots", "blobs", "refs"):
            current = current.parent
            name = current.name
        else:
            break

    # Convert HuggingFace cache naming: "models--org--name" → "org/name"
    if name.startswith("models--"):
        name = name[len("models--"):].replace("--", "/", 1)

    return name


def _scan_safetensors(root: Path) -> list[LocalModelInfo]:
    """Find directories containing .safetensors files under *root*."""
    models: list[LocalModelInfo] = []
    seen_dirs: set[Path] = set()
    try:
        for st_path in root.rglob("*.safetensors"):
            parent = st_path.parent
            if parent in seen_dirs:
                continue
            seen_dirs.add(parent)
            size = _dir_total_size(parent, {".safetensors"})
            name = _resolve_hf_name(parent)
            models.append(LocalModelInfo(
                name=name,
                path=str(parent),
                format="safetensors",
                size_bytes=size,
                detected_quant=None,
            ))
    except OSError as exc:
        logger.debug("SafeTensors scan error in %s: %s", root, exc)
    return models


def _scan_pytorch(root: Path) -> list[LocalModelInfo]:
    """Find directories with config.json alongside .bin files (PyTorch format)."""
    models: list[LocalModelInfo] = []
    seen_dirs: set[Path] = set()
    try:
        for config_path in root.rglob("config.json"):
            parent = config_path.parent
            if parent in seen_dirs:
                continue
            # Must have at least one .bin file next to config.json
            has_bin = any(parent.glob("*.bin"))
            if not has_bin:
                continue
            seen_dirs.add(parent)
            size = _dir_total_size(parent, {".bin"})
            name = _resolve_hf_name(parent)
            models.append(LocalModelInfo(
                name=name,
                path=str(parent),
                format="pytorch",
                size_bytes=size,
                detected_quant=None,
            ))
    except OSError as exc:
        logger.debug("PyTorch scan error in %s: %s", root, exc)
    return models


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_ollama_models(ollama_url: str = "http://localhost:11434") -> list[LocalModelInfo]:
    """Detect installed Ollama models by querying the API or falling back to CLI.

    Returns Ollama models as LocalModelInfo entries with format ``"ollama"``.
    Works even when the Ollama server is not running by using ``ollama list``.
    """
    import subprocess

    models: list[LocalModelInfo] = []

    # 1) Try the running server first (fast path)
    try:
        import urllib.request
        import json as _json
        resp = urllib.request.urlopen(f"{ollama_url}/api/tags", timeout=2)
        data = _json.loads(resp.read())
        for m in data.get("models", []):
            name = m.get("name", "")
            if name:
                models.append(LocalModelInfo(
                    name=name,
                    path="ollama",
                    format="ollama",
                    size_bytes=m.get("size", 0),
                    detected_quant=None,
                ))
        return models
    except Exception:
        pass

    # 2) Server not running — scan Ollama manifest directories on disk.
    # Ollama stores manifests at ~/.ollama/models/manifests/<registry>/<namespace>/<model>/<tag>
    # Each manifest is a JSON file containing layer sizes.
    ollama_dir = Path(os.path.expanduser("~/.ollama/models/manifests"))
    if not ollama_dir.is_dir():
        return []

    try:
        import json as _json

        for registry_dir in ollama_dir.iterdir():
            if not registry_dir.is_dir():
                continue
            for namespace_dir in registry_dir.iterdir():
                if not namespace_dir.is_dir():
                    continue
                for model_dir in namespace_dir.iterdir():
                    if not model_dir.is_dir():
                        continue
                    for tag_file in model_dir.iterdir():
                        if not tag_file.is_file():
                            continue
                        tag = tag_file.name
                        # Build model name from path components
                        registry = registry_dir.name
                        namespace = namespace_dir.name
                        model_name = model_dir.name

                        if registry == "registry.ollama.ai" and namespace == "library":
                            # Standard Ollama models: "model:tag"
                            display_name = f"{model_name}:{tag}" if tag != "latest" else model_name
                        elif registry == "hf.co":
                            # HuggingFace models pulled via ollama: "hf.co/namespace/model:tag"
                            display_name = f"hf.co/{namespace}/{model_name}:{tag}" if tag != "latest" else f"hf.co/{namespace}/{model_name}"
                        else:
                            display_name = f"{registry}/{namespace}/{model_name}:{tag}"

                        # Parse manifest JSON to get total model size
                        size_bytes = 0
                        try:
                            manifest = _json.loads(tag_file.read_text())
                            for layer in manifest.get("layers", []):
                                if layer.get("mediaType", "").endswith(".model"):
                                    size_bytes += layer.get("size", 0)
                        except Exception:
                            pass

                        # Detect quantization from tag or model name
                        quant = _detect_quant_from_filename(tag) or _detect_quant_from_filename(model_name)

                        models.append(LocalModelInfo(
                            name=display_name,
                            path="ollama",
                            format="ollama",
                            size_bytes=size_bytes,
                            detected_quant=quant,
                        ))
    except OSError as exc:
        logger.debug("Ollama manifest scan error: %s", exc)

    return models


def scan_directories(paths: list[str] | None = None) -> list[LocalModelInfo]:
    """Scan a list of directories for downloaded models.

    Parameters
    ----------
    paths : list[str], optional
        Directories to scan.  Defaults to the well-known model cache locations:
        ``~/.specific-labs/models/``, ``~/.ollama/models/``,
        ``~/.cache/huggingface/hub/``.

    Returns
    -------
    list[LocalModelInfo]
    """
    if paths is None:
        paths = DEFAULT_SCAN_PATHS

    all_models: list[LocalModelInfo] = []
    seen_paths: set[str] = set()

    for raw_path in paths:
        expanded = os.path.expanduser(raw_path)
        root = Path(expanded)
        if not root.exists() or not root.is_dir():
            continue

        # Scan for each format; deduplicate by path
        for scanner in (_scan_gguf_files, _scan_safetensors, _scan_pytorch):
            for model in scanner(root):
                if model["path"] not in seen_paths:
                    seen_paths.add(model["path"])
                    all_models.append(model)

    # Also detect Ollama models (works even when server is stopped)
    seen_names: set[str] = {m["name"] for m in all_models}
    for model in detect_ollama_models():
        if model["name"] not in seen_names:
            seen_names.add(model["name"])
            all_models.append(model)

    # Sort by name
    all_models.sort(key=lambda m: m["name"].lower())
    return all_models
