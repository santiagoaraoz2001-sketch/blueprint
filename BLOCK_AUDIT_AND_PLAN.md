# Blueprint Block Audit & Comprehensive Modification Plan

> Full audit of all 104 blocks across 8 categories. Every block was analyzed by reading its `run.py`, `block.yaml`, and frontend registry entry. For each: 5-10 workflows imagined, pain points identified, modification plan written.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Systemic Issues (Cross-Category)](#systemic-issues)
3. [Per-Category Findings Summary](#per-category-findings)
4. [Missing Blocks & New Categories](#missing-blocks)
5. [Implementation Priorities](#implementation-priorities)

---

## Executive Summary

### The Single Biggest Problem: Frontend-Backend Mismatches

**Over 70 of 104 blocks have mismatches between what the frontend UI shows and what the backend actually does.** These fall into 4 categories:

| Mismatch Type | Affected Blocks | Severity |
|---|---|---|
| **Config key names differ** (frontend sends `X`, backend reads `Y`) | ~40 blocks | CRITICAL -- user config has zero effect |
| **Input ports declared but never read** | ~25 blocks | HIGH -- wired connections are silently ignored |
| **Output ports declared but never saved** | ~20 blocks | HIGH -- downstream blocks receive nothing |
| **Config options listed but not implemented** | ~50 blocks | MEDIUM -- misleading UI promises |

### Scale of the Problem

- **66 of 104 blocks are missing `block.yaml`** files
- **14 of 23 inference blocks are demo-only** (no real LLM calls)
- **4 data blocks exist as backend code with no frontend registry entry** (gguf_model, huggingface_model, mlx_model, ollama_model)
- **Every merge block has at least one critical mismatch** (SLERP and DARE are fundamentally broken -- frontend config keys do not match backend)
- **No shared utilities exist** -- each block copies the same Ollama API call code, model resolution code, and file detection code

---

## Systemic Issues

### 1. Config Key Name Mismatches (CRITICAL)

These blocks have config fields where the frontend sends one key name but the backend reads a different one, meaning the user's configuration has **zero effect**:

| Block | Frontend Key | Backend Key | Impact |
|---|---|---|---|
| `slerp_merge` | `t` | `weight` | Interpolation slider does nothing |
| `dare_merge` | `drop_rate`, `rescale` | `weight`, `density` | Both config fields ignored |
| `ties_merge` | weight default `1.0` | weight default `0.5` | Wrong default behavior |
| `llm_inference` | `backend` | `provider` | Backend selection ignored |
| `batch_inference` | `batch_size` | (not read) | Batch size has no effect |
| `embedding_generator` | `column` | `text_column` | Column selection ignored |
| `reranker` | `doc_column` | `text_column` | Document column ignored |
| `conditional_branch` | `metric_key` | `field` | Condition field ignored |
| `aggregator` | `method` | `strategy` | Aggregation method ignored |
| `error_handler` | `retry_count` | `max_retries` | Retry count ignored |
| `parallel_fan_out` | `num_branches` | `num_chunks` | Branch count ignored |
| `multi_agent_debate` | `rounds` | `num_rounds` | Round count ignored |
| `chain_of_thought` | `num_steps` default `5` | `num_steps` default `3` | Wrong default |

### 2. Input Ports Declared But Never Read

| Block | Frontend Input | Status |
|---|---|---|
| `ab_comparator` | `model_a`, `model_b`, `model_c` | Never loaded -- block reads `dataset_a`, `dataset_b` |
| `factuality_checker` | `model` | Never loaded |
| `toxicity_eval` | `model` | Never loaded |
| `model_telemetry` | `dataset` | Never loaded -- uses synthetic text |
| `agent_memory` | `embedding_model`, `dataset` | Never loaded |
| `agent_evaluator` | `agent` | Never loaded |
| `tool_registry` | `config` (required!) | Never loaded |
| `chain_of_thought` | `dataset` | Never loaded -- reads `input` |
| `multi_agent_debate` | `dataset` | Never loaded -- reads `input` |
| `code_agent` | `dataset` | Never loaded -- reads `input` |
| `data_augmentation` | `model` | Never loaded |
| `web_scraper` | `model` | Never loaded |
| `vector_store_build` | `model` (embedding) | Never loaded -- uses ChromaDB default |
| `ties_merge` | `base` | Never loaded -- hardcodes model_a |
| `embedding_generator` | `model` (required!) | Never loaded |

### 3. Output Port ID Mismatches

| Block | Frontend Output IDs | Backend `save_output` IDs |
|---|---|---|
| `aggregator` | `output` | `dataset`, `metrics` |
| `conditional_branch` | `true_branch`, `false_branch` | `output_a`, `output_b` |
| `parallel_fan_out` | `out_1`, `out_2`, `out_3` | `dataset`, `chunks` |
| `error_handler` | `success` | `output` |
| `checkpoint_gate` | `output`, `fail` | `output`, `passed`, `metrics` |

### 4. Inconsistent File Format Conventions

Blocks save their output JSON as different filenames, causing downstream blocks to fail:

| Block | Saves As | Expected By Downstream |
|---|---|---|
| Most dataset blocks | `data.json` | `data.json` (works) |
| `document_ingestion` | `docs.json` | `data.json` (breaks) |
| `text_chunker` | `chunks.json` | `data.json` (breaks) |
| `vector_store_build` | reads `chunks.json` | only works after text_chunker |

**Solution**: All dataset blocks should save as `data.json`. Add a shared utility `find_dataset_file(path)` that checks for `data.json`, `docs.json`, `chunks.json`, then any `*.json`.

### 5. No Shared LLM Calling Utility

Every block that calls an LLM copies the same code. At least 15 blocks have independent `_call_ollama` functions. A shared utility should be created:

```
blocks/_shared/llm_utils.py:
  call_llm(backend, base_url, model_name, messages, temperature, max_tokens, api_key=None)
  resolve_model(model_input_data) -> (model_name, backend, base_url)

blocks/_shared/data_utils.py:
  find_dataset_file(directory_path) -> file_path
  load_dataset_rows(dataset_path) -> list[dict]
  save_dataset_rows(rows, output_dir) -> path
```

### 6. No Shared Model Resolution Utility

Each merge/training/inference block has its own model resolution logic. Some check `model_name`, some check `model_id`, some check `path`. A shared `resolve_model()` function should handle all cases.

### 7. `provider` vs `backend` Naming

Some blocks use `provider`, others use `backend` for the same concept. The frontend consistently uses `backend`. **All run.py files should standardize on `backend`.**

### 8. Missing `block.yaml` Files

66 of 104 blocks have no `block.yaml`. Every block should have one for backend block discovery consistency.

### 9. Missing `detail` Sections in Frontend

Almost no blocks have `detail` (tips, useCases, howItWorks) in the frontend registry. Adding these would significantly improve discoverability and usability.

### 10. Demo Mode Inconsistency

Some blocks have graceful demo fallbacks (custom_benchmark, human_eval), while others crash on missing dependencies (lm_eval_harness, mmlu_eval). All blocks should either have a demo fallback or a clear error message with install instructions.

---

## Per-Category Findings Summary

### Agents (9 blocks)
- **Critical**: Every block except retrieval_agent and agent_text_bridge has severe frontend-backend mismatches
- **agent_memory** is the worst: frontend promises vector store (ChromaDB/FAISS), backend is a JSON key-value file
- **agent_orchestrator** never saves an `agent` output despite declaring one
- All blocks are Ollama-only for LLM calls
- No shared LLM calling utility across agent blocks
- Only 2 of 9 have `block.yaml`

### Data (24 blocks)
- **api_data_fetcher**: Auth, retry, rate-limiting all declared in UI but none implemented
- **document_ingestion**: Opens PDFs as text files (broken), most config fields dead
- **filter_sample**: Only 2 of 5 filter methods implemented
- **vector_store_build**: Embedding model input is required but never used
- **text_chunker**: Saves as `chunks.json` breaking downstream expectations
- 4 blocks (gguf_model, huggingface_model, mlx_model, ollama_model) have no frontend entry -- should be deprecated in favor of model_selector
- `huggingface_loader` type name mismatch between backend (`huggingface_loader`) and frontend (`huggingface_dataset_loader`)

### Evaluation (10 blocks)
- **ab_comparator**: Frontend declares model inputs, backend reads dataset inputs -- completely different block concepts
- **factuality_checker**: Frontend methods (semantic_sim, llm_judge) differ from backend methods (contains, f1)
- **toxicity_eval**: Frontend `categories` config completely ignored by backend
- `lm_eval_harness` and `mmlu_eval` crash immediately without `lm_eval` package (no graceful fallback)
- 6 of 10 blocks are missing `block.yaml`

### Flow (16 blocks)
- **conditional_branch**: Output IDs `output_a`/`output_b` vs frontend's `true_branch`/`false_branch` -- data never flows
- **parallel_fan_out**: Backend saves to filesystem paths but never calls `save_output` with the port IDs -- block is non-functional
- **checkpoint_gate**: Frontend and backend represent completely different blocks (save/pause vs metric threshold gate)
- **human_review_gate**: Auto-approves everything -- never actually blocks
- The `fail` output exists on 4 blocks' frontends but is never implemented in any backend
- 10 of 16 blocks missing `block.yaml`

### Inference (23 blocks)
- **14 of 23 blocks are demo-only** with no real inference
- **llm_inference**: `backend` vs `provider` config mismatch; HuggingFace and GGUF backends listed but not implemented; cloud API calls lack auth headers
- **batch_inference**: 5 config fields used by backend are not exposed in frontend
- **chat_completion**: Only Ollama implemented despite listing 4 backends
- All cloud API blocks (OpenAI, Anthropic) lack API key management
- 17 of 23 blocks missing `block.yaml`

### Merge (5 blocks)
- **SLERP**: Frontend sends `t`, backend reads `weight` -- interpolation slider broken
- **DARE**: Frontend sends `drop_rate`/`rescale`, backend reads `weight`/`density` -- entirely broken
- **TIES**: `base` input port declared but never read; weight defaults differ
- **All blocks**: Hardcoded `layer_range: [0, 32]` breaks for non-32-layer models
- 4 of 5 blocks missing `block.yaml`
- Inconsistent output formats (some dicts, some raw paths)

### Output (5 blocks)
- **report_generator**: Promises HTML/PDF/templates but only generates markdown
- **leaderboard_publisher**: Promises MLflow/W&B publishing but only writes local files
- **model_card_writer**: 4 config fields invisible in frontend; `include_biases` dead; table formatting bug
- **artifact_packager**: `compress` config declared but never implemented; `save_artifact` silently fails on directories
- 3 of 5 blocks missing `block.yaml`
- Blocks scattered across `metrics` and `model` categories instead of a unified `output` category

### Training (12 blocks)
- **distillation**: Backend reads `teacher_model`/`student_model` but frontend IDs are `teacher`/`student` -- input loading fails
- **rlhf_ppo**: `reward_model` input declared but never loaded; `ppo_epochs`/`epochs` config mismatch
- **hyperparameter_sweep**: Mock-only with no actual training integration
- **checkpoint_selector**: `import math` used before the import statement (line 83 bug)
- Many training blocks lack `dataset` output for post-training analysis

---

## Missing Blocks

Based on the workflow analysis across all 104 blocks, these blocks are needed but do not exist:

### New Category: "Deployment" (5 blocks)

These blocks fill the gap between training/evaluation and production:

| Block | Description | Inputs | Outputs |
|---|---|---|---|
| `model_registry` | Register model versions with metadata in a local registry | model, metrics, config | config (registry entry) |
| `onnx_converter` | Convert models to ONNX format for cross-platform deployment | model | model, artifact, metrics |
| `model_server_health` | Health check and monitoring for deployed model servers | config (server URL) | metrics, text (status) |
| `api_endpoint_tester` | Send test requests to a deployed model API and validate responses | config (endpoint), dataset (test cases) | metrics, dataset (results) |
| `model_versioner` | Track model versions, compare metrics across versions, manage rollbacks | model, metrics | config, artifact |

### New Category: "Safety" (5 blocks)

Safety and alignment workflows are scattered across evaluation/inference. Consolidating:

| Block | Description | Inputs | Outputs |
|---|---|---|---|
| `prompt_injection_detector` | Detect prompt injection attempts in user inputs | text | text (filtered), metrics (scores) |
| `pii_redactor` | Detect and redact PII from text (names, emails, SSNs, credit cards) | text or dataset | text or dataset (redacted), metrics |
| `content_classifier` | Classify content by safety category (NSFW, violence, hate, etc.) | text or dataset, model | dataset (classified), metrics |
| `bias_detector` | Detect demographic bias in model outputs across protected attributes | dataset, model | metrics, dataset (bias report) |
| `hallucination_detector` | Detect hallucinated claims by checking against a reference corpus | text (output), text (source), model | metrics, text (annotated) |

### Data Category Additions (4 blocks)

| Block | Description | Inputs | Outputs |
|---|---|---|---|
| `dataset_statistics` | Comprehensive dataset analysis (distributions, correlations, quality scores) | dataset | metrics, artifact (report) |
| `label_studio_connector` | Import/export annotations from Label Studio | config | dataset |
| `data_deduplicator` | Deduplicate datasets using exact hash, MinHash, or embedding similarity | dataset, model (optional) | dataset, metrics |
| `json_transformer` | JQ-like JSON transformation and restructuring | dataset or config | dataset or config |

### Inference Category Additions (3 blocks)

| Block | Description | Inputs | Outputs |
|---|---|---|---|
| `multi_modal_inference` | Unified multimodal inference (text+image+audio) | model, text, artifact | text, config, metrics |
| `caching_proxy` | Cache LLM responses by prompt hash to avoid redundant API calls | text, model | text, metrics |
| `confidence_scorer` | Score model confidence using log-probabilities or consistency sampling | text (response), model | metrics, text |

### Flow Category Additions (3 blocks)

| Block | Description | Inputs | Outputs |
|---|---|---|---|
| `rate_limiter` | Rate-limit throughput to N items/second for API-bound pipelines | any | any (passthrough), metrics |
| `data_validator` | Validate data against a JSON schema or custom rules | dataset, config (schema) | dataset (valid), dataset (invalid), metrics |
| `pipeline_timer` | Measure wall-clock time of pipeline segments | any (start trigger) | metrics, any (passthrough) |

### Evaluation Category Additions (2 blocks)

| Block | Description | Inputs | Outputs |
|---|---|---|---|
| `coherence_eval` | Evaluate text coherence and fluency using perplexity or LLM scoring | dataset, model | metrics, dataset |
| `rouge_bleu_eval` | Dedicated ROUGE/BLEU/METEOR evaluation (separated from custom_benchmark for ease of use) | dataset (predictions + references) | metrics, dataset |

### Output Category Addition (1 block)

| Block | Description | Inputs | Outputs |
|---|---|---|---|
| `huggingface_publisher` | Push model + model card + metrics to HuggingFace Hub | model, text (card), metrics, config | config (hub URL), metrics |

### Total: 23 new blocks across 3 new + 5 existing categories

**New categories needed**: Deployment (5 blocks), Safety (5 blocks)

**Blocks that don't fit existing categories and need "Safety"**: prompt_injection_detector, pii_redactor, content_classifier, bias_detector, hallucination_detector -- these are distinct from "evaluation" (which measures model quality) and from "inference/guardrails" (which is a single filter step). Safety is a workflow concern that spans detection, classification, and remediation.

**Blocks that don't fit existing categories and need "Deployment"**: model_registry, onnx_converter, model_server_health, api_endpoint_tester, model_versioner -- these are distinct from "output" (which generates reports/artifacts) and from "flow" (which controls pipeline logic). Deployment is about getting models into production.

---

## Implementation Priorities

### Phase 0: Shared Utilities (Foundation)
*Must be done first -- everything else depends on this.*

1. Create `blocks/_shared/llm_utils.py` with `call_llm()` and `resolve_model()`
2. Create `blocks/_shared/data_utils.py` with `find_dataset_file()`, `load_dataset_rows()`, `save_dataset_rows()`
3. Create `blocks/_shared/model_utils.py` with `resolve_model_info()` (handles dicts, strings, paths)
4. Standardize all blocks to use `backend` (not `provider`) as the config key name

### Phase 1: Fix Critical Breakage (Highest Priority)
*These are blocks that are fundamentally non-functional due to mismatches.*

1. **slerp_merge**: Fix `t` vs `weight` config key
2. **dare_merge**: Fix `drop_rate`/`rescale` vs `weight`/`density` config keys
3. **ties_merge**: Read the `base` input port; fix weight default
4. **conditional_branch**: Rename outputs `output_a`/`output_b` to `true_branch`/`false_branch`
5. **parallel_fan_out**: Save chunks to `out_1`/`out_2`/`out_3` output ports
6. **aggregator**: Rename output to `output`; rename config to `method`
7. **error_handler**: Rename output to `success`; rename config to `retry_count`
8. **llm_inference**: Rename `provider` to `backend`; add API key handling
9. **distillation**: Fix input IDs `teacher`/`student` vs `teacher_model`/`student_model`
10. **rlhf_ppo**: Load `reward_model` input; fix `ppo_epochs`/`epochs`

### Phase 2: Fix Config Mismatches & Dead Config
*User-facing config that has no effect.*

1. Fix all remaining config key name mismatches (40+ blocks)
2. Implement or remove all dead config fields (50+ blocks)
3. Add missing config fields that backends read but frontends don't expose
4. Fix all default value mismatches between frontend and backend

### Phase 3: Fix Input/Output Mismatches
*Ports that are declared but not wired to anything.*

1. All blocks with unused input ports: either implement loading or remove the port
2. All blocks with missing output ports: add `save_output` calls
3. Standardize output file naming (`data.json` everywhere)
4. Add passthrough outputs to terminal blocks (viewers, loggers, exporters)

### Phase 4: Implement Real Inference
*Replace demo responses with actual LLM calls.*

Priority order for inference blocks:
1. `chat_completion` (most common use case after llm_inference)
2. `structured_output` (high demand for JSON extraction)
3. `function_calling` (agent workflows)
4. `few_shot_prompting` (common ML pattern)
5. `prompt_chain` (workflow composition)
6. `vision_inference` (multimodal)
7. `a/b_test_inference` (evaluation)
8. `model_router` (production routing)

### Phase 5: Create Missing block.yaml Files
*66 blocks need these created.*

Generate `block.yaml` for every block that is missing one, based on the actual run.py behavior and frontend registry definition.

### Phase 6: Add Detail Sections
*Frontend UX improvement.*

Add `detail: { tips, useCases, howItWorks }` to all 104 blocks in the frontend registry.

### Phase 7: Build New Blocks
*Fill workflow gaps identified in the audit.*

1. Safety category (5 blocks) -- high user value
2. Deployment category (5 blocks) -- completes the ML lifecycle
3. Data additions (4 blocks) -- fills common preprocessing gaps
4. Inference additions (3 blocks) -- caching, confidence, multimodal
5. Flow additions (3 blocks) -- rate limiting, validation, timing
6. Evaluation additions (2 blocks) -- coherence, ROUGE/BLEU
7. Output addition (1 block) -- HuggingFace Hub publishing

### Phase 8: Deprecate Redundant Blocks

1. `gguf_model` -> use `model_selector` with `source: local_path`
2. `huggingface_model` -> use `model_selector` with `source: huggingface`
3. `mlx_model` -> use `model_selector` with `source: mlx`
4. `ollama_model` -> use `model_selector` with `source: ollama`
5. `results_exporter` -> merge into `data_exporter` (add Parquet support)

---

## Key File Map

| File | Role | Changes Needed |
|---|---|---|
| `frontend/src/lib/block-registry.ts` | Central frontend registry (3113 lines) | Every block's inputs/outputs/config must be reconciled with backend |
| `backend/block_sdk/context.py` | BlockContext API | Add shared utilities, possibly `PipelinePaused` exception |
| `backend/engine/block_registry.py` | Block discovery | Ensure block.yaml files are used consistently |
| `blocks/_shared/` (NEW) | Shared utilities | Create llm_utils.py, data_utils.py, model_utils.py |

---

*This audit was generated by analyzing all 104 block implementations across 8 categories. Every `run.py`, available `block.yaml`, and frontend registry entry was read and cross-referenced.*
