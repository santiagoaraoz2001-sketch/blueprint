"""Benchmark data fetcher — retrieves model scores from the HuggingFace Open LLM Leaderboard.

Uses only the standard library (``urllib.request`` + ``json``) so the module
has **zero** external dependencies.  Results are cached locally to
``~/.specific-labs/cache/benchmarks.json`` and auto-refreshed every 24 hours.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CACHE_DIR = Path.home() / ".specific-labs" / "cache"
_CACHE_FILE = _CACHE_DIR / "benchmarks.json"
_CACHE_MAX_AGE_S = 24 * 60 * 60  # 24 hours

# HuggingFace Datasets API — the Open LLM Leaderboard publishes its results
# as a dataset on the Hub.  We pull the parquet/json split directly.
_LEADERBOARD_DATASET = "open-llm-leaderboard/results"
_HF_DATASETS_API = "https://huggingface.co/api/datasets"
_HF_LEADERBOARD_API = (
    "https://huggingface.co/api/spaces/open-llm-leaderboard/open_llm_leaderboard"
)
# Fallback: the leaderboard contents endpoint (paginated JSON)
_LEADERBOARD_CONTENTS_URL = (
    "https://huggingface.co/api/datasets/open-llm-leaderboard/results/parquet/default/test/0.parquet"
)
# Simple REST endpoint that returns JSON rows
_LEADERBOARD_JSON_URL = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=open-llm-leaderboard/results&config=default&split=train&offset=0&length=500"
)

_TIMEOUT = 20  # seconds per HTTP request

# Benchmark column names as they appear in the leaderboard dataset
_BENCH_KEYS: dict[str, list[str]] = {
    "mmlu": ["MMLU", "mmlu", "harness|hendrycksTest", "hf_mmlu"],
    "arc": ["ARC", "arc", "arc_challenge", "harness|arc_challenge"],
    "hellaswag": ["HellaSwag", "hellaswag", "harness|hellaswag"],
    "truthfulqa": ["TruthfulQA", "truthfulqa", "truthfulqa_mc2", "harness|truthfulqa_mc"],
    "winogrande": ["Winogrande", "winogrande", "harness|winogrande"],
    "gsm8k": ["GSM8K", "gsm8k", "harness|gsm8k"],
}

_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Helpers (must be defined before data classes that reference them)
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BenchmarkResult:
    """Benchmark scores for a single model."""

    model_id: str
    mmlu: float | None = None
    arc: float | None = None
    hellaswag: float | None = None
    truthfulqa: float | None = None
    winogrande: float | None = None
    gsm8k: float | None = None
    last_updated: str = field(default_factory=lambda: _now_iso())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BenchmarkResult:
        return cls(
            model_id=d["model_id"],
            mmlu=d.get("mmlu"),
            arc=d.get("arc"),
            hellaswag=d.get("hellaswag"),
            truthfulqa=d.get("truthfulqa"),
            winogrande=d.get("winogrande"),
            gsm8k=d.get("gsm8k"),
            last_updated=d.get("last_updated", _now_iso()),
        )


# ---------------------------------------------------------------------------
# Fallback data — approximate scores for well-known models so the UI is
# never completely empty even when the API is unreachable.
# ---------------------------------------------------------------------------

FALLBACK_BENCHMARKS: dict[str, BenchmarkResult] = {
    "meta-llama/Llama-3-70B-Instruct": BenchmarkResult(
        model_id="meta-llama/Llama-3-70B-Instruct",
        mmlu=82.0, arc=71.4, hellaswag=85.7, truthfulqa=63.1, winogrande=82.6, gsm8k=77.4,
    ),
    "meta-llama/Llama-3-8B": BenchmarkResult(
        model_id="meta-llama/Llama-3-8B",
        mmlu=66.6, arc=60.2, hellaswag=82.1, truthfulqa=51.7, winogrande=78.5, gsm8k=45.6,
    ),
    "meta-llama/Llama-3-8B-Instruct": BenchmarkResult(
        model_id="meta-llama/Llama-3-8B-Instruct",
        mmlu=67.1, arc=62.9, hellaswag=78.6, truthfulqa=51.6, winogrande=77.6, gsm8k=68.6,
    ),
    "mistralai/Mistral-7B-v0.1": BenchmarkResult(
        model_id="mistralai/Mistral-7B-v0.1",
        mmlu=62.5, arc=59.9, hellaswag=83.3, truthfulqa=42.2, winogrande=78.4, gsm8k=37.8,
    ),
    "mistralai/Mixtral-8x7B-v0.1": BenchmarkResult(
        model_id="mistralai/Mixtral-8x7B-v0.1",
        mmlu=70.6, arc=66.4, hellaswag=86.5, truthfulqa=46.8, winogrande=81.7, gsm8k=57.6,
    ),
    "google/gemma-7b": BenchmarkResult(
        model_id="google/gemma-7b",
        mmlu=64.6, arc=61.1, hellaswag=82.2, truthfulqa=44.8, winogrande=79.0, gsm8k=50.9,
    ),
    "google/gemma-2b": BenchmarkResult(
        model_id="google/gemma-2b",
        mmlu=42.3, arc=48.5, hellaswag=71.4, truthfulqa=38.3, winogrande=66.9, gsm8k=17.7,
    ),
    "microsoft/phi-2": BenchmarkResult(
        model_id="microsoft/phi-2",
        mmlu=56.7, arc=61.1, hellaswag=75.1, truthfulqa=44.5, winogrande=74.4, gsm8k=54.8,
    ),
    "microsoft/Phi-3-mini-4k-instruct": BenchmarkResult(
        model_id="microsoft/Phi-3-mini-4k-instruct",
        mmlu=69.9, arc=63.6, hellaswag=78.2, truthfulqa=53.1, winogrande=75.3, gsm8k=75.7,
    ),
    "Qwen/Qwen1.5-72B": BenchmarkResult(
        model_id="Qwen/Qwen1.5-72B",
        mmlu=77.5, arc=65.9, hellaswag=85.9, truthfulqa=59.6, winogrande=83.0, gsm8k=79.5,
    ),
    "Qwen/Qwen1.5-7B": BenchmarkResult(
        model_id="Qwen/Qwen1.5-7B",
        mmlu=61.0, arc=57.4, hellaswag=78.9, truthfulqa=51.6, winogrande=73.8, gsm8k=54.5,
    ),
    "01-ai/Yi-34B": BenchmarkResult(
        model_id="01-ai/Yi-34B",
        mmlu=76.3, arc=65.4, hellaswag=85.7, truthfulqa=56.2, winogrande=83.1, gsm8k=67.2,
    ),
    "tiiuae/falcon-40b": BenchmarkResult(
        model_id="tiiuae/falcon-40b",
        mmlu=55.4, arc=54.5, hellaswag=83.6, truthfulqa=40.4, winogrande=79.5, gsm8k=19.3,
    ),
    "HuggingFaceH4/zephyr-7b-beta": BenchmarkResult(
        model_id="HuggingFaceH4/zephyr-7b-beta",
        mmlu=61.4, arc=62.0, hellaswag=84.4, truthfulqa=57.4, winogrande=77.7, gsm8k=32.2,
    ),
}

# ---------------------------------------------------------------------------
# Helpers (continued)
# ---------------------------------------------------------------------------


def _ensure_cache_dir() -> None:
    """Create the cache directory tree if it does not exist."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_age_seconds() -> float | None:
    """Return age of the cache file in seconds, or *None* if it does not exist."""
    try:
        mtime = _CACHE_FILE.stat().st_mtime
        return time.time() - mtime
    except FileNotFoundError:
        return None


def _read_cache() -> dict[str, dict[str, Any]]:
    """Read the on-disk JSON cache.  Returns an empty dict on any error."""
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.debug("Could not read benchmark cache: %s", exc)
    return {}


def _write_cache(data: dict[str, dict[str, Any]]) -> None:
    """Atomically write *data* to the cache file (write-to-temp then rename).

    This avoids partially-written files if two processes refresh concurrently.
    """
    _ensure_cache_dir()
    # Write to a temporary file in the same directory, then do an atomic
    # rename.  On POSIX this is guaranteed atomic; on Windows it is
    # close-enough for our purposes.
    fd, tmp_path = tempfile.mkstemp(
        dir=str(_CACHE_DIR), prefix=".benchmarks_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp_path, str(_CACHE_FILE))
        logger.debug("Benchmark cache written (%d entries)", len(data))
    except Exception:
        # Clean up the temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _http_get_json(url: str, *, timeout: int = _TIMEOUT) -> Any:
    """Perform a GET request and return the parsed JSON body."""
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Blueprint-ML-Workbench/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw)


def _extract_score(row: dict[str, Any], bench_name: str) -> float | None:
    """Try multiple key variants to pull a benchmark score out of *row*.

    Scores are normalised to the 0-100 range.
    """
    for key_variant in _BENCH_KEYS.get(bench_name, []):
        for key in list(row.keys()):
            if key_variant.lower() in key.lower():
                val = row[key]
                if val is None:
                    continue
                try:
                    score = float(val)
                except (TypeError, ValueError):
                    continue
                # Leaderboard scores are sometimes 0-1, sometimes 0-100.
                if 0 < score <= 1.0:
                    score *= 100.0
                return round(score, 2)
    return None


def _row_to_result(row: dict[str, Any]) -> BenchmarkResult | None:
    """Convert a raw leaderboard row dict into a ``BenchmarkResult``."""
    # The model id can live under different keys depending on dataset version.
    model_id: str | None = None
    for candidate in ("model_name", "model_id", "fullname", "Model", "model"):
        model_id = row.get(candidate)
        if model_id:
            break
    if not model_id:
        return None

    # Strip whitespace / leading "results/" prefix that some rows carry
    model_id = model_id.strip().removeprefix("results/")

    return BenchmarkResult(
        model_id=model_id,
        mmlu=_extract_score(row, "mmlu"),
        arc=_extract_score(row, "arc"),
        hellaswag=_extract_score(row, "hellaswag"),
        truthfulqa=_extract_score(row, "truthfulqa"),
        winogrande=_extract_score(row, "winogrande"),
        gsm8k=_extract_score(row, "gsm8k"),
        last_updated=_now_iso(),
    )


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def _fetch_from_leaderboard() -> list[BenchmarkResult]:
    """Pull benchmark rows from the HuggingFace datasets API.

    Tries the rows endpoint first; on failure returns an empty list so that
    callers can fall back to cached / fallback data.
    """
    results: list[BenchmarkResult] = []
    offset = 0
    page_size = 100
    max_rows = 2000  # safety cap

    logger.info("Fetching benchmark data from HuggingFace Open LLM Leaderboard …")

    while offset < max_rows:
        url = (
            "https://datasets-server.huggingface.co/rows"
            f"?dataset=open-llm-leaderboard/results"
            f"&config=default&split=train&offset={offset}&length={page_size}"
        )
        try:
            data = _http_get_json(url)
        except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Leaderboard fetch failed at offset %d: %s", offset, exc)
            break

        rows = data.get("rows", [])
        if not rows:
            break

        for entry in rows:
            row = entry.get("row", entry)
            result = _row_to_result(row)
            if result is not None:
                results.append(result)

        # If we got fewer rows than requested we've reached the end.
        if len(rows) < page_size:
            break
        offset += page_size

    logger.info("Fetched %d benchmark entries from the leaderboard", len(results))
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def refresh_cache(force: bool = False) -> int:
    """Refresh the local benchmark cache from the HuggingFace leaderboard.

    Parameters
    ----------
    force:
        When *True* the cache is refreshed regardless of its age.

    Returns
    -------
    int
        The number of model entries now stored in the cache.
    """
    with _LOCK:
        age = _cache_age_seconds()
        if not force and age is not None and age < _CACHE_MAX_AGE_S:
            existing = _read_cache()
            logger.debug(
                "Benchmark cache is fresh (%.0f s old, %d entries) — skipping refresh",
                age,
                len(existing),
            )
            return len(existing)

        # Fetch fresh data
        try:
            results = _fetch_from_leaderboard()
        except Exception as exc:
            logger.error("Unexpected error while fetching benchmarks: %s", exc)
            results = []

        # Merge with existing cache so we never *lose* data on a partial fetch
        cache_data = _read_cache()
        for r in results:
            cache_data[r.model_id] = r.to_dict()

        # If the cache is still empty (first run + API failure), seed with fallback data
        if not cache_data:
            logger.info("Seeding benchmark cache with fallback data (%d models)", len(FALLBACK_BENCHMARKS))
            for model_id, fb in FALLBACK_BENCHMARKS.items():
                cache_data[model_id] = fb.to_dict()

        _write_cache(cache_data)
        return len(cache_data)


def _ensure_cache() -> dict[str, dict[str, Any]]:
    """Return cached data, refreshing transparently if stale or missing."""
    age = _cache_age_seconds()
    if age is None or age >= _CACHE_MAX_AGE_S:
        try:
            refresh_cache()
        except Exception as exc:
            logger.warning("Background cache refresh failed: %s", exc)

    cache_data = _read_cache()

    # Last resort: return fallback benchmarks as raw dicts
    if not cache_data:
        return {mid: fb.to_dict() for mid, fb in FALLBACK_BENCHMARKS.items()}

    return cache_data


def get_benchmarks(model_id: str) -> BenchmarkResult | None:
    """Get benchmark scores for a specific model.

    Parameters
    ----------
    model_id:
        A HuggingFace model identifier, e.g. ``"meta-llama/Llama-3-8B"``.

    Returns
    -------
    BenchmarkResult | None
        The benchmark scores, or *None* if the model is not found in the
        cache or fallback data.
    """
    cache = _ensure_cache()

    # Exact match
    if model_id in cache:
        return BenchmarkResult.from_dict(cache[model_id])

    # Case-insensitive match
    model_lower = model_id.lower()
    for key, value in cache.items():
        if key.lower() == model_lower:
            return BenchmarkResult.from_dict(value)

    # Check fallback data directly (in case cache was loaded but doesn't
    # contain this model)
    if model_id in FALLBACK_BENCHMARKS:
        return FALLBACK_BENCHMARKS[model_id]
    for key, fb in FALLBACK_BENCHMARKS.items():
        if key.lower() == model_lower:
            return fb

    return None


def search_benchmarks(query: str, limit: int = 20) -> list[BenchmarkResult]:
    """Search benchmark results by (partial) model name.

    Parameters
    ----------
    query:
        A substring to match against model identifiers.  The search is
        case-insensitive.
    limit:
        Maximum number of results to return (default 20).

    Returns
    -------
    list[BenchmarkResult]
        Matching benchmark entries sorted alphabetically by model id.
    """
    cache = _ensure_cache()
    query_lower = query.lower()

    matches: list[BenchmarkResult] = []
    for key, value in cache.items():
        if query_lower in key.lower():
            matches.append(BenchmarkResult.from_dict(value))
            if len(matches) >= limit:
                break

    # Also search fallback data for models not in the cache
    if len(matches) < limit:
        cached_ids = {m.model_id.lower() for m in matches}
        for key, fb in FALLBACK_BENCHMARKS.items():
            if query_lower in key.lower() and key.lower() not in cached_ids:
                matches.append(fb)
                if len(matches) >= limit:
                    break

    matches.sort(key=lambda r: r.model_id)
    return matches[:limit]
