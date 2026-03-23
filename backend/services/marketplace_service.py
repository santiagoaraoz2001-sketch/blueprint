"""
Marketplace service — manages the local marketplace registry.

For v1, the marketplace is a local registry backed by a JSON file.
Future: remote registry at marketplace.specific.ai
"""

import json
import logging
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import yaml

from ..config import BASE_DIR, BUILTIN_BLOCKS_DIR, BLOCKS_DIR

logger = logging.getLogger("blueprint.marketplace")

MARKETPLACE_DIR = BASE_DIR / "marketplace"
REGISTRY_FILE = MARKETPLACE_DIR / "registry.json"
PACKAGES_DIR = MARKETPLACE_DIR / "packages"

VALID_ITEM_TYPES = {"block", "template", "plugin"}
VALID_SORT_OPTIONS = {"popular", "newest", "rating"}
# Regex: only alphanumeric, hyphens, and underscores allowed in item IDs
ITEM_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

_registry_lock = Lock()


def ensure_marketplace_dirs():
    """Create marketplace directories if they don't exist."""
    MARKETPLACE_DIR.mkdir(parents=True, exist_ok=True)
    PACKAGES_DIR.mkdir(parents=True, exist_ok=True)


def _validate_item_id(item_id: str) -> None:
    """Validate item_id format to prevent path traversal and injection."""
    if not item_id or not ITEM_ID_PATTERN.match(item_id):
        raise ValueError(f"Invalid item ID format: '{item_id}'")


def _load_registry() -> dict[str, Any]:
    """Load the marketplace registry from disk. Caller must hold _registry_lock."""
    ensure_marketplace_dirs()
    if not REGISTRY_FILE.exists():
        return {"items": {}, "version": "1.0.0"}
    try:
        with open(REGISTRY_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load marketplace registry: %s", e)
        return {"items": {}, "version": "1.0.0"}


def _save_registry(registry: dict[str, Any]) -> None:
    """Persist the marketplace registry to disk atomically. Caller must hold _registry_lock."""
    ensure_marketplace_dirs()
    tmp = REGISTRY_FILE.with_suffix(".json.tmp")
    try:
        with open(tmp, "w") as f:
            json.dump(registry, f, indent=2)
        tmp.rename(REGISTRY_FILE)
    except OSError as e:
        logger.error("Failed to save marketplace registry: %s", e)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def browse(
    category: str = "",
    search: str = "",
    sort: str = "popular",
    page: int = 1,
    per_page: int = 20,
) -> dict[str, Any]:
    """Browse marketplace items with filtering, sorting, and pagination."""
    # Validate and clamp pagination parameters
    page = max(1, page)
    per_page = max(1, min(per_page, 100))

    # Validate category if provided
    if category and category not in VALID_ITEM_TYPES:
        raise ValueError(f"Invalid category: '{category}'. Must be one of: {', '.join(sorted(VALID_ITEM_TYPES))}")

    # Default to 'popular' for unrecognized sort values
    if sort not in VALID_SORT_OPTIONS:
        sort = "popular"

    with _registry_lock:
        registry = _load_registry()

    items = list(registry.get("items", {}).values())

    # Filter by category
    if category:
        items = [i for i in items if i.get("item_type") == category]

    # Filter by search
    if search:
        q = search.lower()
        items = [
            i for i in items
            if q in i.get("name", "").lower()
            or q in i.get("description", "").lower()
            or any(q in t.lower() for t in i.get("tags", []))
            or q in i.get("author", "").lower()
        ]

    # Sort
    if sort == "popular":
        items.sort(key=lambda i: i.get("downloads", 0), reverse=True)
    elif sort == "newest":
        items.sort(key=lambda i: i.get("published_at", ""), reverse=True)
    elif sort == "rating":
        items.sort(key=lambda i: i.get("avg_rating", 0), reverse=True)

    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = items[start:end]

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


def get_item(item_id: str) -> dict[str, Any] | None:
    """Get full details for a marketplace item."""
    _validate_item_id(item_id)
    with _registry_lock:
        registry = _load_registry()
    return registry.get("items", {}).get(item_id)


def install_item(item_id: str) -> dict[str, Any]:
    """Install a marketplace item."""
    _validate_item_id(item_id)

    with _registry_lock:
        registry = _load_registry()
        item = registry.get("items", {}).get(item_id)
        if not item:
            raise ValueError(f"Item '{item_id}' not found in marketplace")

        if item.get("installed"):
            return {"status": "already_installed", "item_id": item_id}

        item_type = item.get("item_type", "block")
        source_path = item.get("source_path")

        if item_type == "block" and source_path:
            src = Path(source_path)
            if src.exists():
                # Copy block to user blocks directory
                dest = BLOCKS_DIR / src.parent.name / src.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    shutil.rmtree(str(dest))
                shutil.copytree(str(src), str(dest))

        # Mark as installed
        item["installed"] = True
        item["installed_at"] = _now_iso()
        item["downloads"] = item.get("downloads", 0) + 1
        _save_registry(registry)

    return {"status": "installed", "item_id": item_id, "item": item}


def uninstall_item(item_id: str) -> dict[str, Any]:
    """Uninstall a marketplace item."""
    _validate_item_id(item_id)

    with _registry_lock:
        registry = _load_registry()
        item = registry.get("items", {}).get(item_id)
        if not item:
            raise ValueError(f"Item '{item_id}' not found in marketplace")

        if not item.get("installed"):
            return {"status": "not_installed", "item_id": item_id}

        item_type = item.get("item_type", "block")
        source_path = item.get("source_path")

        # Only remove from user blocks dir (never touch builtins)
        if item_type == "block" and source_path:
            src = Path(source_path)
            dest = BLOCKS_DIR / src.parent.name / src.name
            # Safety: ensure dest is within BLOCKS_DIR before removing
            try:
                dest.resolve().relative_to(BLOCKS_DIR.resolve())
            except ValueError:
                raise ValueError("Cannot uninstall: resolved path is outside blocks directory")
            if dest.exists():
                shutil.rmtree(str(dest))

        item["installed"] = False
        item.pop("installed_at", None)
        _save_registry(registry)

    return {"status": "uninstalled", "item_id": item_id}


def publish_item(body: dict[str, Any]) -> dict[str, Any]:
    """Publish a local block/template/plugin to the marketplace."""
    item_type = body.get("type", "block")
    path = body.get("path", "")
    name = body.get("name", "")
    description = body.get("description", "")
    tags = body.get("tags", [])
    license_type = body.get("license", "MIT")
    author = body.get("author", "Local User")

    if not name:
        raise ValueError("Item name is required")
    if not path:
        raise ValueError("Item path is required")
    if item_type not in VALID_ITEM_TYPES:
        raise ValueError(f"Invalid item type: '{item_type}'. Must be one of: {', '.join(sorted(VALID_ITEM_TYPES))}")

    source = Path(path)
    if not source.exists():
        raise ValueError(f"Source path does not exist: {path}")

    # Sanitize name for item_id: only keep alphanumeric and hyphens
    safe_name = re.sub(r"[^a-z0-9-]", "-", name.lower().strip())
    safe_name = re.sub(r"-+", "-", safe_name).strip("-")
    if not safe_name:
        safe_name = "item"
    item_id = f"{item_type}-{safe_name}-{uuid.uuid4().hex[:8]}"

    # Read version from block.yaml or plugin.yaml if available
    version = "1.0.0"
    for manifest_name in ["block.yaml", "plugin.yaml", "manifest.json"]:
        manifest_path = source / manifest_name
        if manifest_path.exists():
            try:
                with open(manifest_path) as f:
                    if manifest_name.endswith(".json"):
                        meta = json.load(f)
                    else:
                        meta = yaml.safe_load(f)
                version = meta.get("version", version)
            except Exception:
                pass

    # Package the item (overwrite if exists from a previous failed attempt)
    pkg_dir = PACKAGES_DIR / item_id
    if pkg_dir.exists():
        shutil.rmtree(str(pkg_dir))
    shutil.copytree(str(source), str(pkg_dir))

    now = _now_iso()
    item = {
        "id": item_id,
        "item_type": item_type,
        "name": name,
        "description": description,
        "author": author,
        "version": version,
        "tags": tags,
        "license": license_type,
        "source_path": str(source),
        "package_path": str(pkg_dir),
        "downloads": 0,
        "avg_rating": 0.0,
        "rating_count": 0,
        "reviews": [],
        "installed": False,
        "published": True,
        "published_at": now,
        "last_updated": now,
    }

    with _registry_lock:
        registry = _load_registry()
        registry.setdefault("items", {})[item_id] = item
        _save_registry(registry)

    return {"status": "published", "item_id": item_id, "item": item}


def list_installed() -> list[dict[str, Any]]:
    """List all installed marketplace items."""
    with _registry_lock:
        registry = _load_registry()
    return [
        item for item in registry.get("items", {}).values()
        if item.get("installed")
    ]


def submit_review(item_id: str, rating: int, text: str) -> dict[str, Any]:
    """Submit a review for a marketplace item."""
    _validate_item_id(item_id)
    if not 1 <= rating <= 5:
        raise ValueError("Rating must be between 1 and 5")
    if not text or not text.strip():
        raise ValueError("Review text is required")

    with _registry_lock:
        registry = _load_registry()
        item = registry.get("items", {}).get(item_id)
        if not item:
            raise ValueError(f"Item '{item_id}' not found")

        review = {
            "id": f"review-{uuid.uuid4().hex[:8]}",
            "rating": rating,
            "text": text.strip(),
            "author": "Local User",
            "created_at": _now_iso(),
        }

        reviews = item.setdefault("reviews", [])
        reviews.append(review)

        # Update average rating
        total_rating = sum(r["rating"] for r in reviews)
        item["avg_rating"] = round(total_rating / len(reviews), 1)
        item["rating_count"] = len(reviews)

        _save_registry(registry)

    return {"status": "submitted", "review": review}


def get_reviews(item_id: str) -> list[dict[str, Any]]:
    """Get all reviews for a marketplace item."""
    _validate_item_id(item_id)
    with _registry_lock:
        registry = _load_registry()
    item = registry.get("items", {}).get(item_id)
    if not item:
        raise ValueError(f"Item '{item_id}' not found")
    return item.get("reviews", [])


def get_published_items() -> list[dict[str, Any]]:
    """Get items published by the current user."""
    with _registry_lock:
        registry = _load_registry()
    return [
        item for item in registry.get("items", {}).values()
        if item.get("published")
    ]


def seed_registry():
    """Seed the marketplace with built-in items if registry is empty."""
    with _registry_lock:
        registry = _load_registry()
        if registry.get("items"):
            return  # Already seeded

        seed_items = _build_seed_items()
        registry["items"] = {item["id"]: item for item in seed_items}
        _save_registry(registry)
    logger.info("Seeded marketplace with %d items", len(seed_items))


def _build_seed_items() -> list[dict[str, Any]]:
    """Build seed items from the existing block library and templates."""
    items: list[dict[str, Any]] = []
    now = _now_iso()

    # Seed blocks from builtin blocks directory
    seed_blocks = [
        ("data", "text_normalizer", {
            "name": "Text Normalizer",
            "description": "Normalize and clean text data with configurable preprocessing steps including lowercasing, whitespace normalization, and special character handling.",
            "tags": ["data", "preprocessing", "text", "cleaning"],
            "downloads": 1247,
            "avg_rating": 4.5,
            "rating_count": 23,
        }),
        ("data", "csv_loader", {
            "name": "CSV Data Loader",
            "description": "Load and parse CSV files with automatic type detection, missing value handling, and configurable delimiters.",
            "tags": ["data", "csv", "loading", "tabular"],
            "downloads": 2891,
            "avg_rating": 4.7,
            "rating_count": 45,
        }),
        ("data", "data_splitter", {
            "name": "Data Splitter",
            "description": "Split datasets into train/validation/test sets with stratified sampling, k-fold cross-validation, and reproducible random seeds.",
            "tags": ["data", "splitting", "training", "validation"],
            "downloads": 1834,
            "avg_rating": 4.3,
            "rating_count": 31,
        }),
        ("inference", "llm_inference", {
            "name": "LLM Inference",
            "description": "Run inference with any large language model. Supports OpenAI, Anthropic, local models via Ollama, and custom endpoints.",
            "tags": ["inference", "llm", "generation", "prompting"],
            "downloads": 5623,
            "avg_rating": 4.8,
            "rating_count": 89,
        }),
        ("evaluation", "metric_evaluator", {
            "name": "Metric Evaluator",
            "description": "Comprehensive evaluation block supporting BLEU, ROUGE, accuracy, F1, perplexity, and custom metric functions.",
            "tags": ["evaluation", "metrics", "benchmarking"],
            "downloads": 1456,
            "avg_rating": 4.4,
            "rating_count": 28,
        }),
    ]

    for category, block_type, overrides in seed_blocks:
        block_dir = BUILTIN_BLOCKS_DIR / category / block_type
        if not block_dir.exists():
            # Still add the item even if block dir doesn't exist locally
            pass

        item_id = f"block-{block_type}"
        item = {
            "id": item_id,
            "item_type": "block",
            "name": overrides["name"],
            "description": overrides["description"],
            "author": "Blueprint Team",
            "version": "1.0.0",
            "tags": overrides.get("tags", []),
            "license": "MIT",
            "source_path": str(block_dir) if block_dir.exists() else "",
            "downloads": overrides.get("downloads", 0),
            "avg_rating": overrides.get("avg_rating", 0.0),
            "rating_count": overrides.get("rating_count", 0),
            "reviews": _make_seed_reviews(overrides.get("avg_rating", 4.0)),
            "installed": block_dir.exists(),
            "published": True,
            "published_at": now,
            "last_updated": now,
            "is_seed": True,
        }
        items.append(item)

    # Seed templates
    template_seeds = [
        {
            "id": "template-lora-finetune",
            "name": "LoRA Fine-Tune Pipeline",
            "description": "Complete LoRA fine-tuning pipeline with data preparation, training with configurable rank/alpha, evaluation, and model export.",
            "tags": ["training", "lora", "fine-tuning", "llm"],
            "downloads": 3412,
            "avg_rating": 4.6,
            "rating_count": 52,
        },
        {
            "id": "template-rag-pipeline",
            "name": "RAG Pipeline",
            "description": "Production-ready Retrieval-Augmented Generation pipeline with document ingestion, chunking, vector storage, and retrieval agent.",
            "tags": ["rag", "retrieval", "agents", "knowledge-base"],
            "downloads": 4567,
            "avg_rating": 4.7,
            "rating_count": 67,
        },
        {
            "id": "template-eval-suite",
            "name": "Evaluation Suite",
            "description": "Comprehensive model evaluation template with multiple metrics, comparison charts, and automated reporting.",
            "tags": ["evaluation", "benchmarking", "metrics", "reporting"],
            "downloads": 1823,
            "avg_rating": 4.3,
            "rating_count": 29,
        },
    ]

    for seed in template_seeds:
        item = {
            **seed,
            "item_type": "template",
            "author": "Blueprint Team",
            "version": "1.0.0",
            "license": "MIT",
            "source_path": "",
            "reviews": _make_seed_reviews(seed.get("avg_rating", 4.0)),
            "installed": False,
            "published": True,
            "published_at": now,
            "last_updated": now,
            "is_seed": True,
        }
        items.append(item)

    # Seed plugins
    plugin_seeds = [
        {
            "id": "plugin-wandb-monitor",
            "name": "W&B Monitor",
            "description": "Weights & Biases integration for experiment tracking, metric logging, artifact versioning, and collaborative dashboards.",
            "tags": ["monitoring", "wandb", "tracking", "mlops"],
            "downloads": 2345,
            "avg_rating": 4.5,
            "rating_count": 38,
        },
        {
            "id": "plugin-gpu-profiler",
            "name": "GPU Profiler",
            "description": "Real-time GPU utilization profiler with memory tracking, CUDA kernel analysis, and optimization suggestions.",
            "tags": ["monitoring", "gpu", "profiling", "performance"],
            "downloads": 1567,
            "avg_rating": 4.2,
            "rating_count": 21,
        },
    ]

    for seed in plugin_seeds:
        item = {
            **seed,
            "item_type": "plugin",
            "author": "Blueprint Team",
            "version": "1.0.0",
            "license": "MIT",
            "source_path": "",
            "reviews": _make_seed_reviews(seed.get("avg_rating", 4.0)),
            "installed": False,
            "published": True,
            "published_at": now,
            "last_updated": now,
            "is_seed": True,
        }
        items.append(item)

    return items


def _make_seed_reviews(avg_rating: float) -> list[dict[str, Any]]:
    """Generate a few seed reviews for demo purposes."""
    reviews_data = [
        (5, "Excellent block, works perfectly out of the box."),
        (4, "Good functionality, documentation could be more detailed."),
        (5, "Great addition to my pipeline. Highly recommend."),
        (3, "Works but could use some performance improvements."),
        (4, "Solid implementation, easy to configure."),
    ]
    # Pick reviews that roughly match the target average
    selected = []
    if avg_rating >= 4.5:
        selected = [reviews_data[0], reviews_data[2], reviews_data[4]]
    elif avg_rating >= 4.0:
        selected = [reviews_data[1], reviews_data[4]]
    else:
        selected = [reviews_data[1], reviews_data[3]]

    now = _now_iso()
    return [
        {
            "id": f"seed-review-{i}",
            "rating": rating,
            "text": text,
            "author": "Blueprint User",
            "created_at": now,
        }
        for i, (rating, text) in enumerate(selected)
    ]


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()
