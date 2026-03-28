/**
 * Validation Store — manages backend validation state for the pipeline editor.
 *
 * Provides debounced backend validation on graph changes, tracks validation
 * status, and exposes per-node error maps for canvas overlays.
 *
 * Generation tracking: each graph change increments a generation counter.
 * Validation results are only applied if their generation matches the current
 * one, preventing stale results from overwriting fresher state. The `isStale`
 * flag is set immediately on graph change so the UI can show "VALIDATING..."
 * even before the debounce fires.
 */

import { create } from 'zustand'
import { api } from '@/api/client'

export interface BackendValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
  estimated_runtime_s: number
  block_count: number
  edge_count: number
}

export interface NodeValidationError {
  nodeId: string
  message: string
  action?: string
  severity: 'error' | 'warning'
}

/** Edge key for type-mismatch overlays */
export interface EdgeValidationError {
  edgeId: string
  sourceId: string
  targetId: string
  message: string
}

interface ValidationState {
  /** Current backend validation result */
  result: BackendValidationResult | null
  /** Whether a validation request is in-flight */
  isValidating: boolean
  /** Whether the current result is stale (graph changed since last validation) */
  isStale: boolean
  /** Monotonically increasing generation counter — incremented on every graph change */
  _generation: number
  /** Generation at which the current result was produced */
  _resultGeneration: number
  /** Parsed per-node errors for canvas overlays */
  nodeErrors: Record<string, NodeValidationError[]>
  /** Parsed edge errors for red dashed strokes */
  edgeErrors: Record<string, EdgeValidationError>
  /** Whether the validation panel is visible */
  panelVisible: boolean

  // Actions
  /** Call when the graph changes — marks current results stale and increments generation */
  markStale: () => void
  /** Trigger backend validation — results are discarded if generation has advanced */
  validate: (pipelineId: string) => Promise<BackendValidationResult | null>
  clearValidation: () => void
  setPanelVisible: (visible: boolean) => void
  togglePanel: () => void
}

/**
 * Parse validation errors to extract node IDs from error messages.
 * Error messages follow the pattern: "Block 'Label' (nodeId): ..." or
 * "Block 'Label': ..." — we try to match node labels against provided nodes.
 */
function parseNodeErrors(
  errors: string[],
  warnings: string[],
  nodes: Array<{ id: string; data: { label: string; type: string } }>,
): Record<string, NodeValidationError[]> {
  const result: Record<string, NodeValidationError[]> = {}
  const labelToId = new Map<string, string>()
  for (const n of nodes) {
    labelToId.set(n.data.label, n.id)
    labelToId.set(n.id, n.id)
  }

  const processItems = (items: string[], severity: 'error' | 'warning') => {
    for (const msg of items) {
      // Match "Block 'Label'" pattern
      const match = msg.match(/Block '([^']+)'/)
      if (match) {
        const label = match[1]
        const nodeId = labelToId.get(label)
        if (nodeId) {
          if (!result[nodeId]) result[nodeId] = []
          result[nodeId].push({ nodeId, message: msg, severity })
          continue
        }
      }
      // Match node IDs directly (e.g., "(node-abc123)")
      const idMatch = msg.match(/\(([a-zA-Z0-9_-]+)\)/)
      if (idMatch) {
        const nodeId = labelToId.get(idMatch[1])
        if (nodeId) {
          if (!result[nodeId]) result[nodeId] = []
          result[nodeId].push({ nodeId, message: msg, severity })
        }
      }
    }
  }

  processItems(errors, 'error')
  processItems(warnings, 'warning')
  return result
}

function parseEdgeErrors(
  errors: string[],
  edges: Array<{ id: string; source: string; target: string }>,
  nodes: Array<{ id: string; data: { label: string; type: string } }>,
): Record<string, EdgeValidationError> {
  const result: Record<string, EdgeValidationError> = {}

  // Build label → nodeId map for matching
  const labelToId = new Map<string, string>()
  for (const n of nodes) {
    labelToId.set(n.data.label, n.id)
  }

  for (const msg of errors) {
    if (!msg.includes('Incompatible connection')) continue

    // Error format: "Incompatible connection: Cannot connect TYPE (SrcLabel) to TYPE (TgtLabel)"
    // Extract the two labels in parentheses
    const labelMatches = [...msg.matchAll(/\(([^)]+)\)/g)]
    if (labelMatches.length < 2) continue

    const srcLabel = labelMatches[0][1]
    const tgtLabel = labelMatches[1][1]
    const srcNodeId = labelToId.get(srcLabel)
    const tgtNodeId = labelToId.get(tgtLabel)

    if (!srcNodeId || !tgtNodeId) continue

    // Find matching edges between these two nodes
    for (const edge of edges) {
      if (edge.source === srcNodeId && edge.target === tgtNodeId) {
        result[edge.id] = {
          edgeId: edge.id,
          sourceId: edge.source,
          targetId: edge.target,
          message: msg,
        }
      }
    }
  }
  return result
}

export const useValidationStore = create<ValidationState>((set, get) => ({
  result: null,
  isValidating: false,
  isStale: false,
  _generation: 0,
  _resultGeneration: -1,
  nodeErrors: {},
  edgeErrors: {},
  panelVisible: false,

  markStale: () => {
    set((s) => ({
      isStale: true,
      _generation: s._generation + 1,
    }))
  },

  validate: async (pipelineId: string) => {
    if (!pipelineId) return null

    // Capture the generation at request time
    const requestGeneration = get()._generation
    set({ isValidating: true })

    try {
      const result = await api.post<BackendValidationResult>(
        `/pipelines/${pipelineId}/validate`,
      )
      if (!result) {
        set({ isValidating: false })
        return null
      }

      // Check if the graph has changed since we started this request.
      // If so, discard these results — a newer request will be incoming.
      const currentGeneration = get()._generation
      if (requestGeneration !== currentGeneration) {
        // Results are stale — keep isValidating true since another request
        // should be in-flight or about to fire from the debounce timer
        return null
      }

      // We need nodes/edges from the pipeline store for error attribution
      const { usePipelineStore } = await import('./pipelineStore')
      const { nodes, edges } = usePipelineStore.getState()
      const nodeErrors = parseNodeErrors(result.errors, result.warnings, nodes as any)
      const edgeErrors = parseEdgeErrors(result.errors, edges as any, nodes as any)

      set({
        result,
        isValidating: false,
        isStale: false,
        _resultGeneration: requestGeneration,
        nodeErrors,
        edgeErrors,
      })
      return result
    } catch {
      // On error, only clear isValidating if generation hasn't advanced
      if (get()._generation === requestGeneration) {
        set({ isValidating: false })
      }
      return null
    }
  },

  clearValidation: () => {
    set({
      result: null,
      nodeErrors: {},
      edgeErrors: {},
      isValidating: false,
      isStale: false,
      _generation: 0,
      _resultGeneration: -1,
    })
  },

  setPanelVisible: (visible: boolean) => {
    set({ panelVisible: visible })
  },

  togglePanel: () => {
    set((s) => ({ panelVisible: !s.panelVisible }))
  },
}))
