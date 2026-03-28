/**
 * Graph utilities for kill-switch validation on the frontend.
 *
 * Mirrors backend/engine/graph_utils.py so the UI can eagerly disable
 * controls that the backend would reject, without a round-trip.
 */

interface MinimalNode {
  id: string
  data?: { type?: string }
}

interface MinimalEdge {
  source: string
  target: string
}

/**
 * Returns true if the pipeline contains a loop_controller block **or** a
 * graph cycle (Kahn's algorithm — identical to the backend check).
 *
 * Runs in O(V + E) time and allocates O(V + E) memory.
 */
export function containsLoopOrCycle(nodes: MinimalNode[], edges: MinimalEdge[]): boolean {
  // (a) Explicit loop_controller block
  for (const node of nodes) {
    if (node.data?.type === 'loop_controller') return true
  }

  if (nodes.length === 0) return false

  // (b) Kahn's algorithm: nodes remaining after peeling = cyclic
  const nodeIds = new Set(nodes.map((n) => n.id))
  const inDegree = new Map<string, number>()
  const adj = new Map<string, string[]>()

  for (const id of nodeIds) {
    inDegree.set(id, 0)
    adj.set(id, [])
  }

  for (const e of edges) {
    if (nodeIds.has(e.source) && nodeIds.has(e.target)) {
      adj.get(e.source)!.push(e.target)
      inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1)
    }
  }

  const queue: string[] = []
  for (const [id, deg] of inDegree) {
    if (deg === 0) queue.push(id)
  }

  let visited = 0
  while (queue.length > 0) {
    const nid = queue.shift()!
    visited++
    for (const neighbor of adj.get(nid) ?? []) {
      const newDeg = (inDegree.get(neighbor) ?? 1) - 1
      inDegree.set(neighbor, newDeg)
      if (newDeg === 0) queue.push(neighbor)
    }
  }

  return visited < nodeIds.size
}

/** Block types that are not exportable. Must stay in sync with backend. */
const NON_EXPORTABLE_BLOCK_TYPES = new Set(['python_runner'])

/**
 * Returns true if the pipeline cannot be exported to a standalone script.
 *
 * Checks for loops/cycles and non-exportable block types (python_runner).
 * This is a client-side mirror of `validate_exportable()` on the backend;
 * the backend is the authoritative gate but this avoids a pointless
 * round-trip for a doomed request.
 */
export function isPipelineExportable(nodes: MinimalNode[], edges: MinimalEdge[]): boolean {
  if (containsLoopOrCycle(nodes, edges)) return false
  for (const node of nodes) {
    if (node.data?.type && NON_EXPORTABLE_BLOCK_TYPES.has(node.data.type)) return false
  }
  return true
}

/**
 * Returns a human-readable tooltip explaining why the pipeline is not
 * exportable, or an empty string if it is exportable.
 */
export function exportDisabledReason(nodes: MinimalNode[], edges: MinimalEdge[]): string {
  if (containsLoopOrCycle(nodes, edges)) {
    return 'Export is not available for pipelines with loops or cycles'
  }
  for (const node of nodes) {
    if (node.data?.type && NON_EXPORTABLE_BLOCK_TYPES.has(node.data.type)) {
      return 'Export is not available for pipelines with custom code blocks'
    }
  }
  return ''
}
