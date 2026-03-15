# Port Naming Convention

## Standard Port IDs

| Semantic | Primary ID | Standard Aliases |
|----------|-----------|-----------------|
| Text content | `text` or `response` | `[text, response, output]` |
| Dataset (tabular) | `dataset` or descriptive | `[dataset]` |
| Model reference | `model` or descriptive | `[model]` |
| Trained model | `trained_model` or descriptive | `[model]` |
| Metrics | `metrics` or descriptive | `[metrics]` |
| LLM config | `llm_config` | `[llm, llm_config]` |

## Rules

1. **Input ports** use short generic names: `dataset`, `model`, `text`, `prompt`
2. **Output ports** use descriptive names when they transform data: `filtered_dataset`, `trained_model`, `parsed_text`
3. **Aliases** always include the generic form so auto-wiring can find them
4. Port `id` never changes after release (backward compatibility)
5. New semantic connections go through aliases, not ID renames

## Text Output Ports

Blocks outputting text content use one of two port IDs:

- `response` — used by LLM/agent blocks (llm_inference, prompt_chain, etc.)
  - Must have `aliases: [text, output]`
- `text` — used by text-processing blocks (prompt_template, guardrails, etc.)
  - Must have `aliases: [response, output]`

This ensures any downstream block expecting either `text` or `response` can auto-wire to either.

## Metrics Output Ports

Blocks outputting metrics use one of several port IDs:

- `metrics` — standard name (no aliases needed)
- `summary` — used by endpoint/export blocks
  - Must have `aliases: [metrics]`
- `stats` — used by data-processing blocks
  - Must have `aliases: [metrics]`
- `gate_metrics` — used by gate blocks
  - Must have `aliases: [metrics]`
- `status` — used by notification blocks (when data_type is metrics)
  - Must have `aliases: [metrics]`

## Dataset Output Ports

When a block produces a transformed dataset with a descriptive name (e.g., `preview`, `rejected`, `train`, `val`, `test`), it must include `aliases: [dataset]` so downstream blocks can discover it via auto-wiring.

## Adding a New Block

When creating a new block:

1. Choose a port ID from the standard set above, or use a descriptive name
2. If using a descriptive name, add aliases that include the generic form
3. Match `data_type` to the appropriate connector type
4. Run `python scripts/generate_block_registry.py` to update the registry
