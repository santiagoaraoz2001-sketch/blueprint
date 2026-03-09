# Blueprint: Block-by-Block Config Modification Plan

> Comprehensive per-block analysis of ALL 104 blocks. For each block: current config, configs to add/modify/remove, input/output port changes, and frontend-backend mismatches. Cross-referenced against actual `run.py` files, `block.yaml`, and `block-registry.ts`.

**Legend:**
- **CRITICAL**: Block is fundamentally broken — user config has no effect
- **HIGH**: Data flow is broken or misleading
- **MEDIUM**: Missing features or dead config
- **LOW**: Nice-to-have improvements

---

## Table of Contents

1. [Merge (5 blocks)](#1-merge-category)
2. [Evaluation (10 blocks)](#2-evaluation-category)
3. [Agents (9 blocks)](#3-agents-category)
4. [Output (5 blocks)](#4-output-category)
5. [Data (24 blocks)](#5-data-category)
6. [Flow (16 blocks)](#6-flow-category)
7. [Inference (23 blocks)](#7-inference-category)
8. [Training (12 blocks)](#8-training-category)
9. [Cross-Cutting Summary](#9-cross-cutting-summary)

---

# 1. MERGE CATEGORY

## 1.1 dare_merge — CRITICAL

**Current frontend config:** `drop_rate` (float, 0.7), `rescale` (boolean, true)
**What run.py actually reads:** `weight` (float, 0.5), `density` (float, 0.5), `output_name` (string)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| REMOVE | `drop_rate` | float | 0.7 | — | — | Backend reads `weight` and `density`, NOT `drop_rate` |
| REMOVE | `rescale` | boolean | true | — | — | Backend never reads this |
| ADD | `weight` | float | 0.5 | min:0 max:1 | — | Interpolation weight for Model B |
| ADD | `density` | float | 0.5 | min:0 max:1 | — | Fraction of delta parameters to keep |
| ADD | `dare_variant` | select | dare_ties | dare_ties, dare_linear | — | DARE variant to use |
| ADD | `dtype` | select | float16 | float16, bfloat16, float32 | — | Output data type |
| ADD | `output_name` | string | dare-merged-model | — | — | Output model name |
| ADD | `allow_crimes` | boolean | false | — | — | Allow architecture mismatches |

**Port changes:**
- ADD input: `base_model` (model, optional) — DARE-TIES needs base for task vectors; currently hardcoded to model_a
- ADD output: `metrics` (metrics, optional) — run.py saves metrics but no port exists

**Mismatches:** Frontend sends `drop_rate`/`rescale`; backend reads `weight`/`density`. User config has ZERO effect. Metrics output saved but invisible.

---

## 1.2 frankenmerge — HIGH

**Current frontend config:** `layer_config` (text_area, '{}'), `merge_embed` (select: a/b/average)
**What run.py actually reads:** `layer_config`, `output_name`

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| REMOVE | `merge_embed` | select | a | a, b, average | — | Backend never reads this. Dead config. |
| MODIFY | `layer_config` | text_area | '' | — | — | Change default from '{}' to '' — empty dict is truthy and causes iteration errors |
| ADD | `dtype` | select | float16 | float16, bfloat16, float32 | — | Currently hardcoded |
| ADD | `copy_tokenizer` | boolean | true | — | — | Currently hardcoded as --copy-tokenizer flag |
| ADD | `output_name` | string | frankenmerge-model | — | — | run.py reads but not exposed |

**Port changes:**
- ADD input: `model_c` (model, optional) — Frankenmerge assembles from multiple models
- ADD output: `metrics` (metrics, optional) — run.py saves metrics but no port exists

**Mismatches:** `merge_embed` in frontend completely ignored. Hardcoded 32-layer assumption for auto-split.

---

## 1.3 mergekit_merge — HIGH

**Current frontend config:** `method` (select: slerp/ties/dare_ties/linear/passthrough), `weight` (float, 0.5)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `method` | select | slerp | slerp, ties, dare_ties, dare_linear, linear | — | Remove `passthrough` (useless here, use frankenmerge), add `dare_linear` |
| ADD | `density` | float | 0.5 | min:0 max:1 | {field:'method', value:'ties'} | Critical for TIES/DARE; run.py reads it but not in frontend |
| ADD | `dtype` | select | float16 | float16, bfloat16, float32 | — | Hardcoded to float16 |
| ADD | `output_name` | string | merged-model | — | — | run.py reads but not exposed |
| ADD | `allow_crimes` | boolean | false | — | — | Allow architecture mismatches |

**Port changes:**
- ADD input: `base_model` (model, optional) — Needed for TIES/DARE methods
- ADD output: `metrics` (metrics, optional) — Uses ctx.log_metric but no output port

**Mismatches:** `density` is invisible — TIES/DARE users can't control sparsity. Hardcoded `layer_range: [0, 32]` breaks non-32-layer models. Output format inconsistent (raw string vs dict).

---

## 1.4 slerp_merge — CRITICAL

**Current frontend config:** `t` (float, 0.5)
**What run.py actually reads:** `weight` (float, 0.5)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `t` → keep `t` | — | — | — | — | Fix run.py to read `t` instead of `weight` (SLERP parameter is mathematically `t`) |
| ADD | `dtype` | select | float16 | float16, bfloat16, float32 | — | Hardcoded to float16 |
| ADD | `output_name` | string | slerp-merged-model | — | — | run.py reads but not exposed |

**Port changes:**
- ADD output: `metrics` (metrics, optional) — run.py saves metrics but no port exists

**Mismatches:** Frontend sends `t`, backend reads `weight`. User's interpolation slider has ZERO effect — always uses default 0.5. Hardcoded `layer_range: [0, 32]`.

---

## 1.5 ties_merge — HIGH

**Current frontend config:** `density` (float, 0.5), `weight` (float, 1.0)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `weight` default | — | — | — | — | Frontend default 1.0 but run.py default 0.5 — fix run.py to match |
| ADD | `dtype` | select | float16 | float16, bfloat16, float32 | — | Hardcoded to float16 |
| ADD | `output_name` | string | ties-merged-model | — | — | run.py reads but not exposed |

**Port changes:**
- MODIFY input: `base` → rename to `base_model` — Backend NEVER reads `base` input; hardcodes `base_model: model_a_name`. Defeats the entire purpose of TIES.
- ADD input: `model_c` (model, optional) — TIES is designed for multi-model merging
- ADD output: `metrics` (metrics, optional) — run.py saves metrics but no port exists

**Mismatches:** `base` input port declared but NEVER read by backend — user's base model connection is silently ignored, destroying TIES's core functionality. Weight default mismatch (1.0 vs 0.5).

---

### Merge Cross-Cutting Issues
- All 5 blocks need `dtype` and `output_name`
- 4 of 5 lack block.yaml files
- No shared model resolution utility — each reimplements differently
- None save mergekit YAML configs as artifacts for reproducibility
- `_get_model_name` doesn't resolve `path` key from training block outputs

---

# 2. EVALUATION CATEGORY

## 2.1 ab_comparator — CRITICAL

**Current frontend config:** `metrics` (string, "accuracy,latency"), `judge_model` (string, "")

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| REMOVE | `metrics` | string | accuracy,latency | — | — | Backend never reads this config. Name collides with output port. |
| ADD | `method` | select | auto | auto, llm_judge, exact_match, semantic_similarity | — | Comparison method |
| ADD | `text_column` | string | _response | — | — | Column name for responses |
| ADD | `seed` | integer | 42 | — | — | Random seed |
| ADD | `max_response_length` | integer | 500 | — | — | Max chars per response in output |
| MODIFY | `judge_model` | string | "" | — | {field:'method', value:'llm_judge'} | Add depends_on |

**Port changes:**
- ADD input: `dataset_a` (dataset, optional) — Backend loads this but frontend has no port
- ADD input: `dataset_b` (dataset, optional) — Backend loads this but frontend has no port
- MODIFY input: `model_a` → required:false — Backend never loads models
- MODIFY input: `model_b` → required:false — Backend never loads models
- REMOVE input: `model_c` — Completely unused in both frontend and backend
- ADD output: `dataset` (dataset, optional) — Backend saves per-row comparison data

**Mismatches:** Frontend declares 3 model inputs; backend loads 0 models and instead loads dataset_a/dataset_b. Scoring is heuristic (response length + noise). `judge_model` config exists but zero LLM-judge logic implemented.

---

## 2.2 custom_benchmark — MEDIUM

**Current frontend config:** `metric` (select: accuracy/f1/bleu/rouge/perplexity/exact_match), `threshold` (float, 0.0)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `metric` | multiselect | accuracy | accuracy, f1, bleu, rouge, exact_match | — | Change from select to multiselect; remove `perplexity` (silently falls back to accuracy) |
| ADD | `input_field` | string | "" | — | — | Column name for inputs |
| ADD | `target_field` | string | "" | — | — | Column name for ground truth |
| ADD | `max_samples` | integer | 0 | — | — | 0 = all samples |
| ADD | `max_new_tokens` | integer | 64 | min:1 max:2048 | — | Backend hardcodes 64 |

**Port changes:**
- ADD output: `dataset` (dataset, optional) — For per-sample results inspection

**Mismatches:** `perplexity` metric silently computes accuracy instead. `exact_match` in frontend but missing from block.yaml. Backend hardcodes `max_new_tokens=64`.

---

## 2.3 custom_eval — LOW

**Current frontend config:** `scoring_function` (text_area), `aggregate` (select: mean/median/min/max/sum), `trust_level` (select: sandboxed/trusted)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `preset` | select | custom | custom, exact_match, contains, json_valid, regex_match, word_count | — | Preset scoring templates |
| ADD | `regex_pattern` | string | "" | — | {field:'preset', value:'regex_match'} | Pattern for regex preset |
| ADD | `max_errors` | integer | 0 | min:0 | — | Stop after N errors (0=unlimited) |
| MODIFY | `scoring_function` | text_area | — | — | {field:'preset', value:'custom'} | Only show when preset=custom |

**Port changes:** None needed.

**Mismatches:** Uses `ctx.inputs.get()` instead of `ctx.load_input()`. Sandbox is ineffective (doesn't prevent `__import__`).

---

## 2.4 factuality_checker — HIGH

**Current frontend config:** `method` (select: exact_match/semantic_sim/llm_judge), `use_judge` (boolean, false)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| REMOVE | `use_judge` | boolean | false | — | — | Dead config. Backend never reads it. |
| MODIFY | `method` options | select | exact_match | exact_match, contains, f1, semantic_sim, llm_judge | — | Backend implements contains/f1 but not semantic_sim/llm_judge |
| ADD | `output_column` | string | _response | — | — | Column with model outputs |
| ADD | `reference_column` | string | reference | — | — | Column with ground truth |
| ADD | `case_sensitive` | boolean | false | — | — | Whether comparison is case-sensitive |
| ADD | `f1_threshold` | float | 0.5 | min:0 max:1 | {field:'method', value:'f1'} | Threshold for F1 |
| ADD | `judge_model` | string | "" | — | {field:'method', value:'llm_judge'} | Model for LLM judging |

**Port changes:**
- MODIFY input: `model` → required:false — Backend NEVER loads model input
- ADD output: `dataset` (dataset, optional) — Backend saves per-item results

**Mismatches:** Model input declared required but never used. Method options diverge between frontend and backend. `use_judge` is dead. Two backend methods (contains, f1) not selectable from frontend.

---

## 2.5 human_eval — MEDIUM

**Current frontend config:** `k_values` (string, "1,10,100"), `temperature` (float, 0.8), `num_samples` (integer, 200)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| REMOVE | `num_samples` | integer | 200 | — | — | Misleading name; replace with num_problems |
| ADD | `num_problems` | integer | 164 | min:1 max:500 | — | Number of HumanEval problems |
| ADD | `model_name` | string | "" | — | — | Fallback model name |
| ADD | `execution_timeout` | float | 5.0 | min:1 max:60 | — | Timeout per test case |
| ADD | `seed` | integer | 42 | — | — | Random seed |
| ADD | `benchmark` | select | humaneval | humaneval, mbpp | — | Code benchmark choice |
| MODIFY | `temperature` default | float | 0.0 | — | — | Backend default is 0.0, not 0.8 |

**Port changes:**
- ADD output: `dataset` (dataset, optional) — Per-problem results

**Mismatches:** `num_samples` (frontend) vs `num_problems` (backend) — different semantics. Temperature default mismatch (0.8 vs 0.0).

---

## 2.6 latency_profiler — HIGH

**Current frontend config:** `num_runs` (integer, 100), `input_length` (integer, 128), `output_length` (integer, 128)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| REMOVE | `input_length` | integer | 128 | — | — | Replace with input_lengths (string) |
| REMOVE | `output_length` | integer | 128 | — | — | Backend never reads it; hardcodes num_predict:10 |
| MODIFY | `num_runs` | integer | 5 | min:1 | — | Change default from 100→5, min from 10→1 to match backend |
| ADD | `input_lengths` | string | "32,128,512" | — | — | Comma-separated sweep |
| ADD | `batch_sizes` | string | "1,2,4,8" | — | — | Key feature of the block |
| ADD | `num_warmup` | integer | 2 | min:0 | — | Warmup runs |
| ADD | `provider` | select | ollama | ollama, openai_compatible, transformers | — | Inference provider |
| ADD | `endpoint` | string | http://localhost:11434 | — | — | API endpoint |
| ADD | `seed` | integer | 42 | — | — | Random seed |

**Port changes:**
- ADD output: `dataset` (dataset, optional) — Per-config profiling data

**Mismatches:** `input_length` (single int) vs `input_lengths` (comma-separated string). `output_length` is dead. `num_runs` default 20x mismatch (100 vs 5). `batch_sizes` — the block's key feature — is invisible.

---

## 2.7 lm_eval_harness — MEDIUM

**Current frontend config:** `tasks` (string, "hellaswag,arc_easy"), `num_fewshot` (integer, 0), `batch_size` (string, "auto")

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `backend` | select | hf | hf, vllm, gguf, openai, local-completions | — | lm_eval model backend |
| ADD | `extra_model_args` | string | "" | — | — | Additional model args |
| ADD | `limit` | integer | 0 | min:0 | — | 0=all; limits per-task examples |
| ADD | `device` | string | auto | — | — | CUDA device |

**Port changes:** None needed.

**Mismatches:** Only HuggingFace backend hardcoded. No demo mode — crashes if lm_eval not installed. Only `acc`/`acc_stderr` extracted (many tasks produce more metrics).

---

## 2.8 mmlu_eval — MEDIUM

**Current frontend config:** `subjects` (string, "all"), `num_fewshot` (integer, 5)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `batch_size` | string | auto | — | — | Hardcoded in backend |
| ADD | `backend` | select | hf | hf, vllm, gguf | — | lm_eval backend |
| ADD | `limit` | integer | 0 | min:0 | — | Per-subject example limit |
| ADD | `device` | string | auto | — | — | CUDA device |

**Port changes:**
- ADD output: `dataset` (dataset, optional) — Per-subject results

**Mismatches:** Same hard lm_eval dependency. Only HF backend. `seed` and `model_name` in backend but not frontend. Highly similar to lm_eval_harness (could be merged).

---

## 2.9 model_telemetry — MEDIUM

**Current frontend config:** `model_path` (string), `capture_attention` (boolean, true), `capture_activations` (boolean, false), `capture_memory` (boolean, true), `capture_layer_stats` (boolean, true), `sample_size` (integer, 10)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `max_attention_samples` | integer | 3 | min:1 max:10 | — | Attention capture is memory intensive |
| MODIFY | `telemetry` output | artifact | — | — | — | Change from `metrics` to `artifact` — backend saves file path, not dict |

**Port changes:**
- MODIFY output: `telemetry` dataType from `metrics` to `artifact` — Three different types across three definitions (frontend: metrics, backend: file path, block.yaml: data)

**Mismatches:** `dataset` input declared but never read (uses synthetic text instead). `capture_activations` config exists but activation capture not implemented. No MPS memory tracking.

---

## 2.10 toxicity_eval — HIGH

**Current frontend config:** `categories` (string, "toxicity,bias,profanity"), `threshold` (float, 0.5)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `categories` | multiselect | toxicity,obscene,insult | toxicity, severe_toxicity, obscene, threat, insult, identity_attack | — | Change from string to multiselect; use real detoxify categories (bias/profanity don't exist) |
| ADD | `text_column` | string | text | — | — | Backend reads but not in frontend |
| ADD | `seed` | integer | 42 | — | — | Backend reads but not in frontend |
| ADD | `prompt_column` | string | "" | — | — | For model inference mode |

**Port changes:**
- MODIFY input: `model` → required:false — Backend NEVER loads model input
- ADD output: `dataset` (dataset, optional) — Backend saves per-text scores

**Mismatches:** Model input required but never used. `categories` config never read by backend (dead config). Frontend category values (bias, profanity) don't match detoxify outputs.

---

### Evaluation Cross-Cutting Issues
- 6 of 10 blocks have phantom inputs (declared but never read)
- 6 of 10 blocks have undeclared dataset outputs
- 6 of 10 lack block.yaml files
- Inconsistent input loading patterns (ctx.load_input vs ctx.inputs.get)

---

# 3. AGENTS CATEGORY

## 3.1 agent_orchestrator — HIGH

**Current frontend config:** `max_steps` (integer, 50), `strategy` (select: sequential/parallel/adaptive)
**What run.py actually reads:** `max_steps`, `strategy`

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `max_steps` default | integer | 10 | — | — | 50 is too high for default |
| ADD | `system_prompt` | text_area | "" | — | — | System prompt for orchestrator |
| ADD | `provider` | select | ollama | ollama, openai, anthropic | — | LLM provider |
| ADD | `endpoint` | string | http://localhost:11434 | — | — | API endpoint |
| ADD | `model_name` | string | "" | — | — | Model name for inference |
| ADD | `temperature` | float | 0.7 | min:0 max:2 | — | Sampling temperature |

**Port changes:**
- ADD input: `input` (text, optional) — Task description input
- ADD input: `tools` (config, optional) — Tool definitions
- ADD output: `text` (text, optional) — Final agent response

**Mismatches:** No text I/O ports — can't receive tasks or emit responses. max_steps default too high.

---

## 3.2 tool_registry — MEDIUM

**Current frontend config:** `tools` (text_area, JSON tool definitions), `validation` (boolean, true)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `include_defaults` | boolean | true | — | — | Whether to include built-in tools |

**Port changes:**
- MODIFY input: `config` → required:false — Should work standalone
- ADD output: `tools` (config, optional) — Registered tool definitions for downstream agents

**Mismatches:** Config input is required but block should work standalone with inline tool definitions.

---

## 3.3 chain_of_thought — HIGH

**Current frontend config:** `num_steps` (integer, 3), `self_consistency` (boolean, false)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `max_tokens` | integer | 512 | min:64 | — | Max tokens per step |
| ADD | `step_template` | text_area | "" | — | — | Template for each reasoning step |
| ADD | `provider` | select | ollama | ollama, openai, anthropic | — | LLM provider |
| ADD | `endpoint` | string | http://localhost:11434 | — | — | API endpoint |
| ADD | `model_name` | string | "" | — | — | Model name |

**Port changes:**
- ADD input: `input` (text, optional) — Problem/question input
- ADD output: `text` (text, optional) — Final reasoned answer

**Mismatches:** No text I/O ports. `self_consistency` config not implemented in backend.

---

## 3.4 multi_agent_debate — CRITICAL

**Current frontend config:** `num_agents` (integer, 3), `rounds` (integer, 2), `debate_format` (select: free_form/structured/panel)
**What run.py actually reads:** `num_agents`, `num_rounds`, `debate_format`

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `rounds` → `num_rounds` | integer | 2 | — | — | Backend reads `num_rounds`, not `rounds` — RENAME |
| ADD | `seed` | integer | 42 | — | — | Reproducibility |
| ADD | `personas` | text_area | "" | — | — | JSON array of agent persona descriptions |
| ADD | `topic` | text_area | "" | — | — | Debate topic |
| ADD | `provider` | select | ollama | ollama, openai, anthropic | — | LLM provider |
| ADD | `endpoint` | string | http://localhost:11434 | — | — | API endpoint |
| ADD | `model_name` | string | "" | — | — | Model name |

**Port changes:**
- MODIFY input: `dataset` → replace with `input` (text, optional)
- ADD output: `text` (text, optional) — Debate transcript/conclusion

**Mismatches:** `rounds` vs `num_rounds` — user's round setting is silently ignored. No text output port.

---

## 3.5 agent_memory — CRITICAL

**Current frontend config:** `backend` (select: chroma/faiss/simple), `collection_name` (string), `embedding_model` (string)
**What run.py actually implements:** JSON file store with get/set/delete/list operations

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `backend` options | select | simple | simple, json, chroma, faiss | — | Only `simple`/`json` are implemented |
| ADD | `action` | select | store | store, retrieve, clear, list | — | Memory operation to perform |
| ADD | `key` | string | "" | — | — | Memory key for store/retrieve |
| ADD | `value` | text_area | "" | — | — | Value to store |
| ADD | `namespace` | string | default | — | — | Memory namespace/partition |

**Port changes:**
- ADD input: `input` (any, optional) — Data to memorize
- ADD output: `output` (any, optional) — Retrieved memories

**Mismatches:** Entire frontend-backend contract is fiction. Frontend promises ChromaDB/FAISS vector store; backend is a JSON file with key-value operations. `embedding_model` config is dead.

---

## 3.6 agent_evaluator — CRITICAL

**Current frontend config:** `eval_criteria` (select: task_completion/accuracy/efficiency/safety), `pass_threshold` (float, 0.7)
**What run.py actually reads:** `method` (not `eval_criteria`), `pass_threshold`

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `eval_criteria` → `method` | select | task_completion | task_completion, accuracy, efficiency, llm_judge | — | Rename to match backend; add llm_judge |
| ADD | `seed` | integer | 42 | — | — | Reproducibility |

**Port changes:**
- MODIFY input: `agent` → replace with `dataset` (dataset, required) — Backend loads dataset, not agent
- ADD input: `references` (dataset, optional) — Ground truth data
- ADD input: `model` (model, optional) — For LLM-judge method
- ADD output: `dataset` (dataset, optional) — Per-task evaluation results

**Mismatches:** `eval_criteria` vs `method` — evaluation method selection is completely broken. `agent` input declared but backend loads `dataset`.

---

## 3.7 retrieval_agent — MEDIUM

**Current frontend config:** `top_k` (integer, 5), `rerank` (boolean, true), `max_tokens` (integer, 1024)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `prompt_template` | text_area | "" | — | — | RAG prompt template |
| ADD | `provider` | select | ollama | ollama, openai, anthropic | — | LLM provider |
| ADD | `endpoint` | string | http://localhost:11434 | — | — | API endpoint |
| ADD | `model_name` | string | "" | — | — | Model name |

**Port changes:** None needed — inputs/outputs are well-defined.

**Mismatches:** No provider/endpoint config despite being an LLM-powered block.

---

## 3.8 code_agent — HIGH

**Current frontend config:** `language` (select: python/javascript/bash), `timeout` (integer, 30), `sandbox` (boolean, true)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `sandbox` → split | — | — | — | — | Split into `execute` (boolean) + `sandbox` (boolean, depends_on execute) |
| ADD | `task` | text_area | "" | — | — | Task description for the agent |
| ADD | `provider` | select | ollama | ollama, openai, anthropic | — | LLM provider |
| ADD | `endpoint` | string | http://localhost:11434 | — | — | API endpoint |
| ADD | `model_name` | string | "" | — | — | Model name |

**Port changes:**
- ADD input: `input` (text, optional) — Task/problem description
- ADD output: `text` (text, optional) — Generated code/result

**Mismatches:** No text I/O ports. `timeout` config may not be implemented in backend.

---

## 3.9 agent_text_bridge — MEDIUM

**Current frontend config:** `direction` (select: agent_to_text/text_to_agent), `format` (select: json/plain/csv)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `separator` | string | "\\n" | — | — | Text separator for joining |
| ADD | `output_format` | select | text | text, json | — | Output text format |
| ADD | `fallback_field` | string | text | — | — | Field to extract when column detection fails |
| MODIFY | `dataset` input | — | — | — | — | Make optional (not always needed) |

**Port changes:**
- MODIFY input: `dataset` → required:false

**Mismatches:** `timeout` config exists in frontend but may not be implemented. Direction option naming could be clearer.

---

### Agents Cross-Cutting Issues
- 7 of 9 blocks have no block.yaml
- 7 of 9 blocks lack text I/O ports (can't chain in text pipelines)
- No shared LLM inference utility — each block would need provider/endpoint/model_name
- 3 blocks have CRITICAL config name mismatches

---

# 4. OUTPUT CATEGORY

## 4.1 results_formatter — MEDIUM

**Current frontend config:** `format` (select: csv/json/markdown/latex), `include_config` (boolean, true)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `title` | string | Results | — | — | Header title for markdown |
| ADD | `include_timestamp` | boolean | false | — | — | Add timestamp to output |
| MODIFY | block.yaml `format` | — | — | Add `latex` | — | block.yaml missing latex option |

**Port changes:**
- ADD input: `dataset` (dataset, optional) — Format dataset stats alongside metrics
- ADD output: `text` (text, optional) — Chaining to text blocks
- ADD output: `metrics` (metrics, optional) — Pass-through

**Mismatches:** `latex` format not implemented in run.py (silently produces JSON). block.yaml category `flow` vs frontend `metrics`. Markdown mode drops nested dict metrics while CSV flattens them.

---

## 4.2 artifact_packager — HIGH

**Current frontend config:** `output_dir` (file_path), `include_readme` (boolean, true), `compress` (boolean, true)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `compress` | — | — | — | — | IMPLEMENT in run.py — currently dead code, no compression logic exists |
| ADD | `version` | string | 1.0.0 | — | — | Version stamp for manifest |
| ADD | `package_name` | string | "" | — | — | Archive name |

**Port changes:**
- ADD input: `config` (config, optional) — Bundle training hyperparameters
- ADD input: `text` (text, optional) — Model card content
- ADD output: `text` (text, optional) — Manifest content

**Mismatches:** `compress` config is completely dead (frontend declares it, default true, but no run.py logic). `save_artifact("package", output_dir)` is a no-op because context.py only handles files, not directories. Model-as-file not handled.

---

## 4.3 report_generator — CRITICAL

**Current frontend config:** `format` (select: html/pdf/markdown), `include_charts` (boolean, true), `template` (select: default/academic/minimal)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `format` | — | — | — | — | IMPLEMENT html/pdf or remove options — run.py always produces markdown |
| MODIFY | `template` | — | — | — | — | IMPLEMENT styling or remove — run.py never reads this |
| MODIFY | `include_charts` | — | — | — | — | IMPLEMENT or remove — read but no chart generation code |
| ADD | `title` | string | Blueprint Report | — | — | run.py reads but frontend doesn't expose |
| ADD | `sections` | multiselect | summary,metrics,details | summary, metrics, details, config, charts | — | run.py reads but frontend doesn't expose |
| ADD | `include_timestamp` | boolean | true | — | — | run.py reads but frontend doesn't expose |

**Port changes:**
- ADD input: `dataset` (dataset, optional) — run.py tries to load but no port declared
- ADD input: `model` (model, optional) — run.py tries to load but no port declared
- MODIFY: `config` input — declared but never loaded (not in backend's input list)
- ADD output: `text` (text, optional) — Change run.py from "report" (invalid type) to "text"

**Mismatches:** `format`, `include_charts`, `template` are ALL dead config in run.py. 3 config fields exist in run.py but not frontend. run.py tries to load 5 inputs but only 2 declared. `ctx.save_output("report",...)` uses invalid ConnectorType.

---

## 4.4 model_card_writer — CRITICAL

**Current frontend config:** `format` (select: markdown/html), `include_biases` (boolean, true)
**What run.py actually reads:** `model_name`, `base_model`, `language`, `license`, `tags`, `description` (NONE in frontend)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `format` | — | — | — | — | IMPLEMENT html or remove — always produces markdown |
| MODIFY | `include_biases` | — | — | — | — | IMPLEMENT or remove — never read by run.py |
| ADD | `model_name` | string | My Fine-Tuned Model | — | — | run.py reads (line 9) but invisible to users |
| ADD | `base_model` | string | "" | — | — | run.py reads (line 10) but invisible |
| ADD | `language` | select | en | en, es, fr, de, zh, ja, ko, pt, ar, hi, multi | — | run.py reads (line 11) but invisible |
| ADD | `license` | select | apache-2.0 | apache-2.0, mit, cc-by-4.0, gpl-3.0, llama2, llama3, other | — | run.py reads (line 12) but invisible |
| ADD | `tags` | string | text-generation,fine-tuned | — | — | run.py reads (line 13) but invisible |
| ADD | `description` | text_area | "" | — | — | run.py reads (line 14) but invisible |
| ADD | `task_type` | select | text-generation | text-generation, text-classification, translation, summarization, question-answering, other | — | Replace hardcoded task in YAML |
| ADD | `intended_use` | text_area | "" | — | — | Standard model card section |
| ADD | `limitations` | text_area | "" | — | — | Standard model card section |

**Port changes:**
- MODIFY input: `metrics` → required:false — run.py uses try/except, effectively optional
- MODIFY input: `model` → required:false — run.py uses try/except
- ADD input: `dataset` (dataset, optional) — Training data info
- ADD input: `config` (config, optional) — Training config
- ADD output: `text` (text, optional) — run.py saves this but no port declared

**Mismatches:** 6 config fields invisible to users — the most important ones (model_name, license, etc.). `format: html` and `include_biases` not implemented. `text` output saved but not declared. Hardcoded `text-generation` task type. Table formatting bug (missing trailing `|`).

---

## 4.5 leaderboard_publisher — CRITICAL

**Current frontend config:** `target` (select: mlflow/wandb/csv/json), `experiment_name` (string), `tags` (text_area, '{}')
**What run.py actually reads:** `title`, `sort_by`, `sort_order`, `format` (NONE match frontend)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `target` | — | — | — | — | IMPLEMENT mlflow/wandb or remove — run.py never reads this |
| ADD | `output_format` | select | markdown | markdown, csv, json | — | What run.py actually uses as `format` |
| ADD | `title` | string | Model Leaderboard | — | — | run.py reads but invisible |
| ADD | `sort_by` | string | "" | — | — | run.py reads but invisible |
| ADD | `sort_order` | select | descending | descending, ascending | — | run.py reads but invisible |
| ADD | `highlight_best` | boolean | true | — | — | Bold best values |
| ADD | `max_entries` | integer | 0 | min:0 | — | Max entries (0=unlimited) |
| MODIFY | `experiment_name` | — | — | — | {field:'target', value:'mlflow'} | Add depends_on |
| MODIFY | `tags` | — | — | — | {field:'target', value:'mlflow'} | Add depends_on |

**Port changes:**
- ADD input: `metrics_1` (metrics, optional) — run.py loads but no port
- ADD input: `metrics_2` (metrics, optional) — run.py loads but no port
- ADD input: `metrics_3` (metrics, optional) — run.py loads but no port
- ADD input: `dataset` (dataset, optional) — run.py loads but no port
- ADD output: `text` (text, optional) — Leaderboard text
- ADD output: `metrics` (metrics, optional) — run.py saves but no port

**Mismatches:** Entire frontend config describes a different block. Frontend: external publishing (mlflow/wandb). Backend: local table generation. Zero overlap between frontend configs and backend configs. 1 input declared but 8 attempted in run.py.

---

### Output Cross-Cutting Issues
- All 5 blocks have at least one dead frontend config
- 3 of 5 lack block.yaml
- No unified `output` category in frontend (scattered across `metrics` and `model`)
- No `text` output ports declared (preventing chaining)

---

# 5. DATA CATEGORY

## 5.1 huggingface_loader — HIGH

**Current frontend config:** `dataset_name` (string), `split` (select: train/validation/test/all), `max_samples` (integer, 1000)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `hf_token` | string | "" | — | — | HuggingFace API token for private datasets |
| ADD | `subset` | string | "" | — | — | Dataset subset/config name |
| ADD | `streaming` | boolean | false | — | — | Stream instead of downloading full dataset |
| ADD | `columns` | string | "" | — | — | Comma-separated columns to keep |
| ADD | `revision` | string | main | — | — | Dataset revision/branch |
| ADD | `trust_remote_code` | boolean | false | — | — | Allow custom loading scripts |

**Mismatches:** Frontend type name mismatch (registered as different type than run.py expects). Several configs declared but not fully implemented.

---

## 5.2 local_file_loader — MEDIUM

**Current frontend config:** `file_path` (file_path), `format` (select: csv/json/jsonl/parquet/text)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `format` options | — | — | Add xlsx | — | Excel support |
| ADD | `encoding` | string | utf-8 | — | — | File encoding |
| ADD | `skip_rows` | integer | 0 | — | — | Header rows to skip |
| ADD | `max_rows` | integer | 0 | — | — | 0=all rows |
| ADD | `delimiter` | string | "," | — | {field:'format', value:'csv'} | CSV delimiter |
| ADD | `sheet_name` | string | "" | — | {field:'format', value:'xlsx'} | Excel sheet name |

**Mismatches:** Several format-specific options not exposed.

---

## 5.3 api_data_fetcher — CRITICAL

**Current frontend config:** `url` (string), `method` (select: GET/POST), `headers` (text_area, '{}'), `pagination` (boolean, false), `auth_type` (select: none/bearer/api_key)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `method` options | select | GET | GET, POST, PUT, PATCH, DELETE | — | Expand methods |
| MODIFY | `pagination` → split | — | — | — | — | Replace with `max_pages` (integer) + `pagination_key` (string) |
| ADD | `body` | text_area | "" | — | {field:'method', value:'POST'} | Request body |
| ADD | `retry_count` | integer | 3 | — | — | Retries on failure |
| ADD | `rate_limit_ms` | integer | 0 | — | — | Delay between requests |

**Mismatches:** Config key name mismatches between frontend and backend. Auth, retry, rate-limiting configs declared but not implemented.

---

## 5.4 web_scraper — CRITICAL

**Current frontend config:** `url` (string), `selector` (string, "body"), `max_pages` (integer, 1), `follow_links` (boolean, false), `extract_images` (boolean, false), `headers` (text_area), `proxy` (string), `rate_limit` (integer, 1000), `user_agent` (string), `cookies` (text_area), `js_render` (boolean, false), `timeout` (integer, 30), `retry_count` (integer, 3), `output_format` (select: json/csv/markdown), `include_metadata` (boolean, true), `max_depth` (integer, 1), `allowed_domains` (string), `exclude_patterns` (string)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| REMOVE or IMPLEMENT | `follow_links` | — | — | — | — | Dead config — backend never reads |
| REMOVE or IMPLEMENT | `extract_images` | — | — | — | — | Dead config |
| REMOVE or IMPLEMENT | `proxy` | — | — | — | — | Dead config |
| REMOVE or IMPLEMENT | `user_agent` | — | — | — | — | Dead config |
| REMOVE or IMPLEMENT | `cookies` | — | — | — | — | Dead config |
| REMOVE or IMPLEMENT | `js_render` | — | — | — | — | Dead config |
| REMOVE or IMPLEMENT | `retry_count` | — | — | — | — | Dead config |
| REMOVE or IMPLEMENT | `output_format` | — | — | — | — | Dead config |
| REMOVE or IMPLEMENT | `include_metadata` | — | — | — | — | Dead config |
| REMOVE or IMPLEMENT | `max_depth` | — | — | — | — | Dead config |
| REMOVE or IMPLEMENT | `allowed_domains` | — | — | — | — | Dead config |
| REMOVE or IMPLEMENT | `exclude_patterns` | — | — | — | — | Dead config |
| ADD | `rate_limit_ms` | integer | 1000 | — | — | Actual rate limiting |

**Mismatches:** 14 of 18 config fields are dead — backend never reads them. This is the worst offender in the entire codebase.

---

## 5.5 column_transform — CRITICAL

**Current frontend config:** `operations` (text_area, JSON), `column_map` (text_area, JSON)
**What run.py actually reads:** Different config keys

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| REMOVE | `operations` | text_area | — | — | — | Backend reads different keys |
| REMOVE | `column_map` | text_area | — | — | — | Backend reads different keys |
| ADD | `rename_map` | text_area | {} | — | — | JSON: {"old_name": "new_name"} |
| ADD | `drop_columns` | string | "" | — | — | Comma-separated columns to drop |
| ADD | `cast_map` | text_area | {} | — | — | JSON: {"col": "int/float/str"} |
| ADD | `derive_map` | text_area | {} | — | — | JSON: {"new_col": "expression"} |

**Port changes:**
- ADD output: `stats` (metrics, optional) — Column statistics

**Mismatches:** Frontend config key names don't match backend. Complete config name mismatch.

---

## 5.6 data_augmentation — CRITICAL

**Current frontend config:** `method` (select), `factor` (float), `seed` (integer)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `method` options | — | — | Harmonize with backend | — | Frontend and backend method lists differ |
| ADD | `text_column` | string | text | — | — | Column to augment |
| ADD | `label_column` | string | "" | — | — | Preserve labels during augmentation |
| ADD | `target_label` | string | "" | — | — | Only augment specific label |

**Port changes:**
- ADD output: `stats` (metrics, optional) — Augmentation statistics

**Mismatches:** Frontend method names don't match backend options.

---

## 5.7 data_merger — CRITICAL

**Current frontend config:** `method` (select: concat/interleave/join), `shuffle` (boolean)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `method` options | — | — | Add `deduplicate` | — | Common use case |
| ADD | `how` | select | inner | inner, left, outer | {field:'method', value:'join'} | Join type |
| ADD | `column_suffix` | string | "" | — | {field:'method', value:'join'} | Suffix for conflicting columns |

**Mismatches:** Config key name mismatches between frontend and backend.

---

## 5.8 filter_sample — HIGH

**Current frontend config:** `method` (select), `sample_size` (integer), `seed` (integer)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `text_column` | string | text | — | — | Column for text-based filtering |
| ADD | `max_tokens` | integer | 0 | — | — | Max token count filter |
| ADD | `regex_pattern` | string | "" | — | — | Regex filter pattern |
| ADD | `regex_column` | string | "" | — | — | Column for regex matching |
| ADD | `quality_threshold` | float | 0.0 | min:0 max:1 | — | Quality score threshold |
| ADD | `stratify_column` | string | "" | — | — | Column for stratified sampling |

**Mismatches:** Backend implements regex/dedup/quality_score methods not in frontend.

---

## 5.9 text_chunker — MEDIUM

**Current frontend config:** `chunk_size` (integer), `overlap` (integer), `strategy` (select: fixed/sentence/paragraph)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `text_column` | string | text | — | — | Column to chunk |
| ADD | `separator` | string | "" | — | — | Custom separator for splitting |
| MODIFY | `strategy` options | — | — | Add recursive, token | — | Implement recursive/token strategies |

---

## 5.10 text_concatenator — LOW

**Current frontend config:** `separator` (string, "\\n"), `max_length` (integer, 0)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `trim` | boolean | true | — | — | Trim whitespace from each text |

---

## 5.11 text_input — LOW

**Current frontend config:** `text` (text_area)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `from_file` | file_path | "" | — | — | Load text from file instead |
| ADD | `env_interpolation` | boolean | false | — | — | Replace ${ENV_VAR} in text |
| MODIFY | `text` default | — | "" | — | — | Change default to empty |

---

## 5.12 synthetic_data_gen — HIGH

**Current frontend config:** `num_samples` (integer), `template` (text_area), `model` (string)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `output_columns` | string | "" | — | — | Comma-separated output column names |
| ADD | `max_tokens` | integer | 256 | — | — | Max tokens per generated sample |
| ADD | `batch_size` | integer | 10 | — | — | Generation batch size |
| ADD | `dedup_generated` | boolean | true | — | — | Remove duplicate generations |
| ADD | `seed` | integer | 42 | — | — | Random seed |

---

## 5.13 train_val_test_split — LOW

**Current frontend config:** `train_ratio` (float, 0.8), `val_ratio` (float, 0.1), `test_ratio` (float, 0.1), `seed` (integer, 42)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `group_column` | string | "" | — | — | Column for grouped splitting (no group leakage) |
| ADD | `stratify_column` | string | "" | — | — | Column for stratified splitting |

---

## 5.14 data_preview — LOW

**Current frontend config:** `num_rows` (integer, 5), `show_stats` (boolean, true)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `include_text_stats` | boolean | false | — | — | Token length distribution |
| ADD | `include_value_counts` | boolean | false | — | — | Value counts for categorical columns |

**Port changes:**
- ADD output: `dataset` (dataset, optional) — Passthrough for chaining

---

## 5.15 document_ingestion — HIGH

**Current frontend config:** `source_dir` (file_path), `file_types` (string, "pdf,txt,md,docx"), `chunk_size` (integer, 1000), `chunk_overlap` (integer, 200)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| — | All existing | — | — | — | — | IMPLEMENT existing configs — most are dead code |

**Port changes:**
- ADD output: `stats` (metrics, optional) — Ingestion statistics

**Mismatches:** Most existing configs not implemented. PDF reading broken.

---

## 5.16 config_builder — LOW

**Current frontend config:** `config` (text_area, JSON)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `env_interpolation` | boolean | false | — | — | Replace ${ENV_VAR} references |

**Port changes:**
- ADD input: `base_config` (config, optional) — Override/merge with base config

---

## 5.17 config_file_loader — LOW

**Current frontend config:** `file_path` (file_path), `format` (select: json/yaml/toml)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `format` options | — | — | Add .env | — | .env file support |
| ADD | `defaults` | text_area | {} | — | — | Default values as JSON |

---

## 5.18 sql_query — CRITICAL

**Current frontend config:** `query` (text_area), `connection_string` (string)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `db_type` | select | sqlite | sqlite, postgresql, mysql | — | Database type |
| ADD | `timeout` | integer | 30 | — | — | Query timeout |

**Mismatches:** Config key name mismatches. Connection string, parameterized queries, timeout not implemented.

---

## 5.19 vector_store_build — MEDIUM

**Current frontend config:** `backend` (select: chroma/faiss), `embedding_model` (string), `collection_name` (string)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `batch_size` | integer | 100 | — | — | Embedding batch size |
| ADD | `text_column` | string | text | — | — | Column to embed |
| ADD | `persist_directory` | string | "" | — | — | Where to save vector store |
| MODIFY | `backend` options | — | — | Add qdrant | — | Qdrant support |

**Port changes:**
- ADD output: `embeddings` (embedding, optional) — Generated embeddings

---

## 5.20 model_selector — MEDIUM

**Current frontend config:** `source` (select: huggingface/local/ollama), `model_name` (string)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `ollama_url` | string | http://localhost:11434 | — | {field:'source', value:'ollama'} | Ollama endpoint |
| ADD | `cache_dir` | string | "" | — | — | Model cache directory |

**Port changes:**
- ADD input: `config` (config, optional) — Dynamic model selection from config

---

## 5.21-5.24 gguf_model, huggingface_model, mlx_model, ollama_model — CRITICAL

**These 4 blocks have NO frontend registry entry at all.** They exist only as run.py files.

| Action | Notes |
|--------|-------|
| ADD frontend entries | All 4 need complete block-registry.ts definitions |

---

### Data Cross-Cutting Issues
- 6 blocks have CRITICAL config key name mismatches
- 4 blocks have NO frontend registry entry
- 5 blocks have dead input ports
- 15+ blocks have dead config fields
- web_scraper has 14 of 18 dead configs (worst in codebase)
- File format inconsistency between blocks (data.json vs docs.json vs chunks.json)

---

# 6. FLOW CATEGORY

## 6.1 aggregator — CRITICAL

**Current frontend config:** `method` (select: concat/merge/best), `wait_all` (boolean, true)
**What run.py reads:** `strategy` (concatenate/flatten/merge_dicts), `deduplicate`

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `method` → align | — | — | concat, merge_dicts, flatten, best | — | Rename backend `strategy` to `method`; align option values |
| REMOVE | `wait_all` | boolean | true | — | — | No backend implementation |
| ADD | `deduplicate` | boolean | false | — | — | Backend reads but not in frontend |
| ADD | `sort_by` | string | "" | — | — | Field to sort by |
| ADD | `conflict_resolution` | select | last_wins | last_wins, first_wins, error | {field:'method', value:'merge'} | Key conflict handling |

**Port changes:**
- MODIFY: Backend must scan `in_1` through `in_5` — current 13-name list doesn't include ANY frontend port IDs
- MODIFY: Backend output `dataset` → `output` to match frontend
- ADD output: `metrics` (metrics, optional) — Backend saves but no port

**Mismatches:** CRITICAL — Input IDs have ZERO overlap (frontend: in_1-in_5, backend: 13 other names). Output ID mismatch. Config key name mismatch (`method` vs `strategy`). Config option value mismatch.

---

## 6.2 artifact_viewer — LOW

**Current frontend config:** `auto_open` (boolean, true), `display_mode` (select: preview/raw/download)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `max_preview_chars` | integer | 2000 | — | — | Max chars in preview |

**Port changes:**
- ADD output: `artifact_out` (artifact, optional) — Passthrough
- ADD output: `summary` (text, optional) — Backend saves but no port

---

## 6.3 checkpoint_gate — CRITICAL

**Current frontend config:** `save_state` (boolean, true), `pause` (boolean, false), `label` (string, "checkpoint")
**What run.py reads:** `metric`, `threshold`, `operator`, `on_fail`

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| REMOVE | `save_state` | boolean | — | — | — | No backend implementation |
| REMOVE | `pause` | boolean | — | — | — | No backend implementation |
| ADD | `metric` | string | accuracy | — | — | Metric to evaluate |
| ADD | `threshold` | float | 0.8 | — | — | Threshold value |
| ADD | `operator` | select | greater_equal | greater_than, greater_equal, less_than, less_equal, equals, not_equals | — | Comparison operator |
| ADD | `on_fail` | select | block | block, warn | — | Action on gate failure |

**Port changes:**
- ADD input: `metrics` (metrics, required) — Backend tries this first
- ADD output: `gate_result` (metrics, optional) — Backend saves this
- `fail` output — not implemented in backend

**Mismatches:** SEVERE — Entire block identity mismatch. Frontend: "save state and pause". Backend: "metric threshold gate". Zero config field overlap.

---

## 6.4 cloud_compute_provider — MEDIUM

**Current frontend config:** `provider` (select: modal/runpod/baseten/replicate/aws_sagemaker), `api_key` (string), `instance_type` (select: A100G/H100G/L40S/T4/CPU-Only)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `region` | select | us-east-1 | us-east-1, us-west-2, eu-west-1 | — | Cloud region |
| ADD | `max_cost_usd` | float | 0 | — | — | Budget limit |
| ADD | `max_runtime_minutes` | integer | 0 | — | — | Runtime limit |
| ADD | `dry_run` | boolean | false | — | — | Validate without provisioning |

**Mismatches:** Entirely mock implementation. Fake auth tokens. 2.5s of artificial sleep delays.

---

## 6.5 conditional_branch — CRITICAL

**Current frontend config:** `condition` (string, "metric > 0.5"), `metric_key` (string, "accuracy")
**What run.py reads:** `condition`, `field`, `operator`, `value`

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| REMOVE | `metric_key` | string | — | — | — | Replace with `field` |
| ADD | `field` | string | "" | — | — | Field to test |
| ADD | `operator` | select | equals | equals, not_equals, greater_than, less_than, greater_equal, less_equal, contains, not_contains, is_empty, is_not_empty, matches_regex, is_true, is_false | — | 13-operator system |
| ADD | `value` | string | "" | — | — | Value to compare against |
| ADD | `mode` | select | first_row | first_row, filter_partition, all_rows | — | How to apply condition |

**Port changes:**
- MODIFY: Backend outputs `output_a`/`output_b` → must rename to `true_branch`/`false_branch`
- ADD output: `result` (metrics, optional) — Backend saves branch info

**Mismatches:** CRITICAL — Output IDs mismatch (output_a/output_b vs true_branch/false_branch). Rich 13-operator system invisible in UI. `metrics` input declared but never read. `eval()` used for conditions (code injection).

---

## 6.6 control_tower — MEDIUM

**Current frontend config:** `host` (string, "http://localhost"), `port` (integer, 4173)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `auth_token` | string | "" | — | — | Bearer token for auth |
| ADD | `endpoint_path` | string | /api/telemetry | — | — | API endpoint path |
| ADD | `retry_count` | integer | 3 | — | — | Retries on failure |

**Port changes:**
- ADD output: `passthrough` (any, optional) — Forward data
- ADD output: `status` (text, optional) — Send status

---

## 6.7 data_exporter — LOW

**Current frontend config:** `format` (select: json/jsonl/csv/tsv/markdown/latex), `filename` (string), `path` (string), `indent` (integer, 2), `include_metadata` (boolean, false)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `columns` | string | "" | — | — | Columns to include |
| ADD | `compress` | select | none | none, gzip, zip | — | Compression |
| ADD | `overwrite` | boolean | true | — | — | Overwrite existing files |

**Port changes:**
- ADD output: `file` (artifact, optional) — Backend saves but no port

---

## 6.8 embedding_visualizer — MEDIUM

**Current frontend config:** `method` (select: umap/tsne/pca), `dimensions` (select: 2/3), `perplexity` (integer, 30)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `perplexity` | — | — | — | {field:'method', value:'tsne'} | Only applies to t-SNE |
| ADD | `color_field` | string | "" | — | — | Field for coloring points |
| ADD | `max_points` | integer | 5000 | min:100 | — | Random sample if exceeded |
| ADD | `n_neighbors` | integer | 15 | min:2 max:200 | {field:'method', value:'umap'} | UMAP parameter |
| ADD | `min_dist` | float | 0.1 | min:0 max:1 | {field:'method', value:'umap'} | UMAP parameter |
| ADD | `random_state` | integer | 42 | — | — | Random seed |

**Port changes:**
- ADD output: `metrics` (metrics, optional) — Quality metrics

**Mismatches:** `dataset` input declared but NEVER read by backend. `perplexity` shown for all methods.

---

## 6.9 error_handler — HIGH

**Current frontend config:** `retry_count` (integer, 1), `retry_delay` (integer, 5), `on_error` (select: continue/stop/fallback)
**What run.py reads:** `max_retries`, `retry_delay` (float, 1.0), `on_error` (fallback/raise/log), `fallback_value`, `script`

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `retry_count` → align | — | — | — | — | Backend uses `max_retries` — rename backend |
| MODIFY | `on_error` options | — | — | continue→log, stop→raise, fallback→fallback | — | Align option values |
| MODIFY | `retry_delay` | float | 1.0 | — | — | Change type to float, default to 1.0 |
| ADD | `fallback_value` | text_area | {} | — | {field:'on_error', value:'fallback'} | Fallback JSON value |
| ADD | `script` | text_area | "" | — | — | Inline Python to wrap |
| ADD | `backoff_multiplier` | float | 1.0 | min:1 max:10 | — | Exponential backoff |
| ADD | `timeout_seconds` | integer | 300 | — | — | Max execution time |

**Port changes:**
- MODIFY: Backend output `output` → `success` to match frontend
- IMPLEMENT: `fail` output — declared in frontend but never saved by backend

**Mismatches:** Output ID mismatch. Config name mismatch. Option value mismatch. `script` and `fallback_value` invisible.

---

## 6.10 experiment_logger — LOW

**Current frontend config:** `experiment_name` (string, ""), `tags` (string, ""), `log_to_file` (boolean, true)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `experiment_name` default | string | default_experiment | — | — | Align with backend |
| ADD | `notes` | text_area | "" | — | — | Experiment notes |
| ADD | `log_dir` | string | ~/.blueprint/experiments/ | — | — | Persistent directory |
| ADD | `tracking_backend` | select | file | file, mlflow, wandb | — | Where to send data |

**Port changes:**
- ADD input: `dataset` (dataset, optional) — Log which dataset was used
- ADD output: `metrics` (metrics, optional) — Passthrough

---

## 6.11 human_review_gate — HIGH

**Current frontend config:** `review_prompt` (text_area), `auto_approve_after_s` (integer, 0), `require_comment` (boolean, false)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `reviewer` | string | "" | — | — | Assigned reviewer |
| ADD | `review_url` | string | "" | — | — | External review webhook |

**Port changes:**
- ADD output: `rejected_data` (any, optional) — Routing rejected data

**Mismatches:** CRITICAL — Auto-approves everything. `approved = True` unconditionally in else branch. `fail` output not implemented. No actual blocking/pausing mechanism.

---

## 6.12 loop_iterator — HIGH

**Current frontend config:** `mode` (select: count/iterate_rows/until_condition), `count` (integer, 3), `max_iterations` (integer, 100)
**What run.py reads:** `max_iterations` (0), `start_index`, `batch_size`

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `max_iterations` default | integer | 0 | — | — | Backend default is 0 (all) |
| ADD | `start_index` | integer | 0 | min:0 | — | Backend reads but not in frontend |
| ADD | `batch_size` | integer | 1 | min:1 | — | Backend reads but not in frontend |
| IMPLEMENT | `mode` | — | — | — | — | Backend has no mode concept |
| IMPLEMENT | `count` | — | — | — | — | Backend doesn't support count mode |

**Port changes:**
- MODIFY: Backend `item` → only returns last item; needs full list or per-iteration triggering
- `done` output has no backend counterpart
- ADD output: `metrics` (metrics, optional) — Backend saves iteration stats

**Mismatches:** Not a real loop — processes all items in single execution. `mode` and `count` are frontend-only with no backend implementation.

---

## 6.13 notification_sender — MEDIUM

**Current frontend config:** `channel` (select: webhook/desktop/log), `webhook_url` (string), `message_template` (text_area), `include_metrics` (boolean, true)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `webhook_headers` | text_area | {} | — | {field:'channel', value:'webhook'} | Custom HTTP headers |
| ADD | `retry_count` | integer | 0 | min:0 max:5 | {field:'channel', value:'webhook'} | Webhook retries |

**Port changes:**
- ADD output: `passthrough` (any, optional) — Forward trigger data
- IMPLEMENT: `fail` output — declared but never saved

---

## 6.14 parallel_fan_out — CRITICAL

**Current frontend config:** `num_branches` (integer, 2, min:2 max:5)
**What run.py reads:** `num_chunks`, `split_method`

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `num_branches` → align | — | — | — | — | Backend uses `num_chunks` — rename backend |
| ADD | `mode` | select | split | split, broadcast | — | Split vs broadcast |
| ADD | `split_method` | select | equal | equal, round_robin, stratified | {field:'mode', value:'split'} | Split strategy |
| ADD | `stratify_column` | string | "" | — | {field:'split_method', value:'stratified'} | Stratification column |

**Port changes:**
- ADD: `out_4`, `out_5` outputs (both optional) — Config allows up to 5 branches but only 3 ports exist
- CRITICAL: Backend NEVER saves to out_1/out_2/out_3 — saves to `dataset` and `chunks` instead. Must fix.
- ADD output: `metadata` (metrics, optional) — Split statistics

**Mismatches:** CRITICAL — Output IDs completely wrong. Backend saves to `dataset`/`chunks`, frontend expects `out_1`-`out_3`. Config name mismatch (`num_branches` vs `num_chunks`).

---

## 6.15 python_runner — LOW

**Current frontend config:** `script` (text_area), `script_path` (file_path), `trust_level` (select: sandboxed/trusted/system), `timeout_seconds` (integer, 300), `requirements` (string)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| — | block.yaml | — | — | Add trust_level | — | Missing from block.yaml |

**Port changes:**
- ADD: `input_data_2`, `input_data_3` inputs (both any, optional) — Multi-input workflows
- ADD: `output_data_2` output (any, optional) — Multi-output workflows

**Mismatches:** `trust_level` missing from block.yaml. Sandboxed mode very restrictive (no re, datetime, collections). Requirements not auto-installed.

---

## 6.16 results_exporter — MEDIUM

**Current frontend config:** `format` (select: csv/json/jsonl/parquet), `file_name` (string, "results"), `include_metadata` (boolean, true)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `path` | string | ./exports/ | — | — | Export directory |
| ADD | `columns` | string | "" | — | — | Columns to include |
| ADD | `compress` | select | none | none, gzip, zip | — | Compression |

**Port changes:**
- ADD input: `metrics` (metrics, optional) — Include in export
- ADD output: `file` (artifact, optional) — Backend saves but no port

**Mismatches:** Near-duplicate of data_exporter. Consider merging.

---

### Flow Cross-Cutting Issues
- 5 blocks have CRITICAL output ID mismatches (data never flows through wires)
- 4 blocks have `fail` output declared but never implemented
- 10 of 16 lack block.yaml files
- Checkpoint gate has complete identity mismatch (frontend vs backend describe different blocks)
- data_exporter and results_exporter are near-duplicates

---

# 7. INFERENCE CATEGORY

## 7.1 llm_inference — MEDIUM

**Current frontend config:** `backend` (select: ollama/openai/anthropic/local), `model_name` (string), `temperature` (float, 0.7), `max_tokens` (integer, 256), `system_prompt` (text_area)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `top_p` | float | 1.0 | min:0 max:1 | — | Nucleus sampling |
| ADD | `stop_sequences` | string | "" | — | — | Comma-separated stop sequences |
| ADD | `seed` | integer | -1 | — | — | -1=random |
| ADD | `api_key` | string | "" | — | {field:'backend', value:'openai'} | API key for cloud providers |

---

## 7.2 batch_inference — HIGH

**Current frontend config:** `batch_size` (integer), `model_name` (string)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `text_column` | string | text | — | — | Input column |
| ADD | `prompt_template` | text_area | "" | — | — | Template with {text} placeholder |
| ADD | `backend` | select | ollama | ollama, openai, transformers | — | Inference backend |
| ADD | `base_url` | string | http://localhost:11434 | — | — | API endpoint |
| ADD | `batch_delay` | float | 0 | — | — | Delay between batches |
| ADD | `output_column` | string | _response | — | — | Output column name |

**Mismatches:** Config key mismatches between frontend and backend. Missing backend/provider selection.

---

## 7.3 chat_completion — MEDIUM

**Current frontend config:** `model` (string), `system_prompt` (text_area), `temperature` (float, 0.7), `max_tokens` (integer, 512)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `top_p` | float | 1.0 | min:0 max:1 | — | Nucleus sampling |

**Port changes:**
- ADD output: `conversation` (dataset, optional) — Full conversation history

---

## 7.4 structured_output — MEDIUM

**Current frontend config:** `schema` (text_area, JSON), `model` (string), `max_tokens` (integer, 512)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `max_retries` | integer | 3 | — | — | Retries on schema validation failure |
| ADD | `base_url` | string | "" | — | — | API endpoint |

**Port changes:**
- ADD output: `config` (config, optional) — Structured output as config

---

## 7.5 vision_inference — MEDIUM

**Current frontend config:** `model` (string), `prompt` (text_area), `max_tokens` (integer, 256)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `temperature` | float | 0.7 | min:0 max:2 | — | Sampling temperature |
| ADD | `base_url` | string | "" | — | — | API endpoint |

---

## 7.6 function_calling — MEDIUM

**Current frontend config:** `model` (string), `tools` (text_area, JSON), `max_tokens` (integer, 512)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `system_prompt` | text_area | "" | — | — | System prompt for tool use |
| ADD | `base_url` | string | "" | — | — | API endpoint |

---

## 7.7 few_shot_prompting — MEDIUM

**Current frontend config:** `num_examples` (integer, 3), `model` (string), `temperature` (float, 0.7)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `input_column` | string | input | — | — | Column for example inputs |
| ADD | `output_column` | string | output | — | — | Column for example outputs |
| ADD | `example_format` | text_area | "" | — | — | Template for formatting examples |
| ADD | `base_url` | string | "" | — | — | API endpoint |

---

## 7.8 prompt_template — MEDIUM

**Current frontend config:** `template` (text_area), `system_prompt` (text_area)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `variables` | text_area | {} | — | — | Default variable values as JSON |
| MODIFY | `system_prompt` | — | — | — | — | IMPLEMENT or remove — run.py never reads it |

**Port changes:**
- ADD input: `text` (text, optional) — Text to template
- ADD output: `text` (text, optional) — Templated output

---

## 7.9 prompt_chain — MEDIUM

**Current frontend config:** `steps` (text_area, JSON), `model` (string), `temperature` (float, 0.7)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `base_url` | string | "" | — | — | API endpoint |
| ADD | `system_prompt` | text_area | "" | — | — | System prompt for all steps |

---

## 7.10 ab_test_inference — HIGH

**Current frontend config:** `model_a` (string), `model_b` (string), `temperature` (float, 0.7), `num_samples` (integer, 100)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `judge_backend` | select | ollama | ollama, openai | — | Backend for judge model |
| ADD | `judge_model` | string | "" | — | — | Model for automated comparison |

**Port changes:**
- ADD input: `model_b` (model, optional) — Second model for comparison
- ADD input: `dataset` (dataset, optional) — Test prompts

---

## 7.11 token_counter — LOW

**Current frontend config:** `model_name` (string), `tokenizer` (select: auto/tiktoken/sentencepiece)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `text_column` | string | text | — | — | Column to count |
| ADD | `cost_per_1k_tokens` | float | 0 | — | — | Cost estimation |

**Port changes:**
- ADD input: `dataset` (dataset, optional) — Count tokens in dataset
- ADD output: `dataset` (dataset, optional) — Dataset with token counts

---

## 7.12 response_parser — LOW

**Current frontend config:** `format` (select: json/regex/xml), `pattern` (string), `output_field` (string)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `match_index` | integer | 0 | — | — | Which regex match to return |
| MODIFY | `format` options | — | — | Add yaml | — | YAML parsing |

---

## 7.13 model_router — HIGH

**Current frontend config:** `primary_model` (string), `fallback_model` (string), `strategy` (select: primary_first/round_robin/load_balanced)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `primary_base_url` | string | "" | — | — | Primary API endpoint |
| ADD | `fallback_base_url` | string | "" | — | — | Fallback API endpoint |
| ADD | `max_tokens` | integer | 256 | — | — | Max tokens |
| ADD | `temperature` | float | 0.7 | — | — | Temperature |

**Port changes:**
- ADD input: `model_b` (model, optional) — Fallback model

---

## 7.14 guardrails — HIGH

**Current frontend config:** `rules` (text_area, JSON), `action` (select: block/warn/modify), `model` (string)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `custom_patterns` | text_area | "" | — | — | Custom regex patterns for detection |
| ADD | `custom_blocked_words` | string | "" | — | — | Comma-separated blocked words |

**Port changes:**
- ADD input: `model` (model, optional) — Model for advanced guardrail checks

---

## 7.15 embedding_generator — HIGH

**Current frontend config:** `model_name` (string), `batch_size` (integer, 32)
**What run.py reads:** `text_column` / `doc_column` (mismatch)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | align column config | string | text | — | — | Fix text_column vs doc_column mismatch |
| ADD | `provider` | select | sentence-transformers | sentence-transformers, openai, ollama | — | Embedding provider |
| ADD | `base_url` | string | "" | — | — | API endpoint |

**Mismatches:** `text_column` vs `doc_column` config name mismatch. Model input is optional in backend but required in some frontend paths.

---

## 7.16 embedding_similarity_search — MEDIUM

**Current frontend config:** `top_k` (integer, 5), `threshold` (float, 0.0)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `query_text` | text_area | "" | — | — | Query for similarity search |

**Port changes:**
- ADD input: `model` (model, optional) — Embedding model
- ADD output: `text` (text, optional) — Top result text

---

## 7.17 embedding_clustering — MEDIUM

**Current frontend config:** `method` (select: kmeans/dbscan/agglomerative), `n_clusters` (integer, 5)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `eps` | float | 0.5 | min:0.01 | {field:'method', value:'dbscan'} | DBSCAN epsilon |
| ADD | `linkage` | select | ward | ward, complete, average, single | {field:'method', value:'agglomerative'} | Agglomerative linkage |
| ADD | `reduce_dims` | boolean | false | — | — | Reduce to 2D for visualization |

**Port changes:**
- ADD output: `embedding` (embedding, optional) — Cluster centroids

---

## 7.18 reranker — MEDIUM

**Current frontend config:** `model_name` (string), `top_k` (integer, 5)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `normalize_scores` | boolean | true | — | — | Normalize scores to 0-1 |

**Port changes:**
- ADD input: `text` (text, optional) — Query text
- ADD output: `metrics` (metrics, optional) — Reranking statistics

---

## 7.19 text_classifier — HIGH

**Current frontend config:** `labels` (string), `model_name` (string), `multi_label` (boolean, false)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `backend` | select | transformers | transformers, ollama, openai | — | Classification backend |

**Port changes:**
- ADD input: `dataset` (dataset, optional) — Batch classification
- ADD output: `dataset` (dataset, optional) — Classified results

**Mismatches:** `backend`/`provider` config name mismatch between frontend and run.py.

---

## 7.20 text_summarizer — MEDIUM

**Current frontend config:** `max_length` (integer, 150), `model_name` (string)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `backend` | select | transformers | transformers, ollama, openai | — | Summarization backend |
| ADD | `min_length` | integer | 30 | — | — | Minimum summary length |

**Port changes:**
- ADD input: `dataset` (dataset, optional) — Batch summarization

---

## 7.21 text_translator — MEDIUM

**Current frontend config:** `source_lang` (select), `target_lang` (select), `model_name` (string)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `backend` | select | transformers | transformers, ollama, openai | — | Translation backend |
| MODIFY | language lists | — | — | Expand options | — | Add more languages |

**Port changes:**
- ADD input: `dataset` (dataset, optional) — Batch translation
- ADD output: `metrics` (metrics, optional) — Translation metrics

---

## 7.22 streaming_server — MEDIUM

**Current frontend config:** `port` (integer, 8000), `backend` (select: ollama/vllm/tgi)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `host` | string | 0.0.0.0 | — | — | Bind address |
| ADD | `model_name` | string | "" | — | — | Model to serve |
| ADD | `cors_enabled` | boolean | true | — | — | CORS headers |
| ADD | `auto_start` | boolean | true | — | — | Auto-start server |

**Port changes:**
- ADD output: `artifact` (artifact, optional) — Server config/logs

---

## 7.23 quantize_model — MEDIUM

**Current frontend config:** `method` (select: gptq/awq/bnb), `bits` (select: 4/8)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `calibration_dataset` | string | "" | — | — | Dataset name for calibration |
| ADD | `model_name` | string | "" | — | — | Model identifier |

**Port changes:**
- ADD input: `dataset` (dataset, optional) — Calibration data

---

### Inference Cross-Cutting Issues
- 7 blocks are completely demo (no real inference)
- 5 blocks have partial implementations
- 20+ config fields in run.py not exposed in frontend
- 2 CRITICAL config key naming mismatches (backend/provider, column names)
- 17 of 23 lack block.yaml
- No shared LLM utility — every block reimplements provider/endpoint/API key logic

---

# 8. TRAINING CATEGORY

## 8.1 lora_finetuning — MEDIUM

**Current frontend config:** `r` (integer, 8), `alpha` (integer, 16), `dropout` (float, 0.05), `epochs` (integer, 3), `learning_rate` (float, 0.0002), `batch_size` (integer, 4)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `target_modules` | string | "" | — | — | Comma-separated module names |
| ADD | `gradient_accumulation_steps` | integer | 1 | — | — | Gradient accumulation |
| ADD | `warmup_steps` | integer | 0 | — | — | LR warmup |
| ADD | `save_steps` | integer | 500 | — | — | Checkpoint frequency |
| ADD | `fp16` | boolean | true | — | — | Mixed precision |

---

## 8.2 qlora_finetuning — HIGH

**Current frontend config:** `r` (integer, 64), `alpha` (integer, 16), `dropout` (float, 0.05), `bits` (select: 4/8), `epochs` (integer, 3), `learning_rate` (float, 0.0002), `batch_size` (integer, 4)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `r` default | integer | 16 | — | — | Frontend default 64, backend default 16 — sync |
| MODIFY | `alpha` default | integer | 32 | — | — | Frontend default 16, backend default 32 — sync |
| ADD | `double_quant` | boolean | true | — | — | Double quantization |
| ADD | `quant_type` | select | nf4 | nf4, fp4 | — | Quantization type |
| ADD | `target_modules` | string | "" | — | — | Module names |
| ADD | `gradient_accumulation_steps` | integer | 1 | — | — | Gradient accumulation |

**Mismatches:** CRITICAL default mismatches — `r` (64 vs 16) and `alpha` (16 vs 32) between frontend and backend.

---

## 8.3 full_finetuning — MEDIUM

**Current frontend config:** `epochs` (integer, 3), `learning_rate` (float, 0.00005), `batch_size` (integer, 2), `gradient_accumulation` (integer, 4)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `warmup_ratio` | float | 0.1 | min:0 max:1 | — | Warmup ratio |
| ADD | `weight_decay` | float | 0.01 | — | — | Weight decay |
| ADD | `max_grad_norm` | float | 1.0 | — | — | Gradient clipping |
| ADD | `fp16` | boolean | true | — | — | Mixed precision |

---

## 8.4 distillation — CRITICAL

**Current frontend config:** `temperature` (float, 2.0), `alpha` (float, 0.5), `epochs` (integer, 5), `learning_rate` (float, 0.0001)
**Inputs:** `teacher` (model), `student` (model), `dataset` (dataset)
**What run.py reads:** `ctx.load_input("teacher_model")`

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `distillation_type` | select | soft | soft, hard, feature | — | Distillation type |
| ADD | `batch_size` | integer | 4 | — | — | Training batch size |

**Port changes:**
- MODIFY input: `teacher` id → `teacher_model` — Backend reads `teacher_model`, frontend sends `teacher`. Input ID MISMATCH.

**Mismatches:** CRITICAL — `teacher` vs `teacher_model` input ID mismatch. Teacher model data never reaches the backend.

---

## 8.5 rlhf_ppo — CRITICAL

**Current frontend config:** `reward_model` (string), `learning_rate` (float), `epochs` (integer), `batch_size` (integer), `kl_penalty` (float, 0.2)
**Inputs:** `model` (model), `reward_model` (model), `dataset` (dataset)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `ppo_epochs` | integer | 4 | — | — | PPO training epochs |
| ADD | `clip_range` | float | 0.2 | — | — | PPO clip range |
| ADD | `value_coef` | float | 0.5 | — | — | Value loss coefficient |

**Mismatches:** CRITICAL — `reward_model` input port declared but run.py NEVER calls `ctx.load_input("reward_model")`. It reads `reward_model` from config as a string model name instead. The wired reward model connection is silently ignored.

---

## 8.6 dpo_training — MEDIUM

**Current frontend config:** `beta` (float, 0.1), `epochs` (integer, 1), `learning_rate` (float, 0.00005), `batch_size` (integer, 4)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `loss_type` | select | sigmoid | sigmoid, hinge, ipo | — | DPO loss variant |
| ADD | `max_length` | integer | 512 | — | — | Max sequence length |
| ADD | `max_prompt_length` | integer | 256 | — | — | Max prompt length |

---

## 8.7 hyperparameter_sweep — HIGH

**Current frontend config:** `search_space` (text_area, JSON), `num_trials` (integer, 10), `strategy` (select: grid/random/bayesian)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `metric_to_optimize` | string | eval_loss | — | — | Metric to optimize |
| ADD | `direction` | select | minimize | minimize, maximize | — | Optimization direction |
| ADD | `timeout_minutes` | integer | 0 | — | — | 0=unlimited |

**Mismatches:** Uses `ctx.inputs.get()` instead of `ctx.load_input()`. Inconsistent input loading.

---

## 8.8 checkpoint_selector — HIGH

**Current frontend config:** `strategy` (select: best/latest/step), `metric` (string, "eval_loss"), `step` (integer, 0)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| MODIFY | `step` | — | — | — | {field:'strategy', value:'step'} | Add depends_on |
| ADD | `direction` | select | minimize | minimize, maximize | — | Whether lower or higher is better |

**Mismatches:** Import bug — `import math` at line 83 but `math.exp()` used at line 72 (before import). Will crash at runtime.

---

## 8.9 evaluation_runner — MEDIUM

**Current frontend config:** `metrics` (multiselect: accuracy/f1/bleu/rouge/perplexity), `batch_size` (integer, 8)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `max_samples` | integer | 0 | — | — | 0=all samples |
| ADD | `text_column` | string | "" | — | — | Input text column |
| ADD | `label_column` | string | "" | — | — | Label column |

---

## 8.10 adapter_merge — MEDIUM

**Current frontend config:** `method` (select: linear/svd/cat), `weight` (float, 1.0)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `output_name` | string | merged-adapter | — | — | Output model name |
| ADD | `dtype` | select | float16 | float16, bfloat16, float32 | — | Output dtype |

---

## 8.11 data_collator — LOW

**Current frontend config:** `padding` (select: longest/max_length), `max_length` (integer, 512), `truncation` (boolean, true)

| Action | Field | Type | Default | Options | depends_on | Notes |
|--------|-------|------|---------|---------|------------|-------|
| ADD | `pad_to_multiple_of` | integer | 0 | — | — | Pad to multiple for efficiency |
| ADD | `label_pad_token_id` | integer | -100 | — | — | Label padding token |

---

## 8.12 ballast_training — CRITICAL

**No frontend registry entry exists.** This block has a run.py but is completely invisible in the UI.

| Action | Notes |
|--------|-------|
| ADD | Complete block-registry.ts entry needed |

---

### Training Cross-Cutting Issues
- 2 blocks have CRITICAL input ID mismatches (distillation, rlhf_ppo)
- 1 block has no frontend registry entry (ballast_training)
- 1 block has a runtime crash bug (checkpoint_selector math import)
- qlora_finetuning has r/alpha default mismatches
- Inconsistent input loading patterns

---

# 9. CROSS-CUTTING SUMMARY

## Critical Severity Blocks (must fix — fundamentally broken)

| Block | Category | Issue |
|-------|----------|-------|
| dare_merge | Merge | Config keys `drop_rate`/`rescale` vs `weight`/`density` — user config has ZERO effect |
| slerp_merge | Merge | Config key `t` vs `weight` — user slider has ZERO effect |
| ties_merge | Merge | `base` input port NEVER read — defeats TIES's core purpose |
| ab_comparator | Evaluation | 3 model inputs declared, 0 used; loads dataset_a/dataset_b instead |
| multi_agent_debate | Agents | `rounds` vs `num_rounds` — round setting ignored |
| agent_evaluator | Agents | `eval_criteria` vs `method` — evaluation method broken |
| agent_memory | Agents | Frontend promises ChromaDB/FAISS; backend is JSON file |
| report_generator | Output | format/include_charts/template ALL dead config; always produces markdown |
| model_card_writer | Output | 6 most important config fields invisible to users |
| leaderboard_publisher | Output | Entire frontend/backend describe different blocks; zero config overlap |
| web_scraper | Data | 14 of 18 config fields are dead code |
| column_transform | Data | Frontend config keys don't match backend |
| aggregator | Flow | Input IDs have ZERO overlap; output ID mismatch; config name mismatch |
| checkpoint_gate | Flow | Frontend/backend describe different blocks; zero config overlap |
| conditional_branch | Flow | Output IDs mismatch (output_a/output_b vs true_branch/false_branch) |
| parallel_fan_out | Flow | Output IDs completely wrong; config name mismatch |
| distillation | Training | `teacher` vs `teacher_model` input ID mismatch |
| rlhf_ppo | Training | `reward_model` input declared but NEVER loaded by run.py |
| qlora_finetuning | Training | r default 64→16 and alpha default 16→32 mismatches |

## Statistics

| Metric | Count |
|--------|-------|
| Total blocks | 104 |
| Blocks with CRITICAL issues | 19 |
| Blocks with dead config fields | 50+ |
| Blocks with phantom inputs (declared, never read) | 25+ |
| Blocks with undeclared outputs (saved, no port) | 20+ |
| Blocks missing block.yaml | 66 |
| Blocks with no frontend registry entry | 5 (gguf_model, huggingface_model, mlx_model, ollama_model, ballast_training) |
| Config fields to ADD across all blocks | 200+ |
| Config fields to MODIFY | 40+ |
| Config fields to REMOVE | 25+ |
| Input ports to add/modify | 30+ |
| Output ports to add | 40+ |
