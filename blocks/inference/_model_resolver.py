"""Model Name Resolution — resolves model identifiers across frameworks.

Provides:
- resolve_model(): Convert any model identifier to rich ModelInfo
- resolve_for_training(): Get the best model ID and framework for training
- resolve_for_merge(): Get the best model ID for merging
- validate_for_framework(): Check if a model can be used with a framework
"""

import json
import logging
import os
import re
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = [
    "ModelInfo",
    "resolve_model",
    "resolve_for_training",
    "resolve_for_merge",
    "validate_for_framework",
]


# ---------------------------------------------------------------------------
# Static lookup tables
# ---------------------------------------------------------------------------

# Ollama tag -> HuggingFace model ID.  Used as a fallback when the Ollama
# daemon is unreachable.  All keys MUST be lowercase.
_KNOWN_OLLAMA_HF_MAP: dict[str, str] = {
    # Llama
    "llama3.2": "meta-llama/Llama-3.2-1B",
    "llama3.2:1b": "meta-llama/Llama-3.2-1B",
    "llama3.2:3b": "meta-llama/Llama-3.2-3B",
    "llama3.1": "meta-llama/Llama-3.1-8B",
    "llama3.1:8b": "meta-llama/Llama-3.1-8B",
    "llama3.1:70b": "meta-llama/Llama-3.1-70B",
    "llama3.1:405b": "meta-llama/Llama-3.1-405B",
    "llama3": "meta-llama/Llama-3-8B",
    "llama3:8b": "meta-llama/Llama-3-8B",
    "llama3:70b": "meta-llama/Llama-3-70B",
    "llama2": "meta-llama/Llama-2-7b-hf",
    "llama2:7b": "meta-llama/Llama-2-7b-hf",
    "llama2:13b": "meta-llama/Llama-2-13b-hf",
    "llama2:70b": "meta-llama/Llama-2-70b-hf",
    "codellama": "codellama/CodeLlama-7b-hf",
    "codellama:7b": "codellama/CodeLlama-7b-hf",
    "codellama:13b": "codellama/CodeLlama-13b-hf",
    "codellama:34b": "codellama/CodeLlama-34b-hf",
    # Mistral
    "mistral": "mistralai/Mistral-7B-v0.3",
    "mistral:7b": "mistralai/Mistral-7B-v0.3",
    "mixtral": "mistralai/Mixtral-8x7B-v0.1",
    "mixtral:8x7b": "mistralai/Mixtral-8x7B-v0.1",
    # Phi
    "phi3": "microsoft/Phi-3-mini-4k-instruct",
    "phi3:mini": "microsoft/Phi-3-mini-4k-instruct",
    "phi3:medium": "microsoft/Phi-3-medium-4k-instruct",
    "phi4": "microsoft/phi-4",
    # Gemma
    "gemma2": "google/gemma-2-9b",
    "gemma2:2b": "google/gemma-2-2b",
    "gemma2:9b": "google/gemma-2-9b",
    "gemma2:27b": "google/gemma-2-27b",
    "gemma": "google/gemma-7b",
    "gemma:7b": "google/gemma-7b",
    "gemma:2b": "google/gemma-2b",
    # Qwen
    "qwen2.5": "Qwen/Qwen2.5-7B",
    "qwen2.5:0.5b": "Qwen/Qwen2.5-0.5B",
    "qwen2.5:1.5b": "Qwen/Qwen2.5-1.5B",
    "qwen2.5:3b": "Qwen/Qwen2.5-3B",
    "qwen2.5:7b": "Qwen/Qwen2.5-7B",
    "qwen2.5:14b": "Qwen/Qwen2.5-14B",
    "qwen2.5:32b": "Qwen/Qwen2.5-32B",
    "qwen2.5:72b": "Qwen/Qwen2.5-72B",
    "qwen2": "Qwen/Qwen2-7B",
    "qwen2:7b": "Qwen/Qwen2-7B",
    "qwen2:72b": "Qwen/Qwen2-72B",
    # DeepSeek
    "deepseek-r1": "deepseek-ai/DeepSeek-R1",
    "deepseek-r1:1.5b": "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
    "deepseek-r1:7b": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "deepseek-r1:8b": "deepseek-ai/DeepSeek-R1-Distill-Llama-8B",
    "deepseek-r1:14b": "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B",
    "deepseek-r1:32b": "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
    "deepseek-r1:70b": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
    "deepseek-coder-v2": "deepseek-ai/DeepSeek-Coder-V2-Lite-Base",
    # LFM
    "lfm-2.5": "LiquidAI/LFM-2.5-1.2B",
    # Granite
    "granite3.1-dense": "ibm-granite/granite-3.1-8b-base",
    "granite3.1-dense:2b": "ibm-granite/granite-3.1-2b-base",
    "granite3.1-dense:8b": "ibm-granite/granite-3.1-8b-base",
    # StarCoder
    "starcoder2": "bigcode/starcoder2-7b",
    "starcoder2:3b": "bigcode/starcoder2-3b",
    "starcoder2:7b": "bigcode/starcoder2-7b",
    "starcoder2:15b": "bigcode/starcoder2-15b",
}

# Model family substrings — order matters: longer/more-specific names MUST
# come before their shorter prefixes (e.g. "codellama" before "llama",
# "mixtral" before "mistral") to prevent partial matches.
_FAMILY_SUBSTRINGS: list[tuple[str, str]] = [
    ("codellama", "codellama"),
    ("command-r", "command-r"),
    ("deepseek", "deepseek"),
    ("starcoder", "starcoder"),
    ("internlm", "internlm"),
    ("mixtral", "mixtral"),
    ("mistral", "mistral"),
    ("granite", "granite"),
    ("falcon", "falcon"),
    ("gemma", "gemma"),
    ("llama", "llama"),
    ("mamba", "mamba"),
    ("qwen", "qwen"),
    ("rwkv", "rwkv"),
    ("phi", "phi"),
    ("lfm", "lfm"),
    ("gpt2", "gpt2"),
]

# Regex for parameter-count strings such as "7B", "1.2B", "0.5B".
_SIZE_RE = re.compile(r"(\d+\.?\d*)\s*[bB]\b")

# Regex for Ollama hf.co/ tag pattern.
_OLLAMA_HF_TAG_RE = re.compile(
    r"hf\.co/([^/]+/[^:]+?)(?:-GGUF|-gguf)?(?::(.+))?$"
)

# Quantization labels that require separator context to avoid false positives
# like "int4" matching inside "point4".
_QUANT_LABEL_RE = re.compile(
    r"(?:^|[-_./])"
    r"(4bit|8bit|int4|int8|gptq|awq|bnb|exl2|eetq|fp8|fp4)"
    r"(?:$|[-_./])",
    re.IGNORECASE,
)

# GGUF quant tags such as "Q4_K_M", "Q8_0".
_GGUF_QUANT_RE = re.compile(r"\b(Q\d+_\w+)\b")

# HuggingFace cache directory format: models--org--name
_HF_CACHE_RE = re.compile(r"^models--(.+?)--(.+)$")


# ---------------------------------------------------------------------------
# ModelInfo
# ---------------------------------------------------------------------------


class ModelInfo:
    """Rich model metadata resolved from any identifier."""

    __slots__ = (
        "original_id",
        "source",
        "hf_id",
        "ollama_tag",
        "mlx_id",
        "local_path",
        "format",
        "family",
        "parameter_size",
        "quantization",
        "capabilities",
        "errors",
    )

    def __init__(self) -> None:
        self.original_id: str = ""
        self.source: str = ""
        self.hf_id: Optional[str] = None
        self.ollama_tag: Optional[str] = None
        self.mlx_id: Optional[str] = None
        self.local_path: Optional[str] = None
        self.format: str = "unknown"
        self.family: str = ""
        self.parameter_size: str = ""
        self.quantization: Optional[str] = None
        self.capabilities: set[str] = set()
        self.errors: list[str] = []

    def to_dict(self) -> dict:
        return {
            "original_id": self.original_id,
            "source": self.source,
            "hf_id": self.hf_id,
            "ollama_tag": self.ollama_tag,
            "mlx_id": self.mlx_id,
            "local_path": self.local_path,
            "format": self.format,
            "family": self.family,
            "parameter_size": self.parameter_size,
            "quantization": self.quantization,
            "capabilities": sorted(self.capabilities),
            "errors": self.errors,
        }

    def __repr__(self) -> str:
        parts = [f"ModelInfo(original_id={self.original_id!r}"]
        if self.source:
            parts.append(f"source={self.source!r}")
        if self.hf_id:
            parts.append(f"hf_id={self.hf_id!r}")
        if self.family:
            parts.append(f"family={self.family!r}")
        if self.parameter_size:
            parts.append(f"size={self.parameter_size!r}")
        if self.quantization:
            parts.append(f"quant={self.quantization!r}")
        parts.append(f"caps={sorted(self.capabilities)}")
        return ", ".join(parts) + ")"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_mlx_available: Optional[bool] = None


def _is_mlx_available() -> bool:
    """Return True if the MLX framework can be imported (result is cached)."""
    global _mlx_available
    if _mlx_available is None:
        try:
            import mlx  # noqa: F401

            _mlx_available = True
        except ImportError:
            _mlx_available = False
    return _mlx_available


def _extract_family(text: str) -> str:
    """Extract model family from any identifier string.

    Uses ordered substring matching so that more specific names
    (e.g. "codellama") are checked before shorter prefixes ("llama").
    """
    lower = text.lower()
    for substring, family in _FAMILY_SUBSTRINGS:
        if substring in lower:
            return family
    return ""


def _extract_parameter_size(text: str) -> str:
    """Extract parameter-count string (e.g. "7B") from an identifier."""
    match = _SIZE_RE.search(text)
    return match.group(0).upper() if match else ""


def _extract_quantization(text: str) -> Optional[str]:
    """Extract quantization level from an identifier string.

    Uses separator-aware matching to avoid false positives (e.g. "int4"
    inside "point4" will NOT match).
    """
    m = _QUANT_LABEL_RE.search(text)
    if m:
        raw = m.group(1).lower()
        if raw in ("int4", "fp4"):
            return "4bit"
        if raw in ("int8", "fp8"):
            return "8bit"
        return raw
    m = _GGUF_QUANT_RE.search(text)
    if m:
        return m.group(1)
    return None


def _lookup_known_ollama(tag: str) -> Optional[str]:
    """Look up a known Ollama tag in the static mapping (case-insensitive)."""
    key = tag.lower().strip()

    # Exact match
    if key in _KNOWN_OLLAMA_HF_MAP:
        return _KNOWN_OLLAMA_HF_MAP[key]

    # Strip ":latest" and retry
    if key.endswith(":latest"):
        base = key[: -len(":latest")]
        if base in _KNOWN_OLLAMA_HF_MAP:
            return _KNOWN_OLLAMA_HF_MAP[base]

    return None


# ---------------------------------------------------------------------------
# Source detection
# ---------------------------------------------------------------------------


def _detect_source(model_id: str) -> str:
    """Heuristic source detection from model identifier format."""
    # Absolute paths are always local (even if the path doesn't exist yet)
    if model_id.startswith("/"):
        return "local_path"
    # Existing relative paths
    if os.path.exists(model_id):
        return "local_path"
    # Ollama hf.co/ shorthand
    if model_id.startswith("hf.co/") or model_id.startswith("huggingface.co/"):
        return "ollama"
    # MLX community namespace
    if model_id.startswith("mlx-community/"):
        return "mlx"
    # org/model -> HuggingFace
    if "/" in model_id:
        return "huggingface"
    # Bare names (llama3.2, mistral, phi4) -> Ollama
    return "ollama"


# ---------------------------------------------------------------------------
# Source-specific resolvers
# ---------------------------------------------------------------------------


def _resolve_ollama(info: ModelInfo, model_id: str) -> None:
    """Resolve an Ollama model tag."""
    info.ollama_tag = model_id
    info.format = "gguf"

    # -- 1. Parse hf.co/Org/Model-GGUF:Quant  --
    hf_match = _OLLAMA_HF_TAG_RE.match(model_id)
    if hf_match:
        raw_hf = hf_match.group(1)
        info.quantization = hf_match.group(2)
        # Strip trailing -GGUF / quant suffixes to recover the base model ID
        base = re.sub(r"-GGUF$|-gguf$", "", raw_hf)
        base = re.sub(r"-\d+bit$", "", base)
        info.hf_id = base

    # -- 2. Try Ollama /api/show for authoritative metadata --
    try:
        payload = json.dumps({"name": model_id}).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/show",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            details = data.get("details", {})

            parent = details.get("parent_model", "")
            if parent and "/" in parent:
                info.hf_id = parent

            info.family = details.get("family", "")
            info.parameter_size = details.get("parameter_size", "")
            info.quantization = info.quantization or details.get(
                "quantization_level", ""
            )

            # Some modelfiles reference a HF repo in the FROM line
            modelfile = data.get("modelfile", "")
            from_match = re.search(r"FROM\s+(\S+/\S+)", modelfile)
            if from_match and not info.hf_id:
                info.hf_id = from_match.group(1)

        logger.debug("Ollama /api/show succeeded for '%s'", model_id)
    except Exception:
        logger.debug(
            "Ollama /api/show unavailable for '%s'; using heuristics", model_id
        )

    # -- 3. Fallback: static known-mapping table --
    if not info.hf_id:
        known = _lookup_known_ollama(model_id)
        if known:
            info.hf_id = known
            logger.debug(
                "Resolved '%s' via known mapping -> '%s'", model_id, known
            )

    # -- 4. Fill in blanks from the identifier or resolved HF ID --
    if not info.family:
        info.family = _extract_family(model_id)
    if not info.parameter_size:
        info.parameter_size = _extract_parameter_size(model_id)
        # Also try the resolved HF ID (e.g. "meta-llama/Llama-3.2-1B" -> "1B")
        if not info.parameter_size and info.hf_id:
            info.parameter_size = _extract_parameter_size(info.hf_id)
    if not info.quantization:
        info.quantization = _extract_quantization(model_id)


def _resolve_huggingface(info: ModelInfo, model_id: str) -> None:
    """Resolve a HuggingFace model ID (org/name format)."""
    if "/" not in model_id:
        return

    info.hf_id = model_id
    info.format = "safetensors"  # default assumption for HF models

    # Detect if this is itself an MLX-community repo
    if model_id.startswith("mlx-community/"):
        info.mlx_id = model_id
        info.format = "mlx"

    name = model_id.split("/")[-1]
    info.family = _extract_family(name)
    info.parameter_size = _extract_parameter_size(name)
    info.quantization = _extract_quantization(name)


def _resolve_mlx(info: ModelInfo, model_id: str) -> None:
    """Resolve an MLX community model ID."""
    info.mlx_id = model_id
    info.hf_id = model_id  # MLX repos are loadable as HF repos
    info.format = "mlx"

    name = model_id.split("/")[-1]
    info.family = _extract_family(name)
    info.parameter_size = _extract_parameter_size(name)
    info.quantization = _extract_quantization(name)


def _resolve_local(info: ModelInfo, model_id: str) -> None:
    """Resolve a local filesystem path."""
    info.local_path = model_id
    basename = os.path.basename(model_id.rstrip(os.sep))

    # -- Single file --
    if os.path.isfile(model_id):
        ext = os.path.splitext(model_id)[1].lower()
        format_map = {
            ".gguf": "gguf",
            ".safetensors": "safetensors",
            ".bin": "bin",
        }
        info.format = format_map.get(ext, "unknown")

    # -- Directory --
    elif os.path.isdir(model_id):
        try:
            entries = os.listdir(model_id)
        except OSError as exc:
            info.errors.append(f"Cannot list directory: {exc}")
            entries = []

        # Detect format from file extensions (priority order)
        if any(f.endswith(".safetensors") for f in entries):
            info.format = "safetensors"
        elif any(f.endswith(".gguf") for f in entries):
            info.format = "gguf"
        elif any(f.endswith(".npz") or f.endswith(".mlx") for f in entries):
            info.format = "mlx"
        elif any(f.endswith(".bin") for f in entries):
            info.format = "bin"

        # Read config.json for model metadata
        config_path = os.path.join(model_id, "config.json")
        if os.path.isfile(config_path):
            try:
                with open(config_path) as fh:
                    config = json.load(fh)
                info.family = config.get("model_type", "")
                hf_name = config.get("_name_or_path", "")
                if hf_name and "/" in hf_name:
                    info.hf_id = hf_name
            except (OSError, json.JSONDecodeError) as exc:
                logger.debug(
                    "Failed to read config.json at '%s': %s", config_path, exc
                )

    # -- Detect HuggingFace cache directory format: models--org--name --
    if not info.hf_id:
        hf_cache_match = _HF_CACHE_RE.match(basename)
        if hf_cache_match:
            info.hf_id = (
                f"{hf_cache_match.group(1)}/{hf_cache_match.group(2)}"
            )

    # Supplement from basename if config.json didn't provide values
    if not info.family:
        info.family = _extract_family(basename)
        # Also try the resolved HF ID
        if not info.family and info.hf_id:
            info.family = _extract_family(info.hf_id)
    if not info.parameter_size:
        info.parameter_size = _extract_parameter_size(basename)
        if not info.parameter_size and info.hf_id:
            info.parameter_size = _extract_parameter_size(info.hf_id)


# ---------------------------------------------------------------------------
# Capability computation
# ---------------------------------------------------------------------------


def _compute_capabilities(info: ModelInfo) -> None:
    """Populate ``info.capabilities`` based on format and metadata."""
    caps: set[str] = {"inference"}

    if info.format in ("safetensors", "bin"):
        caps.add("training")
        caps.add("merge")
    elif info.format == "mlx":
        caps.add("training")  # MLX LoRA fine-tuning
        caps.add("merge")  # mlx_lm.fuse
    elif info.format == "gguf":
        # GGUF weights cannot be fine-tuned or merged directly, but we
        # can redirect to the original HuggingFace model.
        if info.hf_id:
            caps.add("training_via_hf")
            caps.add("merge_via_hf")

    info.capabilities = caps


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_model(model_id: str, source: str = "auto") -> ModelInfo:
    """Resolve any model identifier into rich :class:`ModelInfo`.

    Args:
        model_id: Ollama tag, HuggingFace ID, MLX ID, or local path.
        source: Hint — ``"ollama"``, ``"huggingface"``, ``"mlx"``,
                ``"local_path"``, or ``"auto"`` (detect heuristically).

    Returns:
        A :class:`ModelInfo` instance with all available metadata.
    """
    info = ModelInfo()

    if not model_id or not isinstance(model_id, str):
        info.errors.append("Empty or invalid model identifier")
        return info

    model_id = model_id.strip()
    info.original_id = model_id

    if source == "auto":
        source = _detect_source(model_id)
    info.source = source

    _RESOLVERS = {
        "ollama": _resolve_ollama,
        "huggingface": _resolve_huggingface,
        "mlx": _resolve_mlx,
        "local_path": _resolve_local,
    }

    resolver = _RESOLVERS.get(source)
    if resolver:
        resolver(info, model_id)
    else:
        # Unknown source — try HuggingFace, then Ollama
        _resolve_huggingface(info, model_id)
        if not info.hf_id:
            _resolve_ollama(info, model_id)

    _compute_capabilities(info)
    return info


def resolve_for_training(
    model_id: str, source: str = "auto"
) -> tuple[str, str, list[str]]:
    """Resolve a model for training.

    Returns:
        ``(resolved_id, framework, warnings)`` where *framework* is
        ``"mlx"``, ``"pytorch"``, or ``"unknown"``.
    """
    info = resolve_model(model_id, source)
    warnings: list[str] = list(info.errors)

    # -- Ollama source: need HF ID for training weights --
    if info.source == "ollama":
        if info.hf_id:
            warnings.append(
                f"Ollama model '{model_id}' resolved to HuggingFace ID "
                f"'{info.hf_id}'. Training will use the HuggingFace model "
                f"(full-precision weights required)."
            )
            fw = "mlx" if _is_mlx_available() else "pytorch"
            return info.hf_id, fw, warnings

        warnings.append(
            f"Cannot resolve Ollama model '{model_id}' to a HuggingFace "
            f"model ID. Training requires a HuggingFace model ID "
            f"(e.g., 'meta-llama/Llama-3.2-1B') or a local model path. "
            f"Set model_name in the block config."
        )
        return "", "unknown", warnings

    # -- MLX source --
    if info.source == "mlx" or info.format == "mlx":
        if _is_mlx_available():
            return model_id, "mlx", warnings
        if info.hf_id and info.hf_id != model_id:
            warnings.append("MLX not available. Falling back to PyTorch.")
            return info.hf_id, "pytorch", warnings
        warnings.append(
            "MLX framework is not installed and no PyTorch-compatible "
            "model ID could be determined."
        )
        return model_id, "unknown", warnings

    # -- Local path --
    if info.source == "local_path":
        if info.format == "mlx" and _is_mlx_available():
            return model_id, "mlx", warnings
        return model_id, "pytorch", warnings

    # -- HuggingFace or other --
    fw = "mlx" if _is_mlx_available() else "pytorch"
    return model_id, fw, warnings


def resolve_for_merge(
    model_id: str, source: str = "auto"
) -> tuple[str, list[str]]:
    """Resolve a model for merging (mergekit).

    Returns:
        ``(resolved_hf_id_or_path, warnings)``.
    """
    info = resolve_model(model_id, source)
    warnings: list[str] = list(info.errors)

    if info.source == "ollama":
        if info.hf_id:
            warnings.append(
                f"Ollama model '{model_id}' resolved to HuggingFace ID "
                f"'{info.hf_id}' for merging."
            )
            return info.hf_id, warnings

        warnings.append(
            f"Cannot resolve Ollama model '{model_id}' to a HuggingFace "
            f"model ID. Merging requires HuggingFace model IDs or local "
            f"model paths."
        )
        return "", warnings

    if info.hf_id:
        return info.hf_id, warnings
    if info.local_path:
        return info.local_path, warnings

    return model_id, warnings


def validate_for_framework(
    model_id: str, framework: str, source: str = "auto"
) -> tuple[bool, list[str]]:
    """Check whether *model_id* can be used with *framework*.

    Args:
        model_id: Any model identifier.
        framework: ``"ollama"``, ``"mlx"``, ``"pytorch"``, or ``"mergekit"``.
        source: Source hint (see :func:`resolve_model`).

    Returns:
        ``(is_valid, issues)`` — *is_valid* is ``False`` when any issue is
        a hard blocker.
    """
    info = resolve_model(model_id, source)
    issues: list[str] = list(info.errors)

    if framework == "ollama":
        if info.source == "local_path" and info.format not in (
            "gguf",
            "unknown",
        ):
            issues.append(
                f"Ollama requires GGUF format; this model uses "
                f"{info.format}."
            )
            return False, issues
        return len(issues) == 0, issues

    if framework == "mlx":
        if not _is_mlx_available():
            issues.append("MLX framework is not installed.")
            return False, issues
        if info.format == "gguf":
            issues.append(
                "MLX cannot directly load GGUF models. "
                "Use the HuggingFace variant instead."
            )
            return False, issues
        return len(issues) == 0, issues

    if framework == "pytorch":
        if info.format == "gguf":
            if info.hf_id:
                issues.append(
                    f"GGUF model will be loaded via HuggingFace ID "
                    f"'{info.hf_id}'."
                )
            else:
                issues.append(
                    "PyTorch cannot load GGUF models directly. "
                    "Provide a HuggingFace model ID."
                )
                return False, issues
        if info.format == "mlx":
            issues.append(
                "PyTorch cannot load MLX-format models directly."
            )
            return False, issues
        return len(issues) == 0, issues

    if framework == "mergekit":
        if info.format == "gguf":
            if not info.hf_id:
                issues.append(
                    "mergekit requires HuggingFace model IDs or local "
                    "safetensors paths."
                )
                return False, issues
            issues.append(
                f"GGUF model resolved to HuggingFace ID '{info.hf_id}' "
                f"for merging."
            )
        if info.format == "mlx":
            issues.append("mergekit does not support MLX-format models.")
            return False, issues
        return len(issues) == 0, issues

    issues.append(f"Unknown framework '{framework}'.")
    return False, issues
