/**
 * error-recovery.ts — helpers for one-click error recovery actions.
 *
 * Provides logic for suggesting connections, highlighting missing config,
 * and other automated fix actions.
 */

import { usePipelineStore } from '@/stores/pipelineStore'
import { useErrorStore, type PipelineError } from '@/stores/errorStore'
import { getBlockDefinition, isPortCompatible } from '@/lib/block-registry'
import { api } from '@/api/client'

/**
 * For a "Port Disconnected" error on a node, find the most likely
 * connection based on port type compatibility with other nodes.
 */
export function suggestConnection(nodeId: string, portId: string, direction: 'input' | 'output'): {
  targetNodeId: string
  targetPortId: string
} | null {
  const { nodes, edges } = usePipelineStore.getState()

  const node = nodes.find((n) => n.id === nodeId)
  if (!node) return null

  const def = getBlockDefinition(node.data?.type)
  if (!def) return null

  // Find the port on this node
  const port = direction === 'input'
    ? def.inputs.find((p) => p.id === portId)
    : def.outputs.find((p) => p.id === portId)
  if (!port) return null

  // Already connected edges
  const connected = new Set(
    edges.map((e) =>
      direction === 'input'
        ? `${e.target}:${e.targetHandle}`
        : `${e.source}:${e.sourceHandle}`
    )
  )

  // Search other nodes for a compatible unconnected port
  for (const other of nodes) {
    if (other.id === nodeId) continue
    const otherDef = getBlockDefinition(other.data?.type)
    if (!otherDef) continue

    const otherPorts = direction === 'input' ? otherDef.outputs : otherDef.inputs
    for (const op of otherPorts) {
      const key = direction === 'input'
        ? `${other.id}:${op.id}`
        : `${other.id}:${op.id}`

      if (connected.has(key)) continue

      const compatible = direction === 'input'
        ? isPortCompatible(op.dataType, port.dataType)
        : isPortCompatible(port.dataType, op.dataType)

      if (compatible) {
        return { targetNodeId: other.id, targetPortId: op.id }
      }
    }
  }

  return null
}

/**
 * Create a structured PipelineError from a node execution failure.
 */
export function createNodeError(
  nodeId: string,
  nodeName: string,
  error: {
    title: string
    message: string
    action?: string
    severity?: 'error' | 'warning'
    details?: string
  },
  recoveryType?: PipelineError['recoveryType'],
  recoveryPayload?: Record<string, string>,
): Omit<PipelineError, 'id' | 'timestamp'> {
  return {
    nodeId,
    nodeName,
    title: error.title,
    message: error.message,
    action: error.action,
    severity: error.severity ?? 'error',
    details: error.details,
    recoveryType,
    recoveryPayload,
  }
}

/**
 * Attempt to start a service and refresh capabilities.
 */
export async function startServiceAndRefresh(serviceName: string): Promise<boolean> {
  try {
    await api.post(`/system/start-service/${serviceName}`, {})
    // Wait a bit for the service to boot
    await new Promise((r) => setTimeout(r, 2000))
    // Refresh capabilities
    await useErrorStore.getState().fetchCapabilities()
    return true
  } catch {
    return false
  }
}
