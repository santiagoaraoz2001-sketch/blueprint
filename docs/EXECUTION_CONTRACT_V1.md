# Execution Contract V1

**Date:** 2026-03-27
**Status:** Defining the one authoritative meaning of a Blueprint pipeline.

All code paths that interpret a pipeline graph (executor, partial executor, compiler, validators,
config resolver) MUST conform to this contract. Where current code disagrees with this contract,
the contract wins and the code must be updated in Phase 1.

---

## 1. Legal Graph Shapes

### 1a. DAG (Directed Acyclic Graph) — SUPPORTED

A pipeline with no cycles. Nodes execute in topological order (Kahn's algorithm). All features
(config inheritance, partial rerun, compilation, validation) are fully supported.

### 1b. Single-Controller Loop — SUPPORTED

A cycle is legal if and only if:
1. Every strongly connected component (SCC) contains **exactly one** `loop_controller` node
   (block type from `blocks/flow/loop_controller/`).
2. The SCC contains one or more body nodes.
3. There are **feedback edges** from body nodes back to the controller's `feedback` input port.
4. There are **entry edges** from the controller's `body` output port to body nodes.

**Loop semantics:**
- The controller iterates up to `iterations` times (config, default 10, max 10,000).
- Each iteration: controller emits to `body` output → body nodes execute in topological order → last body node output feeds back to `feedback` input.
- Early stopping: if `stop_metric` is configured and the metric exceeds `stop_threshold` (direction: `minimize` or `maximize`), the loop terminates.
- Context management: `clear` resets state each iteration, `retain` keeps accumulated context, `summarize` condenses context.
- Seed behavior: `fixed` uses same seed, `increment` adds iteration number, `random` uses random seed per iteration.

**Example — valid loop graph:**
```
[Data Loader] → [Loop Controller] → [LLM Inference] → [Quality Gate]
                      ↑                                      |
                      └──────── feedback ─────────────────────┘
```
Nodes: `data_loader`, `loop_controller`, `llm_inference`, `quality_gate`
Edges:
- `data_loader.dataset` → `loop_controller.input`
- `loop_controller.body` → `llm_inference.text`
- `llm_inference.response` → `quality_gate.text`
- `quality_gate.metrics` → `loop_controller.feedback` (feedback edge)

### 1c. Illegal Cycle — REJECTED

Any cycle that does not satisfy the single-controller-loop rules above.

**Example — invalid multi-controller cycle:**
```
[Loop Controller A] → [Block X] → [Loop Controller B] → [Block Y]
         ↑                                                    |
         └────────────────────────────────────────────────────┘
```
**Error code:** `E_MULTI_CONTROLLER_CYCLE`
**Message:** "Cycle contains {n} loop controllers; exactly 1 is required."

**Example — cycle with no controller:**
```
[Block A] → [Block B] → [Block C]
     ↑                       |
     └───────────────────────┘
```
**Error code:** `E_UNCONTROLLED_CYCLE`
**Message:** "Pipeline contains a cycle without a loop controller."

---

## 2. Port Compatibility Rules

The **authoritative** port compatibility matrix. Sourced from `frontend/src/lib/block-registry-types.ts`
(the most up-to-date version). The backend validator MUST be updated to match.

### 2a. Canonical Port Types

10 types: `dataset`, `text`, `model`, `config`, `metrics`, `embedding`, `artifact`, `agent`, `llm`, `any`

### 2b. Compatibility Matrix

| Source ↓ \ Target → | dataset | text | model | config | metrics | embedding | artifact | agent | llm | any |
|---------------------|---------|------|-------|--------|---------|-----------|----------|-------|-----|-----|
| **dataset**         | YES     | YES  |       |        |         |           |          |       |     | YES |
| **text**            | YES     | YES  |       |        |         |           |          |       |     | YES |
| **model**           |         |      | YES   |        |         |           |          |       | YES | YES |
| **config**          |         | YES  |       | YES    |         |           |          |       | YES | YES |
| **metrics**         | YES     | YES  |       |        | YES     |           |          |       |     | YES |
| **embedding**       | YES     |      |       |        |         | YES       |          |       |     | YES |
| **artifact**        |         | YES  |       |        |         |           | YES      |       |     | YES |
| **agent**           |         |      |       |        |         |           |          | YES   |     | YES |
| **llm**             |         |      | YES   | YES    |         |           |          |       | YES | YES |
| **any**             | YES     | YES  | YES   | YES    | YES     | YES       | YES      | YES   | YES | YES |

**Key rules:**
- `text→config` is **REMOVED** (was allowed historically, now blocked).
- `model→llm` is **ALLOWED** (model_selector output feeds agent/inference llm input).
- `config→llm` is **ALLOWED** (config objects can satisfy llm_config inputs).
- `llm→model`, `llm→config` are **ALLOWED** (llm type is interchangeable with model/config).
- `any` connects to everything and everything connects to `any`.

### 2c. Port Type Aliases

Legacy port type names resolve to canonical types before compatibility checking:

| Alias | Canonical Type |
|-------|---------------|
| `data` | `dataset` |
| `external` | `dataset` |
| `training` | `model` |
| `intervention` | `any` |
| `checkpoint` | `model` |
| `optimizer` | `config` |
| `schedule` | `config` |
| `api` | `dataset` |
| `file` | `dataset` |
| `cloud` | `config` |
| `llm_config` | `llm` |

---

## 3. Handle Alias Resolution

Blocks may rename output ports across versions. Saved pipelines may reference old port IDs.

**Rule:** When an edge's `sourceHandle` does not match any current output port ID, check the
block's `block.yaml` `outputs[].aliases` list. If the handle matches an alias, resolve to the
canonical port ID.

**Canonical resolution function:** `block_registry.resolve_output_handle(block_type, handle)`

**Migration for renamed ports:**
1. The new port definition in `block.yaml` MUST include the old ID in its `aliases` array.
2. `resolve_output_handle()` returns the canonical ID; the edge is interpreted as if it used the new ID.
3. The frontend's `resolvePort()` does the same for input ports via `PortDefinition.aliases`.

**Example — stale handle:**
```yaml
# block.yaml for llm_inference
outputs:
  - id: response
    label: Response
    dataType: text
    aliases: [output, text, result]  # old port names
```
An edge with `sourceHandle: "output"` resolves to `sourceHandle: "response"`.

---

## 4. Config Precedence

When determining the final value of a config key for a block, the following precedence applies
(highest to lowest):

1. **Local override** — User explicitly set a value in the block's config panel that differs from the schema default.
2. **Bound input value** — A connected input port satisfies the config field (e.g., `model` input port satisfies `model_name` config). Mapping defined in `schema_validator.py:_config_to_port`.
3. **Inherited upstream value** — First upstream value encountered in topological order, via `resolve_configs()`. Only applies to propagation-eligible keys (global keys, category keys, or block-declared `propagate: true` keys).
4. **Workspace default** — For `file_path` fields: workspace root path + field default, if `auto_fill_paths` is enabled.
5. **Schema default** — The `default` value in `block.yaml` config section.

**Connected-input-versus-config example:**
- Block `llm_inference` has config field `model_name` (mandatory).
- If the `model` input port is connected and provides data, the mandatory check for `model_name` is skipped.
- If `model_name` is also explicitly set in config, the config value is used (the block's `run.py` decides which takes priority at runtime).

---

## 5. Cache Reuse Rules

Cache reuse applies only to partial reruns (`partial_executor.py`).

**Fingerprint for cache validity:**
A cached output from a prior run is reusable if:
1. The node's **block type** matches between current and source pipeline definitions.
2. The node is **upstream** of the rerun start node.

**V1 limitations (unsupported — planned for later phases):**
- No content-hash fingerprint: `block_type + version + config + upstream_outputs` fingerprinting is NOT implemented.
- Config changes in upstream nodes are NOT detected — only block type is compared.
- **Error code:** `E_CACHE_STALE` — reserved for future use when fingerprint validation is added.

---

## 6. Partial Rerun Eligibility

### 6a. DAG Pipelines — SUPPORTED
- Any node in a DAG can be selected as the rerun start point.
- All upstream nodes use cached outputs; start node and downstream re-execute.

### 6b. Loop Pipelines — UNSUPPORTED in V1
- Partial rerun is NOT supported for pipelines containing loops.
- **Error code:** `E_PARTIAL_RERUN_LOOP`
- **Message:** "Partial rerun is not supported for pipelines with loop controllers."
- The partial executor uses `_topological_sort()` (no loop detection), which would silently drop loop body nodes.

### 6c. Validation Requirements
- Source run must be `complete` status with non-null `outputs_snapshot`.
- Start node must exist in current pipeline definition.
- Upstream node block types must match between current and source definitions.
- Config overrides must reference existing nodes.

---

## 7. Export Parity Expectations

The compiler generates standalone Python scripts and Jupyter notebooks.

**Two export paths:**
- `compile_pipeline_from_plan()` — **preferred**: reads `execution_order` and `resolved_config` from the planner's `ExecutionPlan`, ensuring exact parity with in-app execution.
- `compile_pipeline_to_python()` — **legacy**: reads raw node config directly (no planner).

**Export formats:**
- `POST /api/pipelines/{id}/export` with `{"format": "python"}` → `.py` script
- `POST /api/pipelines/{id}/export` with `{"format": "jupyter"}` → `.ipynb` notebook

**Pre-flight check:** `GET /api/pipelines/{id}/export/preflight` returns supported features (green), limitations (yellow warnings), and blockers (red errors) before export generation.

**V1 parity (plan-aware path):**
- DAG execution order: MATCHES executor (same topological sort via `ExecutionPlan.execution_order`)
- Config resolution: MATCHES executor (uses `ResolvedNode.resolved_config` from planner)
- Input gathering: MATCHES executor (edge-based, multi-connection → list)
- Port alias resolution: MATCHES executor (same `resolve_output_handle()`)
- Loop execution: NOT SUPPORTED — refused at export time with specific error
- Secrets resolution: NOT SUPPORTED — `$secret:name` references are NOT resolved
- SSE events: NOT SUPPORTED — no progress streaming in exported code
- Artifact storage: NOT SUPPORTED — local filesystem only
- Partial rerun: NOT SUPPORTED — full pipeline execution only

**Error codes for unsupported features in export:**
- `E_EXPORT_NO_LOOPS` — "Exported pipelines do not support loop execution."
- `E_EXPORT_NO_INHERITANCE` — "Exported pipelines do not support config inheritance."
- `E_EXPORT_NO_SECRETS` — "Exported pipelines do not resolve $secret: references."

---

## 8. Loop Semantics

### 8a. Max Iterations
- Hard limit: `MAX_LOOP_ITERATIONS = 10,000` (executor.py line 142)
- User-configurable: `iterations` config field (default 10, min 1, max 10,000)

### 8b. Feedback Edges
- Edges from body nodes TO the loop controller's `feedback` input port.
- Identified by `_detect_loops()` as edges where source is in SCC body and target is controller.
- Removed from the global edge set before topological sort (to break the cycle).

### 8c. Body Ordering
- Body nodes within a loop are topologically sorted (after removing feedback edges).
- Execution is sequential within each iteration.

### 8d. Entry Edges
- Edges FROM the loop controller's `body` output TO body nodes.
- The controller's output becomes the input for the first body node(s) in each iteration.

### 8e. Result Accumulation
- The controller accumulates results from all iterations into a `result` dataset output.
- The controller emits `metrics` with loop performance data.

---

## 9. Error Codes

| Code | Scope | Description |
|------|-------|-------------|
| `E_EMPTY_PIPELINE` | Validation | Pipeline has no blocks |
| `E_DUPLICATE_NODE_ID` | Validation | Two nodes share the same ID |
| `E_UNCONTROLLED_CYCLE` | Validation | Cycle exists without a loop controller |
| `E_MULTI_CONTROLLER_CYCLE` | Validation | Cycle contains more than one loop controller |
| `E_UNKNOWN_BLOCK_TYPE` | Validation | Block type not in registry |
| `E_MISSING_REQUIRED_INPUT` | Validation | Required input port not connected |
| `E_INCOMPATIBLE_PORT` | Validation | Source port type incompatible with target |
| `E_SELF_LOOP` | Validation | Node connected to itself |
| `E_MISSING_CRITICAL_CONFIG` | Validation | Critical config field empty (e.g., model_name) |
| `E_STALE_PORT_HANDLE` | Validation | Edge references non-existent port (warning if alias exists) |
| `E_PARTIAL_RERUN_LOOP` | Partial Rerun | Loops not supported in partial rerun |
| `E_PARTIAL_RERUN_SOURCE_INCOMPLETE` | Partial Rerun | Source run not complete |
| `E_PARTIAL_RERUN_UPSTREAM_MISMATCH` | Partial Rerun | Upstream definitions changed since source run |
| `E_CACHE_STALE` | Cache | Reserved for future fingerprint validation |
| `E_EXPORT_NO_LOOPS` | Export | Loops not supported in export |
| `E_EXPORT_NO_INHERITANCE` | Export | Config inheritance not supported in export |
| `E_EXPORT_NO_SECRETS` | Export | Secret resolution not supported in export |
| `E_BLOCK_TIMEOUT` | Execution | Block exceeded timeout |
| `E_MEMORY_PRESSURE` | Execution | System memory critically low |
| `E_BLOCK_CONFIG_INVALID` | Execution | Config fails schema validation |
| `E_BLOCK_INPUT_MISSING` | Execution | Required input not provided at runtime |

---

## 10. Unsupported in V1

| Feature | Error Code | Expected Phase |
|---------|-----------|---------------|
| Multi-controller loops | `E_MULTI_CONTROLLER_CYCLE` | No current plan |
| Nested loops | `E_MULTI_CONTROLLER_CYCLE` (if in same SCC) | Future |
| Conditional branching (if/else) | — | Future |
| Parallel execution | — | Future |
| Partial rerun with loops | `E_PARTIAL_RERUN_LOOP` | Phase 2+ |
| Export with loops | `E_EXPORT_NO_LOOPS` | Phase 2+ |
| Export with config inheritance | `E_EXPORT_NO_INHERITANCE` | Phase 2+ |
| Content-hash cache fingerprinting | `E_CACHE_STALE` | Phase 1+ |
| Backend port compatibility enforcement at execution time | — | Phase 1 |
