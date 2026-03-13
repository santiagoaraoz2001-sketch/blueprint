"""
Data Fingerprint — content-addressable hashing for datasets.

Generates a stable SHA256 hash from dataset content so runs can track
exactly which data they used. Handles files, directories, HF dataset IDs,
and in-memory data.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional


def hash_file(path: str, chunk_size: int = 8192) -> str:
    """SHA256 hash of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def hash_directory(path: str) -> str:
    """SHA256 hash of all files in a directory (sorted, deterministic).

    Uses forward slashes for relative paths regardless of platform
    to ensure cross-platform hash stability. Skips files that cannot
    be read (permission errors, broken symlinks).
    """
    h = hashlib.sha256()
    root = Path(path).resolve()
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        # Guard against symlink loops: skip if resolved path is outside root
        try:
            resolved = file_path.resolve()
            resolved.relative_to(root)
        except (ValueError, OSError):
            continue
        # Normalize to forward slashes for cross-platform determinism
        rel = file_path.relative_to(root).as_posix()
        h.update(rel.encode("utf-8"))
        try:
            h.update(hash_file(str(file_path)).encode("utf-8"))
        except (OSError, PermissionError):
            # Skip unreadable files rather than crashing the whole hash
            h.update(b"<unreadable>")
    return h.hexdigest()


def hash_string(content: str) -> str:
    """SHA256 hash of a string."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def hash_json(data: Any) -> str:
    """SHA256 hash of JSON-serializable data (deterministic key ordering)."""
    canonical = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fingerprint_dataset(source: Any, source_type: str = "auto") -> dict:
    """
    Generate a fingerprint for a dataset input.

    Returns:
        {
            "hash": "abc123...",
            "source_type": "file" | "directory" | "string" | "hf_dataset" | "json",
            "source_id": "path/to/file.csv" or "username/dataset" or "<inline>",
            "size_bytes": 12345,  # if applicable
        }
    """
    if source is None:
        return {"hash": "empty", "source_type": "none", "source_id": "none"}

    if isinstance(source, str):
        # Guard: empty string and whitespace-only are always inline text,
        # never filesystem paths (Path("").exists() → True on cwd).
        if not source.strip():
            return {
                "hash": hash_string(source),
                "source_type": "string",
                "source_id": "<inline>",
                "size_bytes": len(source.encode("utf-8")),
            }

        path = Path(source)
        try:
            path_exists = path.exists()
        except OSError:
            # Broken symlinks, permission errors on stat, etc.
            path_exists = False

        if path_exists:
            if path.is_file():
                return {
                    "hash": hash_file(source),
                    "source_type": "file",
                    "source_id": str(path.name),
                    "size_bytes": path.stat().st_size,
                }
            elif path.is_dir():
                total_size = sum(
                    f.stat().st_size
                    for f in path.rglob("*")
                    if f.is_file()
                )
                return {
                    "hash": hash_directory(source),
                    "source_type": "directory",
                    "source_id": str(path.name),
                    "size_bytes": total_size,
                }
        # Not a path — treat as inline text or HF dataset ID
        if "/" in source and not source.startswith("/"):
            # Looks like a HF dataset ID (e.g., "username/dataset")
            return {
                "hash": hash_string(source),
                "source_type": "hf_dataset",
                "source_id": source,
            }
        return {
            "hash": hash_string(source),
            "source_type": "string",
            "source_id": "<inline>",
            "size_bytes": len(source.encode("utf-8")),
        }

    if isinstance(source, (dict, list)):
        canonical = json.dumps(source, sort_keys=True, default=str)
        return {
            "hash": hash_json(source),
            "source_type": "json",
            "source_id": "<inline>",
            "size_bytes": len(canonical.encode("utf-8")),
        }

    # Fallback
    return {
        "hash": hash_string(str(source)),
        "source_type": "unknown",
        "source_id": "<unknown>",
    }
