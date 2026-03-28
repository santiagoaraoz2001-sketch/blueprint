"""
Dry-Run Simulator & Resource Estimator.

Analyses a validated ExecutionPlan to predict viability, resource requirements,
and runtime class *without* executing anything.  Reuses the planner and
capability-detection logic so there is no duplicated graph traversal.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

ConfidenceLevel = Literal["high", "medium", "low"]
DurationClass = Literal["seconds", "minutes", "hours"]


@dataclass(frozen=True)
class NodeEstimate:
    estimated_memory_mb: int
    estimated_duration_class: DurationClass
    confidence: ConfidenceLevel


@dataclass(frozen=True)
class TotalEstimate:
    peak_memory_mb: int
    total_artifact_volume_mb: int
    runtime_class: DurationClass
    confidence: ConfidenceLevel


@dataclass(frozen=True)
class DryRunResult:
    viable: bool
    blockers: list[str]
    warnings: list[str]
    per_node_estimates: dict[str, NodeEstimate]
    total_estimate: TotalEstimate


# ---------------------------------------------------------------------------
# Block-category detection helpers
# ---------------------------------------------------------------------------

_TRAINING_BLOCK_TYPES = {
    "lora_finetuning",
    "full_finetuning",
    "hyperparameter_sweep",
    "dpo_training",
    "rl_training",
    "reward_model_training",
    "continued_pretraining",
}

_INFERENCE_BLOCK_TYPES = {
    "text_generation",
    "batch_inference",
    "rag_pipeline",
    "ab_test_inference",
    "chat_inference",
    "reranker",
    "classification_inference",
    "summarization",
    "translation",
    "question_answering",
}

_EVALUATION_BLOCK_TYPES = {
    "perplexity_eval",
    "benchmark_eval",
    "human_eval",
    "toxicity_eval",
    "mmlu_eval",
    "rouge_eval",
    "custom_eval",
    "bias_eval",
    "factuality_eval",
}

_FILE_OPERATION_TYPES = {
    "file_loader",
    "csv_loader",
    "json_loader",
    "dataset_loader",
    "file_writer",
    "csv_writer",
    "json_writer",
    "dataset_writer",
    "parquet_loader",
    "parquet_writer",
    "hf_dataset_loader",
}


def _block_category(block_type: str) -> str:
    """Return a coarse category for estimation purposes."""
    if block_type in _TRAINING_BLOCK_TYPES:
        return "training"
    if block_type in _INFERENCE_BLOCK_TYPES:
        return "inference"
    if block_type in _EVALUATION_BLOCK_TYPES:
        return "evaluation"
    if block_type in _FILE_OPERATION_TYPES:
        return "file_io"
    return "unknown"


# ---------------------------------------------------------------------------
# Model-size resolution — multi-strategy resolver
# ---------------------------------------------------------------------------

import json as _json
import os
import re
from pathlib import Path


def _guess_model_size_b(config: dict[str, Any]) -> float | None:
    """Resolve model size in billions using a layered strategy.

    Resolution order (first match wins):
      1. Explicit config fields: model_size_b, total_params
      2. HuggingFace config.json: read from local model path
      3. Model family registry: known sizes for common model families
      4. Regex pattern extraction: parse "7B", "3.2b", "500M" from name
      5. None (caller uses defaults)
    """
    # ── Strategy 1: Explicit config fields ──
    size = _from_explicit_config(config)
    if size is not None:
        return size

    # Gather model name from config
    model_name = _extract_model_name(config)
    if not model_name:
        return None

    # ── Strategy 2: Local HuggingFace config.json ──
    size = _from_local_config_json(model_name, config)
    if size is not None:
        return size

    # ── Strategy 3: Model family registry ──
    size = _from_model_family_registry(model_name)
    if size is not None:
        return size

    # ── Strategy 4: Regex pattern extraction ──
    size = _from_regex_pattern(model_name)
    if size is not None:
        return size

    return None


def _extract_model_name(config: dict[str, Any]) -> str:
    """Extract the best model name string from config."""
    for key in ("model_name", "model_path", "base_model", "model",
                "model_a", "model_b", "model_id", "checkpoint_dir"):
        val = config.get(key, "")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _from_explicit_config(config: dict[str, Any]) -> float | None:
    """Strategy 1: Check for explicit parameter count fields."""
    # Direct size in billions
    for key in ("model_size_b", "model_size_billions"):
        if key in config:
            try:
                return float(config[key])
            except (ValueError, TypeError):
                pass

    # Total parameter count (from previous runs or block metadata)
    for key in ("total_params", "num_parameters", "parameter_count"):
        if key in config:
            try:
                params = int(config[key])
                if params > 0:
                    return params / 1e9
            except (ValueError, TypeError):
                pass

    # Trainable params (for LoRA, gives a lower bound on total model size)
    # Not used directly — LoRA trainable params are << total params

    return None


def _from_local_config_json(model_name: str, config: dict[str, Any]) -> float | None:
    """Strategy 2: Read HuggingFace config.json from a local model path.

    HuggingFace models stored locally have a config.json with architecture
    details from which we can compute exact parameter counts.
    """
    # Check if model_name is a local path
    model_path = None

    # Direct path references
    for key in ("model_path", "model_name", "base_model", "checkpoint_dir"):
        val = config.get(key, "")
        if isinstance(val, str) and val.strip():
            candidate = Path(val.strip())
            if candidate.is_dir():
                model_path = candidate
                break
            # HuggingFace cache path
            if candidate.exists() and candidate.suffix == ".json":
                model_path = candidate.parent
                break

    if model_path is None:
        # Try HuggingFace cache directory
        hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
        if hf_cache.is_dir():
            # Convert org/model format to cache directory naming
            safe_name = model_name.replace("/", "--")
            for prefix in ("models--", ""):
                candidate = hf_cache / f"{prefix}{safe_name}"
                if candidate.is_dir():
                    # Look for the latest snapshot
                    snapshots = candidate / "snapshots"
                    if snapshots.is_dir():
                        # Get most recent snapshot
                        snapshot_dirs = sorted(
                            snapshots.iterdir(),
                            key=lambda p: p.stat().st_mtime if p.is_dir() else 0,
                            reverse=True,
                        )
                        for sd in snapshot_dirs:
                            if sd.is_dir() and (sd / "config.json").exists():
                                model_path = sd
                                break
                    break

    if model_path is None:
        return None

    config_file = model_path / "config.json"
    if not config_file.exists():
        return None

    try:
        with open(config_file) as f:
            model_config = _json.load(f)

        # Direct parameter count (best case)
        if "num_parameters" in model_config:
            return int(model_config["num_parameters"]) / 1e9

        # Compute from architecture dimensions
        return _compute_params_from_architecture(model_config)

    except Exception:
        return None


def _compute_params_from_architecture(config: dict) -> float | None:
    """Estimate parameter count from HuggingFace model architecture config.

    Standard transformer parameter count formula:
      vocab_embed = vocab_size * hidden_size
      per_layer = 4 * hidden_size^2 (attention) + 8 * hidden_size * intermediate_size (MLP) / 3
      total ≈ vocab_embed + num_layers * per_layer + hidden_size (final LN)

    Supports:
      - LlamaForCausalLM, MistralForCausalLM, Phi3ForCausalLM (GatedMLP)
      - GPT2LMHeadModel, GPTNeoXForCausalLM (standard MLP)
      - FalconForCausalLM, StableLmForCausalLM
      - Qwen2ForCausalLM, GemmaForCausalLM
    """
    hidden_size = config.get("hidden_size")
    num_layers = config.get("num_hidden_layers", config.get("n_layer"))
    vocab_size = config.get("vocab_size")

    if not all((hidden_size, num_layers, vocab_size)):
        return None

    try:
        h = int(hidden_size)
        n = int(num_layers)
        v = int(vocab_size)
    except (ValueError, TypeError):
        return None

    # Intermediate (FFN) size
    intermediate = config.get(
        "intermediate_size",
        config.get("n_inner", config.get("ffn_hidden_size", 4 * h)),
    )
    try:
        inter = int(intermediate)
    except (ValueError, TypeError):
        inter = 4 * h

    # Number of attention heads and key-value heads (for GQA)
    num_heads = config.get("num_attention_heads", config.get("n_head", h // 128))
    num_kv_heads = config.get("num_key_value_heads", num_heads)

    try:
        nh = int(num_heads)
        nkv = int(num_kv_heads)
    except (ValueError, TypeError):
        nh = h // 128
        nkv = nh

    head_dim = h // max(nh, 1)

    # Attention parameters: Q, K, V projections + output projection
    # Q: hidden_size → num_heads * head_dim
    # K: hidden_size → num_kv_heads * head_dim
    # V: hidden_size → num_kv_heads * head_dim
    # O: num_heads * head_dim → hidden_size
    attn_params = (
        h * nh * head_dim  # Q
        + h * nkv * head_dim  # K
        + h * nkv * head_dim  # V
        + nh * head_dim * h   # O
    )

    # MLP parameters
    # Standard: up (h → inter) + down (inter → h)
    # Gated (Llama/Mistral): gate (h → inter) + up (h → inter) + down (inter → h)
    model_type = config.get("model_type", "").lower()
    gated_types = {
        "llama", "mistral", "mixtral", "qwen2", "gemma", "gemma2",
        "phi3", "cohere", "starcoder2", "deepseek",
    }
    if model_type in gated_types:
        mlp_params = 3 * h * inter  # gate_proj + up_proj + down_proj
    else:
        mlp_params = 2 * h * inter  # up + down

    # Per-layer: attention + MLP + 2 layer norms (negligible but included)
    layer_params = attn_params + mlp_params + 2 * h

    # Total
    embed_params = v * h  # token embedding
    # Some models tie weights (share embed with LM head), others don't
    lm_head_params = v * h if not config.get("tie_word_embeddings", True) else 0
    final_ln = h  # final layer norm

    total = embed_params + n * layer_params + final_ln + lm_head_params

    return total / 1e9


# ---------------------------------------------------------------------------
# Model family registry
# ---------------------------------------------------------------------------

# Maps normalized model-name substrings to known sizes (billions).
# This covers models whose names don't follow the standard "XB" pattern.
_MODEL_FAMILY_REGISTRY: list[tuple[str, float]] = [
    # GPT-2 variants
    ("gpt2-xl", 1.5),
    ("gpt2-large", 0.774),
    ("gpt2-medium", 0.355),
    ("gpt2", 0.124),  # base GPT-2

    # Phi family
    ("phi-4", 14.0),
    ("phi-3.5-moe", 42.0),
    ("phi-3.5-mini", 3.8),
    ("phi-3-medium", 14.0),
    ("phi-3-small", 7.4),
    ("phi-3-mini", 3.8),
    ("phi-2", 2.7),
    ("phi-1.5", 1.3),
    ("phi-1", 1.3),

    # Gemma
    ("gemma-2-27b", 27.0),
    ("gemma-2-9b", 9.0),
    ("gemma-2-2b", 2.6),
    ("gemma-7b", 8.5),
    ("gemma-2b", 2.5),

    # Qwen
    ("qwen2.5-coder-32b", 32.0),
    ("qwen2.5-72b", 72.0),
    ("qwen2.5-32b", 32.0),
    ("qwen2.5-14b", 14.0),
    ("qwen2.5-7b", 7.0),
    ("qwen2.5-3b", 3.0),
    ("qwen2.5-1.5b", 1.5),
    ("qwen2.5-0.5b", 0.5),
    ("qwen2-72b", 72.0),
    ("qwen2-7b", 7.0),
    ("qwen2-1.5b", 1.5),
    ("qwen2-0.5b", 0.5),

    # Mistral / Mixtral
    ("mixtral-8x22b", 141.0),  # MoE total params
    ("mixtral-8x7b", 46.7),    # MoE total params
    ("mistral-large", 123.0),
    ("mistral-small", 22.0),
    ("mistral-nemo", 12.0),

    # BLOOM
    ("bloom-176b", 176.0),
    ("bloom-7b1", 7.1),
    ("bloom-3b", 3.0),
    ("bloom-1b7", 1.7),
    ("bloom-1b1", 1.1),
    ("bloom-560m", 0.56),

    # T5 variants
    ("flan-t5-xxl", 11.0),
    ("flan-t5-xl", 3.0),
    ("flan-t5-large", 0.78),
    ("flan-t5-base", 0.25),
    ("flan-t5-small", 0.08),
    ("t5-11b", 11.0),
    ("t5-3b", 3.0),
    ("t5-large", 0.77),
    ("t5-base", 0.22),
    ("t5-small", 0.06),

    # OPT
    ("opt-66b", 66.0),
    ("opt-30b", 30.0),
    ("opt-13b", 13.0),
    ("opt-6.7b", 6.7),
    ("opt-2.7b", 2.7),
    ("opt-1.3b", 1.3),
    ("opt-350m", 0.35),
    ("opt-125m", 0.125),

    # Falcon
    ("falcon-180b", 180.0),
    ("falcon-40b", 40.0),
    ("falcon-7b", 7.0),

    # StableLM
    ("stablelm-2-12b", 12.0),
    ("stablelm-2-1.6b", 1.6),
    ("stablelm-zephyr-3b", 3.0),

    # DeepSeek
    ("deepseek-v3", 685.0),  # MoE
    ("deepseek-v2.5", 236.0),
    ("deepseek-v2-lite", 16.0),
    ("deepseek-coder-v2", 236.0),
    ("deepseek-coder-33b", 33.0),
    ("deepseek-coder-6.7b", 6.7),
    ("deepseek-coder-1.3b", 1.3),

    # Cohere
    ("command-r-plus", 104.0),
    ("command-r", 35.0),

    # BERT (small but commonly used in eval/embedding)
    ("bert-large", 0.340),
    ("bert-base", 0.110),

    # Sentence transformers / cross-encoders
    ("all-mpnet-base-v2", 0.110),
    ("all-minilm-l6-v2", 0.023),
    ("ms-marco-minilm-l-6-v2", 0.023),
    ("bge-large-en-v1.5", 0.335),
    ("bge-base-en-v1.5", 0.110),
    ("e5-large-v2", 0.335),
    ("e5-base-v2", 0.110),
]


def _from_model_family_registry(model_name: str) -> float | None:
    """Strategy 3: Look up model in the known-models registry."""
    normalized = model_name.lower().replace("_", "-")
    # Strip org prefix (e.g. "meta-llama/" → "")
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]

    for pattern, size in _MODEL_FAMILY_REGISTRY:
        if pattern in normalized:
            return size

    return None


# ---------------------------------------------------------------------------
# Regex pattern extraction
# ---------------------------------------------------------------------------

# Matches patterns like: 7B, 3.2B, 70b, 1.5b, 0.5B, 500M, 125m, 1.8b
_SIZE_REGEX = re.compile(
    r"(?<![a-zA-Z0-9.])"     # Not preceded by alphanumeric or dot
    r"(\d+(?:\.\d+)?)"        # Number (integer or decimal)
    r"\s*"                     # Optional whitespace
    r"([bBmM])"               # Unit: B (billions) or M (millions)
    r"(?![a-zA-Z0-9])"        # Not followed by alphanumeric
)

# Matches "Nx" patterns for MoE: "8x7B", "8x22b"
_MOE_REGEX = re.compile(
    r"(\d+)\s*x\s*(\d+(?:\.\d+)?)\s*([bBmM])",
)


def _from_regex_pattern(model_name: str) -> float | None:
    """Strategy 4: Extract model size from naming patterns via regex."""
    # Check MoE pattern first (e.g. "8x7B")
    moe_match = _MOE_REGEX.search(model_name)
    if moe_match:
        n_experts = int(moe_match.group(1))
        expert_size = float(moe_match.group(2))
        unit = moe_match.group(3).lower()
        if unit == "b":
            return n_experts * expert_size
        elif unit == "m":
            return n_experts * expert_size / 1000
        return None

    # Standard size pattern
    matches = _SIZE_REGEX.findall(model_name)
    if not matches:
        return None

    # Pick the largest match (heuristic: model size is usually the biggest number)
    best_size_b = 0.0
    for num_str, unit in matches:
        try:
            value = float(num_str)
        except ValueError:
            continue

        if unit.lower() == "b":
            size_b = value
        elif unit.lower() == "m":
            size_b = value / 1000
        else:
            continue

        if size_b > best_size_b:
            best_size_b = size_b

    return best_size_b if best_size_b > 0 else None


# ---------------------------------------------------------------------------
# Estimation heuristics
# ---------------------------------------------------------------------------

def _estimate_training_memory_mb(config: dict[str, Any]) -> int:
    """Estimate peak memory for a training block (MB)."""
    model_size_b = _guess_model_size_b(config) or 7.0  # default 7B

    batch_size = int(config.get("batch_size", 4))
    grad_accum = int(config.get("gradient_accumulation_steps", 1))

    # Precision detection
    precision = str(config.get("precision", config.get("dtype", "float16"))).lower()
    if "int4" in precision or "4bit" in precision or "bnb_4bit" in precision:
        bytes_per_param = 1  # 4-bit → 0.5 bytes, but optimizer states ~double
    elif "int8" in precision or "8bit" in precision:
        bytes_per_param = 2
    elif "float32" in precision or "fp32" in precision:
        bytes_per_param = 4
    else:
        bytes_per_param = 2  # float16/bfloat16 default

    # model_size_b * 1e9 * bytes_per_param → bytes → MB
    # Multiply by batch_size factor (activation memory scales linearly)
    # For LoRA, actual trainable params are much smaller, but we still load full model
    base_mb = (model_size_b * 1e9 * bytes_per_param) / (1024 * 1024)
    # Activations + optimizer overhead: ~2x for Adam, scale with batch_size
    activation_factor = 1 + 0.3 * min(batch_size * grad_accum, 32)
    total_mb = base_mb * activation_factor

    return max(512, int(total_mb))


def _estimate_inference_memory_mb(config: dict[str, Any]) -> int:
    """Estimate peak memory for an inference block (MB)."""
    model_size_b = _guess_model_size_b(config) or 7.0

    context_length = int(config.get("max_tokens", config.get("max_seq_length", 2048)))
    # model_size * context_length * 2 bytes (KV cache overhead)
    model_mb = (model_size_b * 1e9 * 2) / (1024 * 1024)
    # KV cache: ~2 bytes per token per layer
    kv_cache_mb = (context_length * 2 * max(1, int(model_size_b * 4))) / (1024 * 1024)
    return max(256, int(model_mb + kv_cache_mb))


def _estimate_evaluation_memory_mb(config: dict[str, Any]) -> int:
    """Estimate memory for evaluation blocks (dataset_rows * model_memory)."""
    model_size_b = _guess_model_size_b(config) or 7.0
    dataset_rows = int(config.get("dataset_rows", config.get("num_samples", 1000)))
    # Base model memory + per-row overhead
    model_mb = (model_size_b * 1e9 * 2) / (1024 * 1024)
    # Rows contribute to batch memory — small per-row cost
    row_overhead_mb = dataset_rows * 0.01  # ~10KB per row
    return max(256, int(model_mb + row_overhead_mb))


def _estimate_file_io_memory_mb(config: dict[str, Any]) -> int:
    """Estimate memory for file I/O blocks."""
    # If we know artifact size, use it; otherwise default to 100MB
    artifact_mb = config.get("artifact_size_mb", 100)
    try:
        return max(64, int(float(artifact_mb) * 2))  # 2x for read buffer + processing
    except (ValueError, TypeError):
        return 200


def _estimate_duration_class(category: str, config: dict[str, Any]) -> DurationClass:
    """Guess the runtime bucket for a block."""
    if category == "training":
        epochs = int(config.get("epochs", config.get("num_epochs", 3)))
        model_size = _guess_model_size_b(config) or 7.0
        if model_size >= 30 or epochs >= 10:
            return "hours"
        if model_size >= 3 or epochs >= 3:
            return "minutes"
        return "minutes"
    if category == "inference":
        return "minutes"
    if category == "evaluation":
        return "minutes"
    if category == "file_io":
        return "seconds"
    return "seconds"


def _estimate_artifact_volume_mb(category: str, config: dict[str, Any]) -> int:
    """Estimate output artifact size for a single node."""
    if category == "training":
        model_size = _guess_model_size_b(config) or 7.0
        # LoRA adapters are small; full finetune = full model
        block_type = config.get("_block_type", "")
        if "lora" in block_type:
            return max(10, int(model_size * 50))  # ~50MB per B for LoRA adapters
        return max(100, int(model_size * 2000))  # ~2GB per B for full model
    if category == "inference":
        return 10  # output text/JSON
    if category == "evaluation":
        return 5  # metrics
    if category == "file_io":
        return int(config.get("artifact_size_mb", 100))
    return 10


# ---------------------------------------------------------------------------
# Historical run data
# ---------------------------------------------------------------------------

def _get_historical_estimates(
    block_type: str,
    config: dict[str, Any],
    run_history: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Look for matching historical runs and return averaged stats.

    Returns dict with 'avg_duration_s' and 'avg_memory_mb' or None.
    """
    if not run_history:
        return None

    # Filter runs for same block type
    matching = [r for r in run_history if r.get("block_type") == block_type]
    if not matching:
        return None

    # Take last 3 matching runs
    recent = matching[-3:]

    durations = [r["duration_seconds"] for r in recent if r.get("duration_seconds")]
    if not durations:
        return None

    avg_duration = sum(durations) / len(durations)

    # Duration class from average
    if avg_duration < 60:
        dur_class = "seconds"
    elif avg_duration < 3600:
        dur_class = "minutes"
    else:
        dur_class = "hours"

    result: dict[str, Any] = {
        "avg_duration_s": avg_duration,
        "duration_class": dur_class,
    }

    # Memory if available
    memories = [r["peak_memory_mb"] for r in recent if r.get("peak_memory_mb")]
    if memories:
        result["avg_memory_mb"] = int(sum(memories) / len(memories))

    return result


# ---------------------------------------------------------------------------
# Capability / dependency checks
# ---------------------------------------------------------------------------

def _check_capabilities(
    block_type: str,
    category: str,
    config: dict[str, Any],
    capabilities: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Check if the system can run this block. Returns (blockers, warnings)."""
    blockers: list[str] = []
    warnings: list[str] = []

    # Training blocks need torch or mlx
    if category == "training":
        has_torch = capabilities.get("torch", False)
        has_mlx = capabilities.get("mlx", False)
        prefer = config.get("prefer_framework", "auto")

        if prefer == "pytorch" and not has_torch:
            blockers.append(
                f"Block '{block_type}' requires PyTorch but it is not installed. "
                f"Install with: pip install torch"
            )
        elif prefer == "mlx" and not has_mlx:
            blockers.append(
                f"Block '{block_type}' requires MLX but it is not installed. "
                f"Install with: pip install mlx mlx-lm"
            )
        elif prefer == "auto" and not has_torch and not has_mlx:
            blockers.append(
                f"Block '{block_type}' requires PyTorch or MLX for training. "
                f"Install with: pip install torch  (or: pip install mlx mlx-lm)"
            )

    # Inference blocks may need specific providers
    if category == "inference":
        provider = config.get("provider", config.get("backend", ""))
        if provider == "ollama" and not capabilities.get("ollama", True):
            warnings.append(
                f"Block '{block_type}' uses Ollama — ensure the Ollama server is running"
            )

    # GPU memory warnings
    gpu_mem_mb = capabilities.get("gpu_memory_mb", 0)
    sys_mem_mb = capabilities.get("system_memory_mb", 16384)

    return blockers, warnings


# ---------------------------------------------------------------------------
# Main simulation entry point
# ---------------------------------------------------------------------------

def simulate(
    plan: Any,  # ExecutionPlan
    capabilities: dict[str, Any],
    run_history: list[dict[str, Any]] | None = None,
    registry: Any = None,
) -> DryRunResult:
    """Simulate execution of a validated plan and estimate resources.

    Args:
        plan: A frozen ExecutionPlan from the planner.
        capabilities: Dict of system capabilities (torch, mlx, gpu_memory_mb, etc.).
        run_history: Optional list of historical run records for the same
            block types, each with keys like block_type, duration_seconds,
            peak_memory_mb.
        registry: Optional block registry for looking up block metadata.

    Returns:
        DryRunResult with viability assessment and resource estimates.
    """
    all_blockers: list[str] = []
    all_warnings: list[str] = list(plan.warnings) if plan.warnings else []
    per_node: dict[str, NodeEstimate] = {}

    peak_memory_mb = 0
    total_artifact_mb = 0
    worst_duration: DurationClass = "seconds"
    lowest_confidence: ConfidenceLevel = "high"

    duration_rank = {"seconds": 0, "minutes": 1, "hours": 2}
    confidence_rank = {"high": 0, "medium": 1, "low": 2}

    for node_id in plan.execution_order:
        resolved = plan.nodes.get(node_id)
        if resolved is None:
            continue

        block_type = resolved.block_type
        config = dict(resolved.resolved_config)
        config["_block_type"] = block_type  # for internal heuristics
        category = _block_category(block_type)

        # ── Capability checks ──
        node_blockers, node_warnings = _check_capabilities(
            block_type, category, config, capabilities,
        )
        all_blockers.extend(node_blockers)
        all_warnings.extend(node_warnings)

        # ── Try historical data first ──
        historical = _get_historical_estimates(block_type, config, run_history)

        if historical:
            # Historical data available → high confidence
            mem_mb = historical.get("avg_memory_mb") or _estimate_memory_for_category(
                category, config,
            )
            dur_class: DurationClass = historical["duration_class"]
            confidence: ConfidenceLevel = "high"
        elif category != "unknown":
            # Heuristic estimation → medium confidence
            mem_mb = _estimate_memory_for_category(category, config)
            dur_class = _estimate_duration_class(category, config)
            confidence = "medium"
        else:
            # Unknown block type → low confidence with defaults
            mem_mb = 256
            dur_class = "seconds"
            confidence = "low"

        per_node[node_id] = NodeEstimate(
            estimated_memory_mb=mem_mb,
            estimated_duration_class=dur_class,
            confidence=confidence,
        )

        # Aggregate totals
        peak_memory_mb = max(peak_memory_mb, mem_mb)
        total_artifact_mb += _estimate_artifact_volume_mb(category, config)

        if duration_rank.get(dur_class, 0) > duration_rank.get(worst_duration, 0):
            worst_duration = dur_class
        if confidence_rank.get(confidence, 0) > confidence_rank.get(lowest_confidence, 0):
            lowest_confidence = confidence

    # Ensure sensible defaults for empty plans
    if not per_node:
        peak_memory_mb = 0
        total_artifact_mb = 0

    total = TotalEstimate(
        peak_memory_mb=peak_memory_mb,
        total_artifact_volume_mb=total_artifact_mb,
        runtime_class=worst_duration,
        confidence=lowest_confidence,
    )

    viable = len(all_blockers) == 0

    return DryRunResult(
        viable=viable,
        blockers=all_blockers,
        warnings=all_warnings,
        per_node_estimates=per_node,
        total_estimate=total,
    )


def _estimate_memory_for_category(category: str, config: dict[str, Any]) -> int:
    """Dispatch to the right memory estimator based on category."""
    if category == "training":
        return _estimate_training_memory_mb(config)
    if category == "inference":
        return _estimate_inference_memory_mb(config)
    if category == "evaluation":
        return _estimate_evaluation_memory_mb(config)
    if category == "file_io":
        return _estimate_file_io_memory_mb(config)
    return 256
