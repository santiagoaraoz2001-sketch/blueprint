import type { Node, Edge } from '@xyflow/react'
import type { BlockNodeData } from '@/stores/pipelineStore'

// ─── Types ───────────────────────────────────────────────────────

export type HistoryOpType = 'add' | 'remove' | 'move' | 'config' | 'connect' | 'disconnect' | 'bulk' | 'unknown'

/**
 * A single undo/redo history entry with metadata for the HistoryTimeline.
 */
export interface HistoryEntry {
  /** Snapshot of nodes at this point in time */
  nodes: Node<BlockNodeData>[]
  /** Snapshot of edges at this point in time */
  edges: Edge[]
  /** Human-readable description of what changed */
  description: string
  /** Type of operation for icon display */
  type: HistoryOpType
  /** ISO timestamp of when this entry was created */
  timestamp: string
}

/** Lightweight metadata stored in the DB column (no node/edge data). */
export interface HistoryEntryMeta {
  description: string
  type: HistoryOpType
  timestamp: string
  nodeCount: number
  edgeCount: number
}

// ─── Size budget constants ───────────────────────────────────────

/** Maximum serialized size for the SNAPSHOTS_DIR history file. */
const MAX_HISTORY_FILE_BYTES = 5 * 1024 * 1024 // 5 MB

/** When over budget, trim to this many entries and retry. */
const TRIM_TARGETS = [30, 20, 10, 5] as const

// ─── Operation inference ─────────────────────────────────────────

/**
 * Infer operation type from node/edge diffs.
 */
export function inferOperationType(
  prevNodes: Node<BlockNodeData>[],
  prevEdges: Edge[],
  currNodes: Node<BlockNodeData>[],
  currEdges: Edge[],
): { type: HistoryOpType; description: string } {
  const prevNodeIds = new Set(prevNodes.map((n) => n.id))
  const currNodeIds = new Set(currNodes.map((n) => n.id))
  const prevEdgeIds = new Set(prevEdges.map((e) => e.id))
  const currEdgeIds = new Set(currEdges.map((e) => e.id))

  const addedNodes = currNodes.filter((n) => !prevNodeIds.has(n.id))
  const removedNodes = prevNodes.filter((n) => !currNodeIds.has(n.id))
  const addedEdges = currEdges.filter((e) => !prevEdgeIds.has(e.id))
  const removedEdges = prevEdges.filter((e) => !currEdgeIds.has(e.id))

  // Multiple types of change at once
  const changeCount = (addedNodes.length > 0 ? 1 : 0)
    + (removedNodes.length > 0 ? 1 : 0)
    + (addedEdges.length > 0 ? 1 : 0)
    + (removedEdges.length > 0 ? 1 : 0)

  if (changeCount > 1) {
    return { type: 'bulk', description: 'Multiple changes' }
  }

  if (addedNodes.length > 0) {
    const name = addedNodes[0].data?.label || addedNodes[0].data?.type || 'node'
    return {
      type: 'add',
      description: addedNodes.length === 1 ? `Added ${name}` : `Added ${addedNodes.length} nodes`,
    }
  }

  if (removedNodes.length > 0) {
    const name = removedNodes[0].data?.label || removedNodes[0].data?.type || 'node'
    return {
      type: 'remove',
      description: removedNodes.length === 1 ? `Removed ${name}` : `Removed ${removedNodes.length} nodes`,
    }
  }

  if (addedEdges.length > 0) {
    return { type: 'connect', description: `Connected ${addedEdges.length} edge${addedEdges.length > 1 ? 's' : ''}` }
  }

  if (removedEdges.length > 0) {
    return { type: 'disconnect', description: `Disconnected ${removedEdges.length} edge${removedEdges.length > 1 ? 's' : ''}` }
  }

  // Check for position changes (moves)
  const movedNodes = currNodes.filter((n) => {
    const prev = prevNodes.find((p) => p.id === n.id)
    if (!prev) return false
    return prev.position.x !== n.position.x || prev.position.y !== n.position.y
  })
  if (movedNodes.length > 0) {
    return {
      type: 'move',
      description: movedNodes.length === 1
        ? `Moved ${movedNodes[0].data?.label || 'node'}`
        : `Moved ${movedNodes.length} nodes`,
    }
  }

  // Check for config changes
  const configChanged = currNodes.some((n) => {
    const prev = prevNodes.find((p) => p.id === n.id)
    if (!prev) return false
    return JSON.stringify(n.data?.config) !== JSON.stringify(prev.data?.config)
  })
  if (configChanged) {
    return { type: 'config', description: 'Changed configuration' }
  }

  return { type: 'unknown', description: 'Edit' }
}

// ─── Serialization: lightweight metadata for DB column ───────────

/**
 * Serialize history as lightweight metadata for the DB `history_json` column.
 * No node/edge payloads — just enough for timeline display and ordering.
 */
export function serializeHistoryMeta(
  past: HistoryEntry[],
  future: HistoryEntry[],
): string {
  const toMeta = (e: HistoryEntry): HistoryEntryMeta => ({
    description: e.description,
    type: e.type,
    timestamp: e.timestamp,
    nodeCount: e.nodes.length,
    edgeCount: e.edges.length,
  })
  return JSON.stringify({
    past: past.map(toMeta),
    future: future.map(toMeta),
  })
}

// ─── Serialization: full snapshots for SNAPSHOTS_DIR file ────────

/**
 * Serialize full history snapshots (nodes + edges) for the
 * SNAPSHOTS_DIR file.  Applies progressive size gating:
 *
 *   1. Serialize all entries.
 *   2. If the result exceeds MAX_HISTORY_FILE_BYTES, keep only the
 *      N most-recent past entries (trying 30, 20, 10, 5 in order).
 *   3. If still over budget, strip non-essential node fields
 *      (measured, width, height, computed, style) to further reduce.
 *
 * Returns the JSON string and a boolean indicating if trimming occurred.
 */
export function serializeHistory(
  past: HistoryEntry[],
  future: HistoryEntry[],
): { json: string; trimmed: boolean } {
  const build = (p: HistoryEntry[], f: HistoryEntry[]) =>
    JSON.stringify({
      past: p.map(entryToSerializable),
      future: f.map(entryToSerializable),
    })

  // First attempt: serialize everything
  let json = build(past, future)
  if (json.length <= MAX_HISTORY_FILE_BYTES) {
    return { json, trimmed: false }
  }

  // Progressive trimming of past entries (future is always small)
  for (const target of TRIM_TARGETS) {
    const trimmedPast = past.slice(-target)
    json = build(trimmedPast, future)
    if (json.length <= MAX_HISTORY_FILE_BYTES) {
      return { json, trimmed: true }
    }
  }

  // Nuclear option: strip heavy fields from nodes before serializing
  const stripped = past.slice(-5).map(stripHeavyFields)
  json = build(stripped, future)
  return { json, trimmed: true }
}

/** Convert a HistoryEntry to a plain serializable object. */
function entryToSerializable(e: HistoryEntry) {
  return {
    nodes: e.nodes,
    edges: e.edges,
    description: e.description,
    type: e.type,
    timestamp: e.timestamp,
  }
}

/** Strip non-essential fields from nodes to reduce serialization size. */
function stripHeavyFields(entry: HistoryEntry): HistoryEntry {
  return {
    ...entry,
    nodes: entry.nodes.map((n) => ({
      ...n,
      measured: undefined,
      width: undefined,
      height: undefined,
      style: undefined,
      data: {
        ...n.data,
        // Keep config but strip any large nested objects
        config: n.data.config,
      },
    })) as Node<BlockNodeData>[],
  }
}

/**
 * Deserialize full history entries from SNAPSHOTS_DIR file.
 */
export function deserializeHistory(json: string | null | undefined): {
  past: HistoryEntry[]
  future: HistoryEntry[]
} {
  if (!json) return { past: [], future: [] }
  try {
    const data = JSON.parse(json)
    return {
      past: (data.past || []).map(parseEntry),
      future: (data.future || []).map(parseEntry),
    }
  } catch {
    return { past: [], future: [] }
  }
}

/**
 * Deserialize metadata-only history from the DB column.
 * Returns HistoryEntryMeta (no nodes/edges) for timeline display.
 */
export function deserializeHistoryMeta(json: string | null | undefined): {
  past: HistoryEntryMeta[]
  future: HistoryEntryMeta[]
} {
  if (!json) return { past: [], future: [] }
  try {
    const data = JSON.parse(json)
    return {
      past: (data.past || []).map(parseMeta),
      future: (data.future || []).map(parseMeta),
    }
  } catch {
    return { past: [], future: [] }
  }
}

function parseEntry(e: any): HistoryEntry {
  return {
    nodes: e.nodes || [],
    edges: e.edges || [],
    description: e.description || 'Edit',
    type: e.type || 'unknown',
    timestamp: e.timestamp || new Date().toISOString(),
  }
}

function parseMeta(e: any): HistoryEntryMeta {
  return {
    description: e.description || 'Edit',
    type: e.type || 'unknown',
    timestamp: e.timestamp || new Date().toISOString(),
    nodeCount: e.nodeCount ?? 0,
    edgeCount: e.edgeCount ?? 0,
  }
}
