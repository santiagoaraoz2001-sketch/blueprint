"""Block aliases and config migrations — single source of truth.

This module contains lightweight, import-free data definitions shared by
the main executor, partial executor, and subprocess block worker.

No heavy imports allowed here — this module must remain loadable in the
subprocess worker without pulling in SQLAlchemy, FastAPI, etc.
"""

import re

# Path safety: block types must be simple identifiers (letters, digits, underscore)
SAFE_BLOCK_TYPE = re.compile(r'^[a-zA-Z0-9_]+$')

# Backward-compat aliases for renamed blocks.
# Key = old block type, Value = canonical block type.
BLOCK_ALIASES: dict[str, str] = {
    "model_prompt": "llm_inference",
    "huggingface_dataset_loader": "huggingface_loader",
    "huggingface_model": "huggingface_model_loader",
    "model_loader": "model_selector",
    "data_exporter": "data_export",
    "results_exporter": "data_export",
    # Block consolidation aliases
    "debate_composite": "multi_agent_debate",
    "checkpoint_gate": "quality_gate",
    "notification_sender": "notification_hub",
    "manual_review": "human_review_gate",
    "save_csv": "data_export",
    "save_json": "data_export",
    "save_parquet": "data_export",
    "save_txt": "data_export",
    "save_yaml": "data_export",
    "save_local": "data_export",
    # Deprecated inference blocks → llm_inference
    "batch_inference": "llm_inference",
    "few_shot_prompting": "llm_inference",
    "text_translator": "llm_inference",
    "text_classifier": "llm_inference",
    "streaming_server": "llm_inference",
    "text_summarizer": "llm_inference",
    "structured_output": "llm_inference",
    "function_calling": "llm_inference",
    "chat_completion": "llm_inference",
    # Deprecated model blocks → model_selector
    "gguf_model": "model_selector",
    "mlx_model": "model_selector",
    "ollama_model": "model_selector",
}

# Config defaults injected when an aliased block resolves to its new type.
# This ensures saved workflows that used the old block type still work correctly.
CONFIG_MIGRATIONS: dict[str, dict[str, object]] = {
    "save_csv": {"format": "csv"},
    "save_json": {"format": "json"},
    "save_parquet": {"format": "parquet"},
    "save_txt": {"format": "txt"},
    "save_yaml": {"format": "yaml"},
    "save_local": {"format": "auto"},
}
