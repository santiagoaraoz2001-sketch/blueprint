// block-registry-types.ts — Hand-maintained type definitions and utility functions
// The BLOCK_REGISTRY data is auto-generated in block-registry.generated.ts
// Lookup helpers (getBlocksByCategory, getBlockDefinition) live in block-registry.ts

import { CONNECTOR_COLORS } from './design-tokens'

/** The 10 wire types that flow between blocks */
export type ConnectorType =
  | 'dataset'     // structured tabular data (DataFrames, HF datasets, rows/columns)
  | 'text'        // raw text, prompts, strings, documents
  | 'model'       // model weights, adapters, checkpoints
  | 'config'      // configuration objects, hyperparameters, settings
  | 'metrics'     // evaluation scores, loss values, benchmark results
  | 'embedding'   // vector embeddings, dense representations
  | 'artifact'    // files, reports, packages, exported assets
  | 'agent'       // autonomous agent instances
  | 'llm'         // LLM provider config (model info dict or full llm_config)
  | 'any'         // accepts anything (generic utilities, interventions)

/** Backward compat alias */
export type PortType = ConnectorType | string

export interface PortDefinition {
  id: string
  label: string
  dataType: PortType
  required: boolean
  aliases?: string[]  // Additional port IDs this port accepts connections from
}

export interface ConfigField {
  name: string
  label: string
  type: 'string' | 'integer' | 'float' | 'boolean' | 'select' | 'multiselect' | 'file_path' | 'text_area'
  default?: any
  min?: number
  max?: number
  options?: string[]
  description?: string
  depends_on?: { field: string; value: any }
}

export type BlockMaturity = 'stable' | 'beta' | 'experimental'

export interface BlockDetail {
  format?: string
  formatEditable?: boolean
  codePreview?: string
  tips?: string[]
  useCases?: string[]
  howItWorks?: string
}

export interface BlockDefinition {
  type: string
  name: string
  description: string
  category: string
  tags: string[]
  aliases: string[]
  icon: string
  accent: string
  maturity: BlockMaturity
  inputs: PortDefinition[]
  outputs: PortDefinition[]
  defaultConfig: Record<string, any>
  configFields: ConfigField[]
  detail?: BlockDetail
  deprecated?: boolean
  deprecatedMessage?: string
  recommended?: boolean
}

/** Backward-compat aliases — map old type names to new 10-type system */
const PORT_TYPE_ALIASES: Record<string, string> = {
  data:         'dataset',     // old catch-all → dataset
  external:     'dataset',     // old external → dataset
  training:     'model',       // old training output → model
  intervention: 'any',         // old intervention → any (pass-through)
  // Sub-type aliases for backward compat with saved pipelines
  checkpoint:   'model',
  optimizer:    'config',
  schedule:     'config',
  api:          'dataset',
  file:         'dataset',
  cloud:        'config',
  llm_config:   'llm',         // old type name → new llm type
}

/** Get port color from CONNECTOR_COLORS map (handles legacy port types) */
export function getPortColor(dataType: ConnectorType | string): string {
  const resolved = PORT_TYPE_ALIASES[dataType] || dataType
  return CONNECTOR_COLORS[resolved] || CONNECTOR_COLORS.dataset
}

/**
 * Strict port compatibility matrix with smart coercion.
 *
 * SOURCE     → CAN CONNECT TO
 * dataset    → dataset, text, any
 * text       → text, dataset, any                (REMOVED config — no more text→config)
 * model      → model, llm, any                   (ADDED llm — model_selector→agent works)
 * config     → config, text, llm, any             (ADDED llm — config→llm for llm_config outputs)
 * metrics    → metrics, dataset, text, any
 * embedding  → embedding, dataset, any
 * artifact   → artifact, text, any
 * agent      → agent, any
 * llm        → llm, model, config, any            (accepts model AND config)
 * any        → ALL TYPES
 */
const COMPAT: Record<string, Set<string>> = {
  dataset:   new Set(['dataset', 'text', 'any']),
  text:      new Set(['text', 'dataset', 'any']),
  model:     new Set(['model', 'llm', 'any']),
  config:    new Set(['config', 'text', 'llm', 'any']),
  metrics:   new Set(['metrics', 'dataset', 'text', 'any']),
  embedding: new Set(['embedding', 'dataset', 'any']),
  artifact:  new Set(['artifact', 'text', 'any']),
  agent:     new Set(['agent', 'any']),
  llm:       new Set(['llm', 'model', 'config', 'any']),
  any:       new Set(['any', 'dataset', 'text', 'model', 'config', 'metrics', 'embedding', 'artifact', 'agent', 'llm']),
}

export function isPortCompatible(source: ConnectorType | string, target: ConnectorType | string): boolean {
  const s = (PORT_TYPE_ALIASES[source] || source) as string
  const t = (PORT_TYPE_ALIASES[target] || target) as string
  return COMPAT[s]?.has(t) ?? false
}

/** Check if a source port can connect to a target port (type compatibility + alias awareness) */
export function canConnect(sourcePort: PortDefinition, targetPort: PortDefinition): boolean {
  return isPortCompatible(sourcePort.dataType, targetPort.dataType)
}

/** Get all IDs a port responds to: its own id plus any aliases */
export function getPortAliases(port: PortDefinition): string[] {
  return [port.id, ...(port.aliases || [])]
}

/** File extension → expected port types mapping for format warnings */
export const FILE_FORMAT_COMPAT: Record<string, ConnectorType[]> = {
  // Dataset formats
  '.csv': ['dataset'], '.tsv': ['dataset'], '.jsonl': ['dataset'],
  '.parquet': ['dataset'], '.xlsx': ['dataset'], '.arrow': ['dataset'],
  // Text formats
  '.txt': ['text', 'dataset'], '.md': ['text'], '.rst': ['text'],
  '.html': ['text', 'dataset'],
  // Model formats
  '.safetensors': ['model'], '.bin': ['model'], '.gguf': ['model'],
  '.pt': ['model'], '.pth': ['model'], '.onnx': ['model'],
  // Config formats
  '.json': ['dataset', 'config', 'text'], '.yaml': ['config', 'text'],
  '.yml': ['config', 'text'], '.toml': ['config', 'text'],
  // Embedding formats
  '.npy': ['embedding', 'dataset'], '.hdf5': ['embedding', 'dataset'],
  // Artifact formats
  '.pdf': ['artifact', 'text'], '.tar.gz': ['artifact'], '.zip': ['artifact'],
}

/** Check if a file extension is compatible with a block's expected output type */
export function getFileFormatWarning(filePath: string, expectedType: ConnectorType): string | null {
  const ext = filePath.match(/\.[^.]+$/)?.[0]?.toLowerCase()
  if (!ext || !FILE_FORMAT_COMPAT[ext]) return null
  if (FILE_FORMAT_COMPAT[ext].includes(expectedType)) return null
  const expected = FILE_FORMAT_COMPAT[ext].join(', ')
  return `File "${ext}" is typically used for ${expected} data, but this block expects ${expectedType}. The pipeline may produce unexpected results.`
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//  DYNAMIC BLOCK SIZING
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

const PORT_SLOT_WIDTH = 56
const MIN_BLOCK_WIDTH = 280
const MAX_BLOCK_WIDTH = 560

/** Compute block width based on number of ports */
export function computeBlockWidth(def: BlockDefinition): number {
  const maxPorts = Math.max(def.inputs.length, def.outputs.length, 1)
  return Math.min(MAX_BLOCK_WIDTH, Math.max(MIN_BLOCK_WIDTH, maxPorts * PORT_SLOT_WIDTH))
}
