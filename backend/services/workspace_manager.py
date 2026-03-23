"""Managed workspace folder structure for Blueprint.

Creates and maintains an organized directory tree for ML assets:
datasets, models, outputs, embeddings, configs, and an auto-sorting inbox.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Folder structure definition ──

WORKSPACE_DIRS = [
    "inbox",
    "datasets/raw",
    "datasets/processed",
    "models/base",
    "models/fine-tuned",
    "models/merged",
    "models/quantized",
    "outputs/inference",
    "outputs/evaluations",
    "outputs/exports",
    "embeddings",
    "configs",
    "logs",
]

# ── Block type + field name → workspace subfolder mapping ──

# Explicit mappings for known block types
_BLOCK_FIELD_MAP: dict[tuple[str, str], str] = {
    # Endpoint / export blocks
    ("data_export", "output_path"): "outputs/exports",
    ("save_csv", "output_path"): "outputs/exports",
    ("save_json", "output_path"): "outputs/exports",
    ("save_parquet", "output_path"): "outputs/exports",
    ("save_txt", "output_path"): "outputs/exports",
    ("save_yaml", "output_path"): "outputs/exports",
    ("save_pdf", "output_path"): "outputs/exports",
    ("save_model", "output_path"): "models/fine-tuned",
    ("save_embeddings", "output_path"): "embeddings",
    # Source / loader blocks
    ("huggingface_loader", "cache_dir"): "models/base",
    ("huggingface_dataset_loader", "cache_dir"): "datasets/raw",
    ("local_file_loader", "file_path"): "datasets/raw",
    ("model_selector", "local_path"): "models/base",
    ("config_file_loader", "file_path"): "configs",
}

# Fallback: category-based mapping for output_path fields
_CATEGORY_FIELD_MAP: dict[str, str] = {
    "training": "models/fine-tuned",
    "metrics": "outputs/evaluations",
    "evaluation": "outputs/evaluations",
    "inference": "outputs/inference",
    "embedding": "embeddings",
    "endpoints": "outputs/exports",
    "external": "datasets/raw",
    "data": "datasets/processed",
}

# ── Extension → category mapping for inbox auto-sort ──

EXTENSION_MAP: dict[str, str] = {
    # Datasets
    ".csv": "datasets/raw",
    ".parquet": "datasets/raw",
    ".jsonl": "datasets/raw",
    ".tsv": "datasets/raw",
    ".xlsx": "datasets/raw",
    ".arrow": "datasets/raw",
    ".txt": "datasets/raw",
    ".md": "datasets/raw",
    # Models
    ".safetensors": "models/base",
    ".bin": "models/base",
    ".gguf": "models/base",
    ".pt": "models/base",
    ".pth": "models/base",
    ".onnx": "models/base",
    # Configs
    ".json": "configs",
    ".yaml": "configs",
    ".yml": "configs",
    ".toml": "configs",
    # Embeddings
    ".npy": "embeddings",
    ".hdf5": "embeddings",
    ".faiss": "embeddings",
    # Exports/archives
    ".pdf": "outputs/exports",
    ".zip": "outputs/exports",
}

# Category prefix for naming convention
_CATEGORY_PREFIX: dict[str, str] = {
    "datasets/raw": "dataset",
    "datasets/processed": "dataset",
    "models/base": "model",
    "models/fine-tuned": "model",
    "models/merged": "model",
    "models/quantized": "model",
    "outputs/inference": "output",
    "outputs/evaluations": "eval",
    "outputs/exports": "export",
    "embeddings": "embedding",
    "configs": "config",
    "logs": "log",
}


class WorkspaceManager:
    """Manages the workspace folder structure and path resolution."""

    def __init__(self, root_path: str):
        self.root = Path(root_path)

    def ensure_structure(self) -> None:
        """Create all workspace directories (idempotent)."""
        for subdir in WORKSPACE_DIRS:
            (self.root / subdir).mkdir(parents=True, exist_ok=True)
        logger.info("Workspace structure ensured at %s", self.root)

    def resolve_output_path(self, block_type: str, field_name: str, category: str = "") -> str | None:
        """Map a block type + field name to an absolute workspace path.

        Returns None if no mapping exists (field won't be auto-filled).
        """
        # 1. Check explicit block+field mapping
        subfolder = _BLOCK_FIELD_MAP.get((block_type, field_name))

        # 2. Fall back to category-based mapping for output_path fields
        if not subfolder and field_name in ("output_path", "save_path", "export_path", "cache_dir"):
            subfolder = _CATEGORY_FIELD_MAP.get(category)

        if subfolder:
            return str(self.root / subfolder)

        return None

    def get_all_paths(self) -> dict[str, str]:
        """Return a mapping of subfolder keys to absolute paths for the frontend."""
        paths = {}
        for subdir in WORKSPACE_DIRS:
            key = subdir.replace("/", "_")
            paths[key] = str(self.root / subdir)
        return paths

    def get_folder_health(self) -> dict[str, bool]:
        """Check which workspace directories exist."""
        health = {}
        for subdir in WORKSPACE_DIRS:
            key = subdir.replace("/", "_")
            health[key] = (self.root / subdir).is_dir()
        return health

    def get_inbox_count(self) -> int:
        """Count files in the inbox directory."""
        inbox = self.root / "inbox"
        if not inbox.is_dir():
            return 0
        return sum(1 for f in inbox.iterdir() if f.is_file())

    def list_inbox_files(self) -> list[dict]:
        """List files currently in the inbox."""
        inbox = self.root / "inbox"
        if not inbox.is_dir():
            return []
        files = []
        for f in sorted(inbox.iterdir()):
            if f.is_file():
                files.append({
                    "name": f.name,
                    "size_bytes": f.stat().st_size,
                    "extension": f.suffix.lower(),
                })
        return files

    @staticmethod
    def rename_for_workspace(original_name: str, subfolder: str) -> str:
        """Rename a file to workspace naming convention.

        Format: {category}_{descriptive-name}_{YYYY-MM-DD}.{ext}
        """
        p = Path(original_name)

        # Handle compound extensions like .tar.gz
        if p.name.endswith(".tar.gz"):
            ext = ".tar.gz"
            stem = p.name[: -len(".tar.gz")]
        else:
            ext = p.suffix.lower()
            stem = p.stem

        category = _CATEGORY_PREFIX.get(subfolder, "file")
        date_str = datetime.now().strftime("%Y-%m-%d")

        # Clean the stem: lowercase, replace spaces/underscores with hyphens,
        # strip common prefixes, keep only alphanumeric + hyphens
        clean = stem.lower()
        clean = re.sub(r"[_\s]+", "-", clean)
        clean = re.sub(r"[^a-z0-9\-]", "", clean)
        clean = re.sub(r"-+", "-", clean).strip("-")

        # Limit length
        if len(clean) > 40:
            clean = clean[:40].rstrip("-")

        if not clean:
            clean = "unnamed"

        return f"{category}_{clean}_{date_str}{ext}"

    @staticmethod
    def deduplicate_path(target_dir: Path, filename: str) -> Path:
        """Ensure a unique filename by appending -2, -3, etc. if needed."""
        target = target_dir / filename
        if not target.exists():
            return target

        p = Path(filename)
        # Handle compound extensions
        if filename.endswith(".tar.gz"):
            ext = ".tar.gz"
            stem = filename[: -len(".tar.gz")]
        else:
            ext = p.suffix
            stem = p.stem

        counter = 2
        while True:
            new_name = f"{stem}-{counter}{ext}"
            new_target = target_dir / new_name
            if not new_target.exists():
                return new_target
            counter += 1

    @staticmethod
    def get_extension_subfolder(filename: str) -> str | None:
        """Determine the target subfolder for a file based on its extension."""
        lower = filename.lower()

        # Handle compound extensions
        if lower.endswith(".tar.gz"):
            return EXTENSION_MAP.get(".tar.gz")

        ext = Path(lower).suffix
        return EXTENSION_MAP.get(ext)
