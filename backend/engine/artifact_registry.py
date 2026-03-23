"""
Artifact Registry — automatic registration of block outputs as tracked artifacts.

After each block completes, the executor calls `register_block_artifacts()` to scan
the block's outputs for file paths on disk. Each file found is recorded in the
`blueprint_artifacts` table with full lineage (pipeline_id, run_id, node_id, block_type).

SHA-256 hashing is performed inline for files under MAX_HASH_SIZE (256 MB).
Larger files get hash=None (can be backfilled later).
"""

import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..database import SessionLocal
from ..models.artifact import Artifact

# Files larger than this skip inline hashing (256 MB)
MAX_HASH_SIZE = 256 * 1024 * 1024

# Internal engine files that should never be registered as artifacts
_INTERNAL_FILES = {"metrics.jsonl", "run-export.json", "error.log", "manifest.json"}

# Map file extensions to artifact_type
_EXT_TO_TYPE = {
    # Datasets
    ".jsonl": "dataset",
    ".csv": "dataset",
    ".tsv": "dataset",
    ".parquet": "dataset",
    ".arrow": "dataset",
    # Models
    ".gguf": "model",
    ".bin": "model",
    ".safetensors": "model",
    ".onnx": "model",
    ".pt": "model",
    ".pth": "model",
    ".h5": "model",
    ".mlmodel": "model",
    # Adapters (LoRA, etc.)
    ".npz": "adapter",
    # Logs
    ".log": "log",
    ".txt": "log",
    # Figures
    ".png": "figure",
    ".jpg": "figure",
    ".jpeg": "figure",
    ".svg": "figure",
    ".pdf": "figure",
    # Metrics
    ".json": "metrics",
}


def _sha256_file(path: str) -> str | None:
    """Compute SHA-256 hex digest of a file. Returns None if file is too large or unreadable."""
    try:
        size = os.path.getsize(path)
        if size > MAX_HASH_SIZE:
            return None
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(131072), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _infer_artifact_type(file_path: str) -> str:
    """Infer artifact_type from file extension."""
    ext = Path(file_path).suffix.lower()
    return _EXT_TO_TYPE.get(ext, "log")


def _extract_file_paths(outputs: dict[str, Any]) -> list[str]:
    """Extract file paths from block outputs, recursively checking dicts and lists."""
    paths: list[str] = []

    def _visit(value: Any):
        if isinstance(value, str):
            # Check if it looks like a file path and exists on disk
            if value and os.path.isfile(value):
                paths.append(value)
            elif value and os.path.isdir(value):
                # Scan directory for output files (non-recursive, top-level only)
                try:
                    for entry in os.scandir(value):
                        if entry.is_file() and entry.name not in _INTERNAL_FILES:
                            paths.append(entry.path)
                except OSError:
                    pass
        elif isinstance(value, dict):
            for v in value.values():
                _visit(v)
        elif isinstance(value, list):
            for item in value:
                _visit(item)

    _visit(outputs)
    return paths


def register_block_artifacts(
    pipeline_id: str,
    run_id: str,
    node_id: str,
    block_type: str,
    outputs: dict[str, Any],
    run_dir: str,
) -> list[str]:
    """Scan block outputs for files and register them as artifacts.

    Also scans the block's run_dir for any files written via ctx.save_artifact().

    Args:
        pipeline_id: The pipeline that owns this run.
        run_id: The current run ID.
        node_id: The DAG node that produced these outputs.
        block_type: The block type (e.g. "jsonl_exporter").
        outputs: The block's output dict from ctx.get_outputs().
        run_dir: The block's run directory (artifacts/{run_id}/{node_id}).

    Returns:
        List of artifact IDs that were registered.
    """
    # Collect file paths from outputs
    file_paths = _extract_file_paths(outputs)

    # Also scan the block's run_dir/artifacts/ for files saved via ctx.save_artifact()
    artifacts_subdir = os.path.join(run_dir, "artifacts")
    if os.path.isdir(artifacts_subdir):
        try:
            for entry in os.scandir(artifacts_subdir):
                if entry.is_file() and entry.path not in file_paths:
                    file_paths.append(entry.path)
        except OSError:
            pass

    if not file_paths:
        return []

    # Deduplicate by absolute path
    seen: set[str] = set()
    unique_paths: list[str] = []
    for p in file_paths:
        abs_p = os.path.abspath(p)
        if abs_p not in seen:
            seen.add(abs_p)
            unique_paths.append(abs_p)

    # Filter out internal engine files
    unique_paths = [
        p for p in unique_paths
        if os.path.basename(p) not in _INTERNAL_FILES
    ]

    if not unique_paths:
        return []

    # Use a separate session to avoid interfering with the executor's transaction
    db = SessionLocal()
    artifact_ids: list[str] = []
    try:
        for file_path in unique_paths:
            try:
                stat = os.stat(file_path)
                size_bytes = stat.st_size
            except OSError:
                continue

            artifact_id = str(uuid.uuid4())
            name = os.path.basename(file_path)
            artifact_type = _infer_artifact_type(file_path)
            file_hash = _sha256_file(file_path)

            artifact = Artifact(
                id=artifact_id,
                run_id=run_id,
                pipeline_id=pipeline_id,
                node_id=node_id,
                block_type=block_type,
                name=name,
                artifact_type=artifact_type,
                file_path=file_path,
                size_bytes=size_bytes,
                hash=file_hash,
                metadata_={},
                created_at=datetime.now(timezone.utc),
            )
            db.add(artifact)
            artifact_ids.append(artifact_id)

        if artifact_ids:
            db.commit()
    except Exception:
        # Artifact registration is best-effort — never crash the pipeline
        try:
            db.rollback()
        except Exception:
            pass
        artifact_ids = []
    finally:
        db.close()

    return artifact_ids
