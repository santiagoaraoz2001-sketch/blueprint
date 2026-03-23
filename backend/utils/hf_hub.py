"""HuggingFace Hub integration — search models and fetch details via the public API.

Uses only the ``requests`` library (no huggingface_hub dependency).
All functions handle errors gracefully and return typed dicts.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

import requests

logger = logging.getLogger(__name__)

HF_API_BASE = "https://huggingface.co/api"
_TIMEOUT = 15  # seconds


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class HFModelSummary(TypedDict):
    id: str
    author: str
    downloads: int
    likes: int
    pipeline_tag: str
    tags: list[str]
    formats: list[str]
    last_modified: str


class HFModelDetail(TypedDict):
    id: str
    author: str
    downloads: int
    likes: int
    pipeline_tag: str
    tags: list[str]
    formats: list[str]
    last_modified: str
    card_data: dict[str, Any]
    siblings: list[dict[str, Any]]
    description: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FORMAT_EXTENSIONS: dict[str, str] = {
    ".gguf": "gguf",
    ".safetensors": "safetensors",
    ".bin": "pytorch",
    ".pt": "pytorch",
    ".onnx": "onnx",
    ".tflite": "tflite",
    ".mlmodel": "coreml",
    ".mlpackage": "coreml",
}


def _extract_formats(siblings: list[dict[str, Any]]) -> list[str]:
    """Detect model formats from the files list (siblings)."""
    formats: set[str] = set()
    for entry in siblings:
        filename: str = entry.get("rfilename", "")
        for ext, fmt in _FORMAT_EXTENSIONS.items():
            if filename.endswith(ext):
                formats.add(fmt)
    return sorted(formats)


def _parse_model_summary(raw: dict[str, Any]) -> HFModelSummary:
    """Parse a raw HF API model object into a clean summary dict."""
    siblings = raw.get("siblings", [])
    author = raw.get("author", "")
    model_id: str = raw.get("modelId", raw.get("id", ""))
    if not author and "/" in model_id:
        author = model_id.split("/")[0]
    return HFModelSummary(
        id=model_id,
        author=author,
        downloads=raw.get("downloads", 0),
        likes=raw.get("likes", 0),
        pipeline_tag=raw.get("pipeline_tag", ""),
        tags=raw.get("tags", []),
        formats=_extract_formats(siblings),
        last_modified=raw.get("lastModified", ""),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_models(
    query: str,
    task: str | None = None,
    limit: int = 20,
) -> list[HFModelSummary]:
    """Search HuggingFace Hub for models matching *query*.

    Parameters
    ----------
    query : str
        Free-text search string.
    task : str, optional
        Pipeline task filter (e.g. ``text-generation``).
    limit : int
        Maximum number of results (default 20).

    Returns
    -------
    list[HFModelSummary]
    """
    params: dict[str, str | int] = {
        "search": query,
        "sort": "downloads",
        "direction": "-1",
        "limit": limit,
    }
    if task:
        params["pipeline_tag"] = task

    try:
        resp = requests.get(
            f"{HF_API_BASE}/models",
            params=params,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return [_parse_model_summary(m) for m in data]
    except requests.RequestException as exc:
        logger.warning("HuggingFace search failed: %s", exc)
        return []
    except (ValueError, KeyError) as exc:
        logger.warning("HuggingFace response parse error: %s", exc)
        return []


def get_model_details(model_id: str) -> HFModelDetail | None:
    """Fetch full details for a single model.

    Parameters
    ----------
    model_id : str
        Fully-qualified model id, e.g. ``meta-llama/Llama-3-8B``.

    Returns
    -------
    HFModelDetail or None
        ``None`` if the request fails.
    """
    try:
        resp = requests.get(
            f"{HF_API_BASE}/models/{model_id}",
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        raw = resp.json()
    except requests.RequestException as exc:
        logger.warning("HuggingFace model detail request failed: %s", exc)
        return None
    except (ValueError, KeyError) as exc:
        logger.warning("HuggingFace model detail parse error: %s", exc)
        return None

    siblings = raw.get("siblings", [])
    author = raw.get("author", "")
    mid: str = raw.get("modelId", raw.get("id", model_id))
    if not author and "/" in mid:
        author = mid.split("/")[0]

    card_data = raw.get("cardData", {}) or {}

    return HFModelDetail(
        id=mid,
        author=author,
        downloads=raw.get("downloads", 0),
        likes=raw.get("likes", 0),
        pipeline_tag=raw.get("pipeline_tag", ""),
        tags=raw.get("tags", []),
        formats=_extract_formats(siblings),
        last_modified=raw.get("lastModified", ""),
        card_data=card_data,
        siblings=siblings,
        description=card_data.get("description", raw.get("description", "")),
    )
