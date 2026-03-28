# Baseline Audit — Graph Interpreters

**Date:** 2026-03-27
**Scope:** Every code path that reads, interprets, or decides something about a pipeline graph.

---

## 1. Backend Executor — `_topological_sort()`

- **File:** `backend/engine/executor.py`
- **Function:** `_topological_sort(nodes, edges)` — line 115
- **Decides:** Execution order for DAG nodes (Kahn's algorithm).
- **Algorithm:** Builds in-degree map and adjacency list. BFS from zero in-degree nodes.
- **Returns:** `list[str]` of node IDs in execution order.
- **Note:** Silently drops nodes involved in cycles (they never reach in-degree 0). Does NOT raise on cycles — the caller must compare `len(order)` vs `len(nodes)` to detect missing nodes.

### 1a. Backend Executor — `_detect_loops()`

- **File:** `backend/engine/executor.py`
- **Function:** `_detect_loops(nodes, edges)` — line 154
- **Decides:** Whether cycles in the graph are legal single-controller loops or illegal.
- **Algorithm:** Two-phase: (1) Kahn's to find cyclic node set, (2) iterative Kosaraju's SCC to partition cycles.
- **Validation:** Each SCC must contain exactly 1 `loop_controller` node. Raises `ValueError` otherwise.
- **Returns:** `list[LoopDefinition]` with controller_id, body_node_ids, feedback_edges, entry_edges.

### 1b. Backend Executor — `_topological_sort_with_loops()`

- **File:** `backend/engine/executor.py`
- **Function:** `_topological_sort_with_loops(nodes, edges, loops)` — line 303
- **Decides:** Execution order after removing feedback edges to break legal cycles.
- **Algorithm:** Removes feedback edges from each LoopDefinition, then calls `_topological_sort()`.

### 1c. Backend Executor — `execute_pipeline()`

- **File:** `backend/engine/executor.py`
- **Function:** `execute_pipeline(pipeline_id, run_id, definition, db, *, project_id)` — line 1107
- **Decides:** Full pipeline execution orchestration.
- **Graph interpretation:**
  - Calls `_detect_loops()` at ~line 1212
  - Calls `_topological_sort_with_loops()` at ~line 1213
  - Calls `resolve_configs()` at ~line 1225 (config inheritance)
  - Skips `groupNode` visual nodes
  - Skips loop body nodes (handled by `_execute_loop()`)
  - For loop controllers: delegates to `_execute_loop()`
  - For regular nodes: gathers inputs from edges, resolves output handle aliases via `resolve_output_handle()`, executes block
  - Multiple connections to same handle: converts single value to list
  - Applies `CONFIG_MIGRATIONS` for aliased blocks (~line 1301)

### 1d. Backend Executor — `_execute_loop()`

- **File:** `backend/engine/executor.py`
- **Function:** `_execute_loop(...)` — line 711
- **Decides:** Loop body execution order, iteration count, early stopping, feedback routing.
- **Graph interpretation:**
  - Uses pre-sorted body_node_ids from `_detect_loops()`
  - Iterates up to `MAX_LOOP_ITERATIONS` (10,000)
  - Routes feedback port output back to controller
  - Stop condition: metric exceeds threshold

---

## 2. Partial Executor — `execute_partial_pipeline()`

- **File:** `backend/engine/partial_executor.py`
- **Function:** `execute_partial_pipeline(...)` — line 90
- **Decides:** Which nodes to re-execute vs cache from a prior run.
- **Graph interpretation:**
  - Imports `_topological_sort` from executor.py (line 22) — uses simple DAG sort, **no loop detection**
  - Calls `_get_downstream_nodes()` (line 43) for BFS from start node
  - Upstream nodes: reuse cached `outputs_snapshot` from source run
  - Downstream nodes: execute fresh
  - **Does NOT call `resolve_configs()`** — uses node config directly
  - **Does NOT apply `CONFIG_MIGRATIONS`** for aliased blocks
  - **Does NOT validate upstream definitions beyond block type matching** (line 62)

### Disagreements with Executor:
| Aspect | `executor.py` | `partial_executor.py` |
|--------|---------------|----------------------|
| Loop detection | Yes (`_detect_loops`) | No |
| Config inheritance | Yes (`resolve_configs`) | No |
| Config migrations | Yes (`CONFIG_MIGRATIONS`) | No |
| Port alias resolution | Yes (`resolve_output_handle`) | Yes (shared import) |
| Memory pressure | Per-node + per-loop-iteration | Per-loop-iteration only |

---

## 3. Compiler — `compile_pipeline_to_python()`

- **File:** `backend/engine/compiler.py`
- **Function:** `compile_pipeline_to_python(pipeline_name, definition)` — line 7
- **Decides:** Python code generation from pipeline graph.
- **Graph interpretation:**
  - Calls `_topological_sort()` (imported from executor) — line 15. **No loop detection.**
  - Pre-scans for missing blocks (lines 18-31)
  - Skips `groupNode` / `stickyNote` visual nodes
  - Resolves output handle aliases at compile time via `resolve_output_handle()` (line ~179)
  - Multiple connections to same handle → list aggregation (same logic as executor)
  - **Does NOT call `resolve_configs()`** — bakes in node-local config only
  - **Does NOT handle loops** — generates linear execution for all nodes

### Disagreements with Executor:
| Aspect | `executor.py` | `compiler.py` |
|--------|---------------|--------------|
| Loop handling | Full loop execution | Ignored — treats loop body as normal nodes |
| Config inheritance | Yes | No |
| Config migrations | Yes | No |
| Error handling | Try/except per block with typed errors | Try/except per block, generic |

---

## 4. Config Resolver — `resolve_configs()`

- **File:** `backend/engine/config_resolver.py`
- **Function:** `resolve_configs(nodes, edges, topo_order, find_block_dir_fn)` — line 235
- **Decides:** Config key inheritance across the DAG.
- **Graph interpretation:**
  - Walks DAG in topological order (input `topo_order` from executor)
  - Builds per-node `propagation_pool` from upstream nodes (line ~334)
  - **First upstream wins** — takes FIRST value encountered in topo order (line ~336)
  - Override detection: value differs from schema default → treated as user override, NOT replaced
  - Propagation keys: GLOBAL (`text_column`, `seed`, `trust_remote_code`) + per-category (`temperature`, `max_tokens`, etc.) + block-declared (`propagate: true` in block.yaml)
  - Workspace auto-fill: injects absolute paths for `file_path` fields BEFORE propagation (line ~306)
  - Returns `{node_id: resolved_config}` with `_inherited` provenance metadata

### Disagreements:
- Only called by `executor.py`. **Not called by** `partial_executor.py` or `compiler.py`.
- Config inheritance is invisible to partial reruns — a downstream block may get different config.

---

## 5. Backend Validator — `validate_pipeline()`

- **File:** `backend/engine/validator.py`
- **Function:** `validate_pipeline(definition)` — line 95
- **Decides:** Pre-run validation verdict (valid/invalid), cycle detection, port compatibility, config completeness.
- **Graph interpretation:**
  - Cycle detection: iterative DFS with WHITE/GRAY/BLACK coloring (lines 138-178). **Different algorithm from executor** (Kahn's+Kosaraju). Does NOT distinguish legal loops from illegal cycles.
  - Port compatibility: uses `COMPAT` set of `(src, tgt)` tuples (line 44) + `_PORT_TYPE_ALIASES` (line 59).
  - Required ports: checks connected target handles (line 197-206)
  - Config validation: checks `CRITICAL_CONFIG_FIELDS` (line 86), deep schema validation via `get_block_config_schema()` (line 280)
  - Port existence: warns on edges referencing non-existent ports (line 319)
  - Runtime estimation: by category (line 338)

### Port Compatibility Drift (CRITICAL):

**Backend `COMPAT` (validator.py line 44) is a set of tuples:**
```
text→config: ALLOWED     (("text", "config") in COMPAT)
model→llm:   MISSING     (no ("model", "llm") tuple)
config→llm:  MISSING     (no ("config", "llm") tuple)
llm→model:   MISSING     (no ("llm", "model") tuple)
llm→config:  MISSING     (no ("llm", "config") tuple)
llm→llm:     MISSING     (no ("llm", "llm") tuple)
```

**Frontend `COMPAT` (block-registry-types.ts line 123) is a Record of Sets:**
```
text→config: REMOVED     (not in text's Set)
model→llm:   ALLOWED     (in model's Set)
config→llm:  ALLOWED     (in config's Set)
llm→model:   ALLOWED     (in llm's Set)
llm→config:  ALLOWED     (in llm's Set)
llm→llm:     ALLOWED     (in llm's Set)
```

**Summary of drift between backend validator and frontend:**

| Connection | Frontend | Backend Validator | Status |
|-----------|----------|-------------------|--------|
| `text→config` | BLOCKED | ALLOWED | **DRIFT** — frontend removed, backend still allows |
| `model→llm` | ALLOWED | BLOCKED | **DRIFT** — frontend added, backend missing |
| `config→llm` | ALLOWED | BLOCKED | **DRIFT** — frontend added, backend missing |
| `llm→llm` | ALLOWED | BLOCKED | **DRIFT** — backend has no llm type at all |
| `llm→model` | ALLOWED | BLOCKED | **DRIFT** — backend has no llm type at all |
| `llm→config` | ALLOWED | BLOCKED | **DRIFT** — backend has no llm type at all |
| `llm_config` alias | N/A | MISSING | Backend `_PORT_TYPE_ALIASES` lacks `llm_config→llm` |

**Backend `_PORT_TYPE_ALIASES` is also missing `llm_config: "llm"` which frontend has.**

---

## 6. Schema Validator — `validate_config()` / `validate_inputs()`

- **File:** `backend/engine/schema_validator.py`
- **Function:** `validate_config(schema, config, inputs)` — line 70
- **Function:** `validate_inputs(schema, inputs)` — line 37
- **Decides:** Per-block config/input validity at execution time.
- **Graph interpretation:**
  - Input-port-aware: if input port provides value, skips mandatory config check (line 111-118, `_config_to_port` mapping line 98)
  - Type validation: integer rejects bool, float rejects bool and checks NaN/Inf, select checks options
  - Bounds: min/max on numeric fields
  - Called by executor per-block BEFORE `_load_and_run_block()`
  - **Not a graph interpreter per se** but makes graph-dependent decisions (input satisfaction skips config requirement)

---

## 7. Block Registry — `resolve_output_handle()` / `scan_blocks()`

- **File:** `backend/engine/block_registry.py`
- **Function:** `resolve_output_handle(block_type, handle)` — line 136
- **Function:** `scan_blocks()` — line 17
- **Decides:** Block discovery, output port alias resolution.
- **Graph interpretation:**
  - `resolve_output_handle()`: maps old port IDs → canonical IDs via block.yaml aliases
  - Used by executor (line ~1438), compiler (line ~179), partial_executor (imported)
  - `scan_blocks()`: discovers blocks in `blocks/` directory, caches result
  - `get_block_config_schema()`: returns config section from block.yaml (used by validator)

---

## 8. Frontend Client Validator — `validatePipelineClient()`

- **File:** `frontend/src/lib/pipeline-validator.ts`
- **Function:** `validatePipelineClient(nodes, edges, hardware?)` — line 193
- **Decides:** Client-side validation before Run button is enabled.
- **Graph interpretation:**
  - Cycle detection: recursive DFS with `visited` + `stack` sets (lines 76-111). Returns cycle path or null.
  - **Does NOT distinguish legal loops from illegal cycles** — any cycle is an error.
  - Port compatibility: uses `isPortCompatible()` from block-registry-types.ts (line ~387)
  - Required inputs: checks connected edges per node (line ~294)
  - Config validation: `CRITICAL_CONFIG` map + `validateConfigField()` (lines 307-353)
  - Hardware feasibility: peak memory vs available RAM (lines 437-452)
  - Performance: `estimatePipeline()` for runtime/memory estimation (line ~435)

### Disagreements with Backend Validator:
| Aspect | Frontend `validatePipelineClient` | Backend `validate_pipeline` |
|--------|----------------------------------|---------------------------|
| Cycle detection | Recursive DFS | Iterative DFS (WHITE/GRAY/BLACK) |
| Loop awareness | None — all cycles are errors | None — all cycles are errors |
| Port compat matrix | 10-type COMPAT with llm type | Tuple-set COMPAT missing llm |
| text→config | BLOCKED | ALLOWED |
| model→llm | ALLOWED | BLOCKED |
| Hardware checks | Yes (memory, GPU) | No |
| Performance estimation | Yes (per-block with scaling) | Yes (per-category rough) |
| Deep config validation | Yes (type/bounds/select) | Yes (type/bounds/select) |

---

## 9. Frontend `isPortCompatible()` — Sole Port Compatibility Authority

- **File:** `frontend/src/lib/block-registry-types.ts`
- **Function:** `isPortCompatible(source, target)` — line 136
- **Decides:** Whether a connection between two port types is allowed.
- **Used by:** Canvas connection validation, `validatePipelineClient()`, `canConnect()`, `findBestInputPort()`
- **No backend equivalent enforced at execution time.** The executor trusts edges as given.

---

## 10. Frontend Pipeline Estimator

- **File:** `frontend/src/lib/pipeline-estimator.ts`
- **Function:** `estimatePipeline(nodes, hardware?)` — line 248
- **Decides:** Runtime estimation, memory feasibility per block.
- **Graph interpretation:** None — assumes sequential execution of all blocks. Does NOT analyze edges or dependencies.

---

## 11. Frontend Pipeline Store — Graph Operations

- **File:** `frontend/src/stores/pipelineStore.ts`
- **Functions:** `getUpstreamNodes()`, `getDownstreamNodes()`, config inheritance overlay
- **Decides:** UI-level graph traversal for re-run mode, config inheritance display.
- **Graph interpretation:**
  - BFS upstream/downstream from a node
  - `INHERITABLE_KEYS` / `INHERITANCE_DENY_LIST` for UI config inheritance visualization
  - `CONFIG_PROPAGATION_HANDLES` for which edge types carry config
  - Calls backend `/resolve-config` API for actual resolution

---

## Summary: Who Decides What

| Decision | Authoritative Source | Also Decided By (may disagree) |
|----------|---------------------|-------------------------------|
| Execution order (DAG) | `executor._topological_sort()` | `partial_executor` (same fn), `compiler` (same fn) |
| Execution order (loops) | `executor._detect_loops()` + `_topological_sort_with_loops()` | Nobody else handles loops |
| Cycle = legal loop? | `executor._detect_loops()` | `validator.validate_pipeline()` (all cycles = error), `validatePipelineClient()` (all cycles = error) |
| Port compatibility | `block-registry-types.ts:isPortCompatible()` (frontend) | `validator.py:_port_compatible()` (backend, DRIFTED) |
| Config inheritance | `config_resolver.resolve_configs()` | Nobody else (partial_executor/compiler skip it) |
| Config validity | `schema_validator.validate_config()` (execution time) | `validator.validate_pipeline()` (pre-run), `validatePipelineClient()` (client) |
| Block discovery | `block_registry.scan_blocks()` | `executor._find_block_module()` (searches more dirs + aliases + plugins) |
| Output port aliases | `block_registry.resolve_output_handle()` | Used by executor, compiler, partial_executor |
| Cache reuse | `partial_executor` (upstream outputs from source run) | No fingerprint verification beyond block type match |
| Hardware feasibility | `validatePipelineClient()` (frontend only) | No backend equivalent |
