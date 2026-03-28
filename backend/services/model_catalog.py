"""Model Catalog — scalable model intelligence for OOM prediction and context checks.

Loads model families from docs/MODEL_CATALOG.yaml, compiles regex patterns,
and provides O(N) lookup where N is the number of families (~50). Falls back
to heuristic extraction (parsing "7b", "70b", "350m" from the name) when no
family matches.

Thread-safe: the catalog is immutable after loading.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("blueprint.copilot.model_catalog")

_CATALOG_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "MODEL_CATALOG.yaml"


@dataclass(frozen=True)
class ModelInfo:
    """Resolved model intelligence for a single model name."""
    params_b: float          # Parameter count in billions
    context: int | None      # Context window in tokens, or None if unknown
    source: str              # How this was resolved: "catalog", "heuristic", "config"


@dataclass(frozen=True)
class _CompiledFamily:
    """A compiled model family entry from the YAML catalog."""
    regex: re.Pattern
    aliases: frozenset[str]
    params_b: float
    context: int | None


@dataclass(frozen=True)
class _HeuristicPattern:
    """A compiled heuristic extraction pattern."""
    regex: re.Pattern
    unit: str  # "B" for billions, "M" for millions


def _normalize_name(name: str) -> str:
    """Normalize a model name for matching.

    Lowercases and replaces /, _, . with '-' so that:
      "meta-llama/Llama-3.1-8B-Instruct" → "meta-llama-llama-3-1-8b-instruct"
      "Qwen/Qwen2.5-72B-Instruct"        → "qwen-qwen2-5-72b-instruct"
    """
    return re.sub(r"[/_.]", "-", name.lower())


class ModelCatalog:
    """Lazy-loaded, immutable model catalog backed by docs/MODEL_CATALOG.yaml.

    Usage:
        catalog = ModelCatalog()
        info = catalog.lookup("meta-llama/Llama-3.1-8B-Instruct")
        if info:
            print(f"{info.params_b}B params, context={info.context}")
    """

    def __init__(self) -> None:
        self._families: list[_CompiledFamily] | None = None
        self._heuristics: list[_HeuristicPattern] | None = None

    def _ensure_loaded(self) -> None:
        """Lazy-load and compile the catalog on first access."""
        if self._families is not None:
            return

        families: list[_CompiledFamily] = []
        heuristics: list[_HeuristicPattern] = []

        try:
            with open(_CATALOG_PATH, "r") as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning("MODEL_CATALOG.yaml not found at %s — using empty catalog", _CATALOG_PATH)
            self._families = []
            self._heuristics = []
            return
        except yaml.YAMLError as e:
            logger.error("Failed to parse MODEL_CATALOG.yaml: %s", e)
            self._families = []
            self._heuristics = []
            return

        # Compile family patterns
        for entry in data.get("families", []):
            pattern_str = entry.get("pattern", "")
            try:
                regex = re.compile(pattern_str, re.IGNORECASE)
            except re.error as e:
                logger.warning("Invalid regex in MODEL_CATALOG.yaml: %r — %s", pattern_str, e)
                continue

            aliases = frozenset(a.lower() for a in entry.get("aliases", []))
            families.append(_CompiledFamily(
                regex=regex,
                aliases=aliases,
                params_b=float(entry.get("params_b", 0)),
                context=int(entry["context"]) if entry.get("context") is not None else None,
            ))

        # Compile heuristic patterns
        for entry in data.get("heuristic_patterns", []):
            pattern_str = entry.get("pattern", "")
            try:
                regex = re.compile(pattern_str, re.IGNORECASE)
            except re.error as e:
                logger.warning("Invalid heuristic regex: %r — %s", pattern_str, e)
                continue
            heuristics.append(_HeuristicPattern(
                regex=regex,
                unit=entry.get("unit", "B"),
            ))

        self._families = families
        self._heuristics = heuristics
        logger.info(
            "Model catalog loaded: %d families, %d heuristic patterns",
            len(families), len(heuristics),
        )

    def lookup(self, model_name: str) -> ModelInfo | None:
        """Look up model intelligence by name.

        Resolution order:
        1. Regex pattern match against compiled family entries (first match wins)
        2. Exact alias substring match
        3. Heuristic extraction (parse "7b", "70b", "350m" from name)
        4. None — model is unknown

        Args:
            model_name: Raw model name string from block config.

        Returns:
            ModelInfo with params_b and optional context, or None.
        """
        self._ensure_loaded()
        assert self._families is not None
        assert self._heuristics is not None

        if not model_name:
            return None

        normalized = _normalize_name(model_name)

        # 1. Regex pattern match (first match wins — families are ordered specific → generic)
        for family in self._families:
            if family.regex.search(normalized):
                return ModelInfo(
                    params_b=family.params_b,
                    context=family.context,
                    source="catalog",
                )

        # 2. Alias substring match (fallback for unusual name formats)
        for family in self._families:
            for alias in family.aliases:
                if alias in normalized:
                    return ModelInfo(
                        params_b=family.params_b,
                        context=family.context,
                        source="catalog",
                    )

        # 3. Heuristic extraction
        for heuristic in self._heuristics:
            match = heuristic.regex.search(normalized)
            if match:
                try:
                    value = float(match.group(1))
                    if heuristic.unit == "M":
                        value = value / 1000.0
                    if value > 0:
                        return ModelInfo(
                            params_b=value,
                            context=None,
                            source="heuristic",
                        )
                except (ValueError, IndexError):
                    continue

        return None

    def lookup_from_config(self, config: dict[str, Any]) -> ModelInfo | None:
        """Look up model info from a block config dict.

        Checks config keys in priority order:
        1. Explicit model_params_b / num_parameters (user-specified)
        2. model_name / model / base_model / pretrained_model_name_or_path
        """
        # Check explicit parameter count first (highest priority — user knows best)
        for key in ("model_params_b", "num_parameters", "param_count"):
            val = config.get(key)
            if val is not None:
                try:
                    params = float(val)
                    if params > 0:
                        # If the value looks like raw param count (>100), convert to billions
                        if params > 1000:
                            params = params / 1e9
                        return ModelInfo(
                            params_b=params,
                            context=None,
                            source="config",
                        )
                except (ValueError, TypeError):
                    pass

        # Check explicit context window
        explicit_context = None
        for key in ("model_max_length", "max_position_embeddings", "context_length"):
            val = config.get(key)
            if val is not None:
                try:
                    explicit_context = int(val)
                    break
                except (ValueError, TypeError):
                    pass

        # Try model name lookup
        for key in ("model_name", "model", "base_model", "pretrained_model_name_or_path", "model_id"):
            name = config.get(key)
            if name and isinstance(name, str):
                info = self.lookup(name)
                if info:
                    # Override context if explicitly specified
                    if explicit_context is not None:
                        return ModelInfo(
                            params_b=info.params_b,
                            context=explicit_context,
                            source=info.source,
                        )
                    return info

        return None

    def get_context_from_config(self, config: dict[str, Any]) -> int | None:
        """Get model context window from config, checking explicit keys then catalog."""
        # Explicit context keys
        for key in ("model_max_length", "max_position_embeddings", "context_length"):
            val = config.get(key)
            if val is not None:
                try:
                    return int(val)
                except (ValueError, TypeError):
                    pass
        # Fall back to catalog lookup
        info = self.lookup_from_config(config)
        return info.context if info else None


# Module-level singleton
_catalog: ModelCatalog | None = None


def get_model_catalog() -> ModelCatalog:
    """Return the global ModelCatalog singleton (lazy-loaded)."""
    global _catalog
    if _catalog is None:
        _catalog = ModelCatalog()
    return _catalog
