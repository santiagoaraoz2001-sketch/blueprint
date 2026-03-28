// block-registry-types.ts — Hand-maintained type definitions and utility functions
// Block data is served by the backend registry API (see registry-client.ts).
// Lookup helpers (getBlocksByCategory, getBlockDefinition) live in registry-client.ts.

import { CONNECTOR_COLORS } from './design-tokens'
import { COMPAT, PORT_TYPE_ALIASES } from './port-compatibility.generated'

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
  /** Old port IDs that resolve to this port (backward compat for saved pipelines) */
  aliases?: string[]
  position?: 'top' | 'bottom' | 'left' | 'right'
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
  mandatory?: boolean
  /** For file_path fields: 'file' (default) opens a file picker, 'directory' opens a folder picker */
  path_mode?: 'file' | 'directory'
  /** File extension filters for file_path fields (e.g. ['.csv', '.json']) */
  file_extensions?: string[]
  /** When true, this field's value propagates to downstream blocks that share the same key */
  propagate?: boolean
  /** UI grouping section (e.g. "sampling", "advanced"). Fields without a section appear in the default group. */
  section?: string
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
  version: string
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
  side_inputs?: PortDefinition[]
}

/** Get port color from CONNECTOR_COLORS map (handles legacy port types) */
export function getPortColor(dataType: ConnectorType | string): string {
  const resolved = PORT_TYPE_ALIASES[dataType] || dataType
  return CONNECTOR_COLORS[resolved] || CONNECTOR_COLORS.dataset
}

export function isPortCompatible(source: ConnectorType | string, target: ConnectorType | string): boolean {
  const s = (PORT_TYPE_ALIASES[source] || source) as string
  const t = (PORT_TYPE_ALIASES[target] || target) as string
  return COMPAT[s]?.has(t) ?? false
}

/**
 * Find a port by ID, falling back to aliases for backward compatibility.
 * Saved pipelines may reference old port IDs that have since been renamed.
 */
export function resolvePort(ports: PortDefinition[], handleId: string | null | undefined): PortDefinition | undefined {
  if (!handleId) return undefined
  return ports.find((p) => p.id === handleId) ??
         ports.find((p) => p.aliases?.includes(handleId))
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
//  PORT ALIAS MATCHING
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

/** Get all names a port responds to: its own ID plus any aliases */
export function getPortNames(port: PortDefinition): string[] {
  return port.aliases ? [port.id, ...port.aliases] : [port.id]
}

/** Check whether a port matches a given name (by ID or alias) */
export function portMatchesName(port: PortDefinition, name: string): boolean {
  return port.id === name || (port.aliases?.includes(name) ?? false)
}

/**
 * Find the best type-compatible input port on a target block for a given source port.
 *
 * Preference order:
 *   1. Exact ID match (source.id === input.id)
 *   2. Alias overlap (source names ∩ input names)
 *   3. First type-compatible port
 *   4. First 'any'-typed port
 *
 * Returns undefined when no compatible port exists.
 */
export function findBestInputPort(
  sourcePort: PortDefinition,
  targetInputs: PortDefinition[],
): PortDefinition | undefined {
  const sourceNames = new Set(getPortNames(sourcePort))

  let typeMatch: PortDefinition | undefined
  let anyMatch: PortDefinition | undefined

  for (const inp of targetInputs) {
    // Exact ID match — best possible
    if (inp.id === sourcePort.id) return inp

    // Alias overlap
    if (getPortNames(inp).some((n) => sourceNames.has(n))) return inp

    // Track first type-compatible and first 'any' as fallbacks
    if (!typeMatch && isPortCompatible(sourcePort.dataType, inp.dataType)) {
      typeMatch = inp
    }
    if (!anyMatch && inp.dataType === 'any') {
      anyMatch = inp
    }
  }

  return typeMatch ?? anyMatch
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//  DYNAMIC BLOCK SIZING
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

const PORT_SLOT_WIDTH = 72
const MIN_BLOCK_WIDTH = 280
const MAX_BLOCK_WIDTH = 640

/** Compute block width based on number of ports */
export function computeBlockWidth(def: BlockDefinition): number {
  const maxPorts = Math.max(def.inputs.length, def.outputs.length, 1)
  return Math.min(MAX_BLOCK_WIDTH, Math.max(MIN_BLOCK_WIDTH, maxPorts * PORT_SLOT_WIDTH))
}
