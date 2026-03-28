"""Export dependency resolution — single backend source of truth for block pip deps.

Maps block type IDs to the pip packages they need at runtime.  This mirrors
the frontend's ``BLOCK_DEPENDENCIES`` map (in ``block-dependencies.ts``) so
the Jupyter/Python export can generate accurate ``pip install`` cells without
scanning the filesystem (no block has its own ``requirements.txt``).

Maintenance contract: when a new block is added or a block's dependencies
change, update **both** this file and ``frontend/src/lib/block-dependencies.ts``.

The map is intentionally kept flat and simple — one dict, alphabetically
sorted by block type.  No inheritance, no wildcards, no scanning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .planner_models import ExecutionPlan

# Packages always included in every generated requirements file.
BASE_DEPENDENCIES: list[str] = ["numpy", "tqdm", "torch"]

# Maps block type → pip packages required at runtime.
# Mirrors frontend/src/lib/block-dependencies.ts exactly.
BLOCK_DEPENDENCIES: dict[str, list[str]] = {
    # ── Source / External ──
    "huggingface_loader": ["datasets", "huggingface_hub"],
    "huggingface_model": ["transformers", "huggingface_hub", "accelerate"],
    "local_file_loader": ["pandas", "pyarrow"],
    "api_data_fetcher": ["requests", "aiohttp"],
    "web_scraper": ["beautifulsoup4", "requests"],
    "sql_query": ["sqlalchemy"],
    "document_ingestion": ["pypdf", "python-docx"],
    "synthetic_data_gen": ["faker"],
    "text_input": [],
    "config_builder": ["pyyaml"],
    "config_file_loader": ["pyyaml", "toml"],
    # ── Data / Transform ──
    "filter_sample": ["pandas"],
    "column_transform": ["pandas"],
    "data_augmentation": ["nlpaug"],
    "train_val_test_split": ["scikit-learn", "pandas"],
    "data_preview": ["pandas"],
    "data_merger": ["pandas"],
    "text_chunker": ["langchain-text-splitters"],
    "text_concatenator": [],
    "prompt_template": ["jinja2"],
    # ── Training ──
    "lora_finetuning": ["peft", "transformers", "torch", "datasets", "accelerate", "bitsandbytes"],
    "qlora_finetuning": ["peft", "transformers", "torch", "datasets", "accelerate", "bitsandbytes"],
    "full_finetuning": ["transformers", "torch", "datasets", "accelerate"],
    "dpo_alignment": ["trl", "transformers", "torch", "datasets"],
    "rlhf_ppo": ["trl", "transformers", "torch", "datasets"],
    "distillation": ["transformers", "torch"],
    "curriculum_training": ["transformers", "torch", "datasets"],
    "reward_model_trainer": ["trl", "transformers", "torch"],
    "continued_pretraining": ["transformers", "torch", "datasets", "accelerate"],
    "hyperparameter_sweep": ["optuna", "transformers", "torch"],
    "checkpoint_selector": [],
    # ── Model / Inference ──
    "llm_inference": ["transformers", "torch"],
    "quantize_model": ["auto-gptq", "transformers", "torch"],
    "reranker": ["sentence-transformers", "torch"],
    "slerp_merge": ["mergekit"],
    "ties_merge": ["mergekit"],
    "dare_merge": ["mergekit"],
    "frankenmerge": ["mergekit"],
    "mergekit_merge": ["mergekit"],
    # ── Evaluate / Metrics ──
    "mmlu_eval": ["lm-eval"],
    "lm_eval_harness": ["lm-eval"],
    "human_eval": ["human-eval"],
    "toxicity_eval": ["detoxify"],
    "factuality_checker": ["transformers", "torch"],
    "custom_eval": [],
    "results_formatter": ["pandas"],
    "experiment_logger": [],
    # ── Embedding ──
    "vector_store_build": ["chromadb", "sentence-transformers"],
    "embedding_generator": ["sentence-transformers", "torch"],
    "embedding_similarity_search": ["faiss-cpu", "numpy"],
    "embedding_clustering": ["scikit-learn", "numpy"],
    "embedding_visualizer": ["matplotlib", "scikit-learn"],
    # ── Agents ──
    "retrieval_agent": ["langchain", "chromadb"],
    "agent_orchestrator": ["langchain"],
    "agent_evaluator": ["langchain"],
    "chain_of_thought": [],
    "code_agent": [],
    "multi_agent_debate": [],
    "tool_registry": [],
    "agent_memory": [],
    "agent_text_bridge": [],
    # ── Utilities / Flow ──
    "conditional_branch": [],
    "loop_iterator": [],
    "aggregator": [],
    "parallel_fan_out": [],
    "python_runner": [],
    "artifact_viewer": [],
    # ── Interventions ──
    "human_review_gate": [],
    "notification_hub": ["requests"],
    "ab_split_test": [],
    "quality_gate": [],
    "rollback_point": [],
    "agentic_review_loop": ["transformers", "torch"],
    # ── Save ──
    "data_export": ["pandas", "pyarrow", "pyyaml"],
    "save_pdf": ["reportlab"],
    "save_model": ["safetensors", "torch"],
    "save_embeddings": ["numpy", "faiss-cpu"],
}


def collect_pip_dependencies_for_plan(plan: ExecutionPlan) -> list[str]:
    """Collect all pip dependencies for blocks in an ExecutionPlan.

    Uses the authoritative ``BLOCK_DEPENDENCIES`` map.  Includes base
    dependencies and deduplicates.  Returns a sorted list.
    """
    deps: set[str] = set(BASE_DEPENDENCIES)
    for node_id in plan.execution_order:
        resolved = plan.nodes.get(node_id)
        if not resolved:
            continue
        block_deps = BLOCK_DEPENDENCIES.get(resolved.block_type)
        if block_deps:
            deps.update(block_deps)
    return sorted(deps, key=str.lower)


def collect_pip_dependencies_for_block_types(block_types: list[str]) -> list[str]:
    """Collect all pip dependencies for a list of block types.

    Used by the export endpoint when no ExecutionPlan is available.
    """
    deps: set[str] = set(BASE_DEPENDENCIES)
    for bt in block_types:
        block_deps = BLOCK_DEPENDENCIES.get(bt)
        if block_deps:
            deps.update(block_deps)
    return sorted(deps, key=str.lower)
