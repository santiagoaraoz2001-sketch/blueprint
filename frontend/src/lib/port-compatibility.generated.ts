// ──────────────────────────────────────────────────────────────────
// AUTO-GENERATED from docs/PORT_COMPATIBILITY.yaml — DO NOT EDIT
// Regenerate: python3 scripts/generate_port_compat.py
// ──────────────────────────────────────────────────────────────────

/** Backward-compat aliases — map old type names to current 10-type system. */
export const PORT_TYPE_ALIASES: Record<string, string> = {
  api             : 'dataset',
  checkpoint      : 'model',
  cloud           : 'config',
  data            : 'dataset',
  external        : 'dataset',
  file            : 'dataset',
  intervention    : 'any',
  llm_config      : 'llm',
  model_path      : 'model',
  optimizer       : 'config',
  schedule        : 'config',
  training        : 'model',
}

/** Port compatibility matrix — source type → set of allowed target types. */
export const COMPAT: Record<string, Set<string>> = {
  dataset     : new Set(['dataset', 'text', 'any']),
  text        : new Set(['text', 'dataset', 'any']),
  model       : new Set(['model', 'llm', 'any']),
  config      : new Set(['config', 'text', 'llm', 'any']),
  metrics     : new Set(['metrics', 'dataset', 'text', 'any']),
  embedding   : new Set(['embedding', 'dataset', 'any']),
  artifact    : new Set(['artifact', 'text', 'any']),
  agent       : new Set(['agent', 'any']),
  llm         : new Set(['llm', 'model', 'config', 'any']),
  number      : new Set(['number', 'text', 'metrics', 'any']),
  boolean     : new Set(['boolean', 'config', 'any']),
  file_path   : new Set(['file_path', 'text', 'artifact', 'any']),
  any         : new Set(['any', 'dataset', 'text', 'model', 'config', 'metrics', 'embedding', 'artifact', 'agent', 'llm', 'number', 'boolean', 'file_path']),
}

