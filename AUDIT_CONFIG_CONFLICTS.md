# Config Conflict Audit

Generated: Session 14 — Pipeline Config Conflict Resolution

## Cross-Category Duplicates (Scan 2)

Keys appearing in 3+ blocks across 2+ categories. Session 10 already resolved model_name, provider, endpoint, api_key. This audit covers everything else.

| Key | Blocks | Categories | Status |
|-----|--------|------------|--------|
| `output_format` | 37 | data, agents, evaluation, inference, flow | FALSE POSITIVE — block-specific rendering preference |
| `model_name` | 34 | data, training, output, evaluation, inference, flow | RESOLVED (Session 10) |
| `temperature` | 23 | data, agents, training, evaluation, inference, flow | RESOLVED (Session 10 inheritance); `distillation` uses different semantics (KD temp=2.0) — intentionally independent |
| `text_column` | 21 | data, training, evaluation, inference | **REAL CONFLICT** — Conflict 1 |
| `batch_size` | 20 | data, training, evaluation, inference, endpoints, flow | FALSE POSITIVE — different purposes per category (training=4, eval=auto, embedding=32, write=1000) |
| `max_tokens` | 18 | agents, data, inference | RESOLVED (Session 10 inheritance) |
| `endpoint` | 18 | data, evaluation, inference | RESOLVED (Session 10) |
| `api_key` | 18 | flow, inference | RESOLVED (Session 10) |
| `method` | 16 | data, merge, agents, evaluation, inference, endpoints, flow | FALSE POSITIVE — wildly different semantics (HTTP method, merge strategy, clustering algo, etc.) |
| `provider` | 16 | data, flow, evaluation, inference | RESOLVED (Session 10) |
| `format` | 14 | data, agents, output, inference, endpoints, flow | FALSE POSITIVE — block-specific serialization format |
| `system_prompt` | 14 | agents, data, flow, inference | **REAL CONFLICT** — Conflict 2 |
| `seed` | 10 | agents, data, evaluation | **REAL CONFLICT** — Conflict 3 |
| `max_samples` | 10 | data, evaluation | FALSE POSITIVE — data loader caps rows loaded; eval blocks cap samples evaluated. Different stages. |
| `prompt_template` | 7 | training, inference | **REAL CONFLICT** — Conflict 4 |
| `trust_remote_code` | 5 | data, evaluation | **REAL CONFLICT** — Conflict 5 |
| `threshold` | 8 | flow, evaluation, inference | FALSE POSITIVE — different thresholds for different block purposes |
| `max_new_tokens` | 6 | training, evaluation | FALSE POSITIVE — each eval/training block has its own generation limit |
| `max_seq_length` | 8 | training, evaluation | FALSE POSITIVE — training blocks share the same training context; eval model_telemetry is independent |
| `normalize` | 4 | endpoints, flow, inference | FALSE POSITIVE — all relate to embedding normalization, but blocks are in different pipeline positions |
| `shuffle` | 4 | data, flow | **REAL CONFLICT** — Conflict 3 (propagated with seed) |
| `decimal_precision` | 15 | evaluation only | FALSE POSITIVE — evaluation-only, same category |
| `top_k` | 5 | agents, data, inference | FALSE POSITIVE — all retrieval-related but different pipeline positions |
| `embedding_column` | 4 | flow, inference | FALSE POSITIVE — intentionally independent (each block reads/writes embeddings) |
| `filename` | 10 | endpoints, flow | FALSE POSITIVE — intentionally independent (different output files) |

## Pipeline Conflict Map (Scan 3)

### Pipeline 1: huggingface_loader → train_val_test_split → model_selector → lora_finetuning → lm_eval_harness → results_formatter

| Key | huggingface_loader | train_val_test_split | lora_finetuning | lm_eval_harness | Owner | Conflict? |
|-----|-------------------|---------------------|-----------------|-----------------|-------|-----------|
| `seed` | 42 | 42 | — | — | huggingface_loader | YES — must propagate |
| `shuffle` | false | true | — | — | huggingface_loader | YES — must propagate |
| `text_column` | (via columns) | — | "" | — | huggingface_loader | YES — must propagate |
| `model_name` | — | — | "" | "" | model_selector | RESOLVED (S10) |
| `prompt_template` | — | — | "" | — | lora_finetuning | YES — rename to training_format |
| `trust_remote_code` | false | — | — | false | huggingface_loader | YES — must propagate |
| `batch_size` | — | — | 4 | "auto" | Each block | No (different purpose) |

### Pipeline 2: model_selector → llm_inference → chat_completion → batch_inference → results_formatter

| Key | llm_inference | chat_completion | batch_inference | Owner | Conflict? |
|-----|--------------|-----------------|-----------------|-------|-----------|
| `system_prompt` | "" | "You are helpful..." | "" | Each block (NOT inherited) | YES — Conflict 2 |
| `temperature` | 0.7 | 0.7 | 0.7 | llm_inference (inherited) | RESOLVED (S10) |
| `prompt_template` | "{input}" | — | "{text}" | Each inference block | No (legitimate difference) |
| `text_column` | — | — | "text" | batch_inference only | No (only batch_inference uses dataset) |

### Pipeline 3: local_file_loader → text_chunker → embedding_generator → vector_store_build → model_selector → rag_pipeline → results_formatter

| Key | local_file_loader | text_chunker | embedding_generator | rag_pipeline | Owner | Conflict? |
|-----|------------------|-------------|--------------------|-----------| ------|-----------|
| `text_column` | (via columns) | "text" | "text" | "text" | local_file_loader | YES — must propagate |

### Pipeline 4: model_selector → llm_inference → chain_of_thought → multi_agent_debate → custom_benchmark

| Key | llm_inference | chain_of_thought | multi_agent_debate | Owner | Conflict? |
|-----|--------------|-----------------|-------------------|-------|-----------|
| `system_prompt` | "" | — | — | Each block | YES — Conflict 2 |
| `temperature` | 0.7 | 0.3 | 0.7 | llm_inference (inherited) | RESOLVED (S10) |
| `seed` | — | — | 42 | — | No (only multi_agent_debate uses seed) |

### Pipeline 5: huggingface_loader → model_selector → custom_benchmark → lm_eval_harness → toxicity_eval → results_formatter

| Key | huggingface_loader | custom_benchmark | lm_eval_harness | toxicity_eval | Owner | Conflict? |
|-----|-------------------|-----------------|-----------------|---------------|-------|-----------|
| `trust_remote_code` | false | — | false | — | model (propagated) | YES — Conflict 5 |
| `text_column` | — | — | — | "text" | huggingface_loader | YES — Conflict 1 |
| `max_samples` | 0 | 0 | — | 0 | Each block | No (each eval limits independently) |

### Pipeline 6: huggingface_loader → filter_sample → text_chunker → train_val_test_split → save_csv

| Key | huggingface_loader | filter_sample | text_chunker | train_val_test_split | Owner | Conflict? |
|-----|-------------------|--------------|-------------|---------------------|-------|-----------|
| `text_column` | — | "text" | "text" | — | huggingface_loader | YES — Conflict 1 |
| `seed` | 42 | 42 | — | 42 | huggingface_loader | YES — Conflict 3 |
| `shuffle` | false | — | — | true | huggingface_loader | YES — Conflict 3 |

### Pipeline 7: model_selector → model_selector → slerp_merge → lm_eval_harness → custom_benchmark

No data-layer conflicts. Model routing via different ports (model_a, model_b).

### Pipeline 8: local_file_loader → data_augmentation → train_val_test_split → qlora_finetuning → custom_benchmark

| Key | local_file_loader | data_augmentation | train_val_test_split | qlora_finetuning | Owner | Conflict? |
|-----|------------------|------------------|---------------------|-----------------|-------|-----------|
| `text_column` | — | "text" | — | "" | local_file_loader | YES — Conflict 1 |
| `seed` | — | 42 | 42 | — | data_augmentation | YES — Conflict 3 |

### Pipeline 9: model_selector → llm_inference → structured_output → response_parser → save_json

| Key | llm_inference | structured_output | Owner | Conflict? |
|-----|--------------|------------------|-------|-----------|
| `system_prompt` | "" | "" | Each block | YES — Conflict 2 |
| `temperature` | 0.7 | 0.3 | llm_inference (inherited) | RESOLVED (S10) |

### Pipeline 10: huggingface_loader → text_chunker → embedding_generator → embedding_clustering → save_csv

| Key | huggingface_loader | text_chunker | embedding_generator | embedding_clustering | Owner | Conflict? |
|-----|-------------------|-------------|--------------------|--------------------|-------|-----------|
| `text_column` | — | "text" | "text" | — | huggingface_loader | YES — Conflict 1 |
| `normalize` | — | — | false | false | Each block | No (independent decision) |

## Port Compatibility Issues (Scan 4)

42 blocks read from a model input port. The standardized model output from model_selector includes: `source`, `model_id`, `model_name`, `validated`, `downloaded`, `quantization`.

**Pattern A (8 blocks) — Read standardized keys directly:**
chat_completion, few_shot_prompting, function_calling, model_router, prompt_chain, structured_output, vision_inference, batch_inference
Keys read: `model_name`, `model_id`, `backend`, `provider`, `base_url`, `endpoint`, `api_key` — all present in model output.

**Pattern B (many blocks) — Also read `path` key:**
lm_eval_harness, mmlu_eval, model_telemetry, custom_benchmark — read `path` which IS present for local source models but NOT for ollama/huggingface sources. These blocks fall back to `model_name`/`model_id`, so no crash.

**Pattern C — Missing `trust_remote_code` from model output:**
lm_eval_harness, mmlu_eval, model_telemetry read `trust_remote_code` from their own config but NOT from model data. This is **Conflict 5**.

**No port compatibility issues found** beyond Conflict 5. All blocks gracefully fall back when model keys are absent.

## Semantic Collisions (Same Key, Different Meaning)

| Key | Block A Meaning | Block B Meaning | Verdict |
|-----|----------------|-----------------|---------|
| `temperature` | Sampling temperature (0.0-2.0) in inference/agents | Knowledge distillation temperature (2.0) in training/distillation | FALSE POSITIVE — blocks never in same pipeline position; distillation defaults to 2.0 which is a different concept |
| `temperature` | Sampling temperature in training/rlhf_ppo | Same meaning (sampling during PPO rollouts) | FALSE POSITIVE — same semantic |
| `prompt_template` | Runtime prompt wrapping in inference blocks | Training data format template in training blocks | **REAL CONFLICT** — Conflict 4 |
| `method` | HTTP method (GET/POST) in api_data_fetcher/api_publisher | Filter strategy in filter_sample | FALSE POSITIVE — never in same pipeline |
| `method` | Clustering algorithm in embedding_clustering | Evaluation method in bias_fairness_eval | FALSE POSITIVE — never in same pipeline |
| `batch_size` | Training mini-batch (4) | Eval batch (auto/32) | FALSE POSITIVE — different pipeline stages |
| `batch_size` | Embedding encoding batch (32) | Vector store indexing batch (256) | FALSE POSITIVE — embedding_generator → vector_store_build, but each has legitimately different optimal batch sizes |
| `max_length` | Filter max char length | DPO max sequence length | FALSE POSITIVE — never in same pipeline |
| `top_k` | Retrieval count (5-10) in RAG/reranker | Filter top-K rows (100) in filter_sample | FALSE POSITIVE — different pipeline stages |
| `output_format` | "json"/"csv" in eval | "text"/"markdown" in inference | FALSE POSITIVE — block-specific rendering |
| `normalize` | Embedding L2 normalization | Same meaning across all 4 blocks | FALSE POSITIVE — consistent semantics |

## NEW CONFLICTS FOUND

No additional real conflicts discovered beyond the 5 known conflicts. The scans confirmed that:

1. `output_format`, `batch_size`, `method`, `format`, `threshold`, `max_samples`, `decimal_precision`, `filename`, `max_new_tokens`, `top_k`, `normalize`, `embedding_column`, `max_seq_length` are all **intentionally independent** — either they exist in a single category, or they have clearly different semantics that users would understand.

2. The `temperature` collision in `training/distillation` (KD temperature=2.0) is semantically different but NEVER appears in the same pipeline as inference temperature, so it's a false positive.

3. `random_seed` (used in flow/ab_split_test, flow/parallel_fan_out, inference/embedding_clustering) is a DIFFERENT key from `seed`, so no collision with the data `seed` propagation.

## Recommended Fixes

### Conflict 1: text_column → Propagate via dataset_meta
- Data loaders (huggingface_loader, local_file_loader) output `dataset_meta` with column info
- Intermediate blocks (filter_sample, text_chunker, data_augmentation, train_val_test_split, data_merger) pass through meta
- Downstream blocks read text_column from meta first, config as fallback

### Conflict 2: system_prompt → Block-specific, NOT inherited
- Each block keeps its own system_prompt
- Never read system_prompt from upstream model data or llm_config

### Conflict 3: seed + shuffle → Propagate via dataset_meta
- Data loaders include seed/shuffle in dataset_meta
- Downstream data blocks read from meta, local config overrides

### Conflict 4: prompt_template → Rename to training_format in training blocks
- 5 training blocks: ballast_training, curriculum_training, full_finetuning, lora_finetuning, qlora_finetuning
- Backward compatible: read new key first, fall back to old key

### Conflict 5: trust_remote_code → Propagate via model metadata
- model_selector, huggingface_model_loader include trust_remote_code in model output
- lm_eval_harness, mmlu_eval, model_telemetry read from model data first, config as fallback

## Post-Fix Verification

### Build Verification
- Backend: `python3 -c "from backend.main import app; print('OK')"` — PASS
- Frontend: `npx tsc --noEmit` — PASS (zero errors)

### Conflict 1 Verification (text_column via dataset_meta)
- `grep -n "dataset_meta" blocks/data/huggingface_loader/run.py` → save_output at line 239 ✓
- `grep -n "dataset_meta" blocks/data/local_file_loader/run.py` → save_output at line 209 ✓
- `grep -n "dataset_meta" blocks/training/lora_finetuning/run.py` → load_input at line 11, text_column from meta at line 27 ✓
- `grep -n "dataset_meta" blocks/data/filter_sample/run.py` → load/passthrough at lines 14-18, 167-169 ✓
- All 25 block.yaml files have dataset_meta ports ✓

### Conflict 2 Verification (system_prompt block-specific)
- All 14 blocks read system_prompt from ctx.config.get() only — ALREADY CORRECT, no changes needed ✓

### Conflict 3 Verification (seed propagation)
- `blocks/data/filter_sample/run.py:34` → `seed = int(ctx.config.get("seed") or _dataset_meta.get("seed", 42))` ✓
- `blocks/data/train_val_test_split/run.py` → seed from meta with local override ✓
- `blocks/data/data_augmentation/run.py` → seed from meta with local override ✓
- `blocks/data/data_merger/run.py` → seed from meta with local override ✓

### Conflict 4 Verification (training_format rename)
- `grep -rn "training_format" blocks/training/*/run.py` → 5 blocks, all with backward-compat fallback ✓
- `grep -n "training_format" frontend/src/lib/block-registry.ts` → 10 entries (5 defaultConfig + 5 configFields) ✓
- Only 2 inference blocks (llm_inference, batch_inference) still use prompt_template as PRIMARY key ✓

### Conflict 5 Verification (trust_remote_code propagation)
- `blocks/data/huggingface_model_loader/run.py` already outputs trust_remote_code in model_info ✓
- `blocks/evaluation/lm_eval_harness/run.py` → reads from model_info.get("trust_remote_code") as fallback ✓
- `blocks/evaluation/mmlu_eval/run.py` → same pattern ✓
- `blocks/evaluation/model_telemetry/run.py` → same pattern ✓

### Post-Fix Scan Results
Cross-category duplicates with prompt_template: The scan shows 7 blocks across training+inference. However:
- 5 training blocks use `training_format` as PRIMARY key, only referencing `prompt_template` as backward-compat fallback
- 2 inference blocks (llm_inference, batch_inference) use `prompt_template` as their legitimate primary key
- **No actual collision exists** — the keys are semantically separated

All remaining cross-category duplicates are either:
- (a) RESOLVED by Session 10 (model_name, temperature, max_tokens, endpoint, api_key, provider)
- (b) RESOLVED by this session (text_column, system_prompt, seed, shuffle, prompt_template, trust_remote_code)
- (c) Documented as INTENTIONALLY INDEPENDENT (output_format, batch_size, method, format, threshold, etc.)

### Workflow Traces

**Workflow 1 (Standard LoRA Fine-tuning):** huggingface_loader(text_column detected from columns) → train_val_test_split(inherits text_column, seed=42, shuffle from meta) → model_selector → lora_finetuning(reads text_column from meta, uses training_format) → lm_eval_harness(reads trust_remote_code from model) ✓

**Workflow 2 (RAG with Custom Columns):** local_file_loader(detects text_column="body") → text_chunker(reads text_column="body" from meta) → embedding_generator(reads text_column="body" from meta) → vector_store_build → model_selector → rag_pipeline(reads text_column from meta) ✓

**Workflow 3 (Agent with Task-Specific Prompts):** model_selector → llm_inference(system_prompt="Research AI") → chain_of_thought(own system_prompt) → multi_agent_debate(own system_prompt) — each uses its OWN system_prompt ✓

**Workflow 4 (Training vs Inference Template):** huggingface_loader → lora_finetuning(training_format="### Q: {instruction}") → llm_inference(prompt_template="{context}\n{input}") — different keys, no collision ✓

**Workflow 5 (Eval Sweep with Shared Model):** model_selector(trust_remote_code from huggingface_model_loader) → lm_eval_harness(inherits trust_remote_code) → toxicity_eval(own threshold) → custom_benchmark(own temperature) ✓

**Edge Case 1 (Two Model Selectors):** model_selector_A → slerp_merge ← model_selector_B — different ports (model_a, model_b), no conflict ✓

**Edge Case 2 (Overriding Inherited Values):** model_selector → llm_inference(temperature=0.0) → batch_inference(temperature=0.5) — local config override wins ✓

**Edge Case 3 (Non-Standard Columns):** local_file_loader(custom.csv with "body","category") → filter_sample(text_column="body" from meta) → lora_finetuning(text_column="body" from meta) ✓

**Edge Case 4 (Backward Compatibility):** Old pipeline with no dataset_meta → lora_finetuning → falls back to ctx.config.get("text_column", "") → no crash ✓

### ZERO unresolved cross-category conflicts remaining.
