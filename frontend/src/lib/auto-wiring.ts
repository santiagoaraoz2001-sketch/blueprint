// auto-wiring.ts — Connection suggestion algorithm for dropped/moved blocks

import type { Node, Edge } from '@xyflow/react'
import type { BlockNodeData } from '@/stores/pipelineStore'
import type { PortDefinition } from './block-registry-types'
import { getBlockDefinition, isPortCompatible } from './block-registry'

export interface ConnectionSuggestion {
  sourceNodeId: string
  sourcePortId: string
  targetNodeId: string
  targetPortId: string
  score: number    // 0-1, higher = better match
  label: string    // e.g., "Column Transform: Transformed → Dataset"
  dataType: string // Wire type for color indicator (e.g., "dataset", "model")
}

/**
 * Score a potential connection between two ports.
 * Returns 0 if incompatible, otherwise 0.3–1.0 based on match quality.
 */
function scoreConnection(sourcePort: PortDefinition, targetPort: PortDefinition): number {
  if (!isPortCompatible(sourcePort.dataType, targetPort.dataType)) return 0

  let score = 0.3 // Base score for type compatibility

  // Exact type match (dataset→dataset) scores higher than coercion (dataset→text)
  if (sourcePort.dataType === targetPort.dataType) score += 0.3

  // Port ID match (source 'model' → target 'model') scores highest
  if (sourcePort.id === targetPort.id) {
    score += 0.4
  } else if (sourcePort.id.includes(targetPort.id) || targetPort.id.includes(sourcePort.id)) {
    // Partial ID match (source 'trained_model' contains 'model', target is 'model')
    score += 0.2
  }

  // Required target port gets a bonus
  if (targetPort.required) score += 0.1

  return Math.min(score, 1.0)
}

/**
 * Find nodes within proximity of a dropped/moved node.
 * "Nearby" means within `threshold` px on both axes.
 */
export function findNearbyNodes(
  droppedNode: Node<BlockNodeData>,
  allNodes: Node<BlockNodeData>[],
  threshold = 300,
): string[] {
  return allNodes
    .filter((n) => n.id !== droppedNode.id && n.type === 'blockNode')
    .filter((n) => {
      const dx = Math.abs(n.position.x - droppedNode.position.x)
      const dy = Math.abs(n.position.y - droppedNode.position.y)
      return dx < threshold && dy < threshold
    })
    .map((n) => n.id)
}

/**
 * Suggest compatible connections between a dropped/moved node and nearby nodes.
 * Returns up to 5 suggestions sorted by score descending.
 */
export function suggestConnections(
  droppedNodeId: string,
  nearbyNodeIds: string[],
  nodes: Node<BlockNodeData>[],
  edges: Edge[],
): ConnectionSuggestion[] {
  const droppedNode = nodes.find((n) => n.id === droppedNodeId)
  if (!droppedNode) return []

  const droppedDef = getBlockDefinition((droppedNode.data as BlockNodeData).type)
  if (!droppedDef) return []

  const suggestions: ConnectionSuggestion[] = []

  for (const nearbyId of nearbyNodeIds) {
    const nearbyNode = nodes.find((n) => n.id === nearbyId)
    if (!nearbyNode) continue

    const nearbyDef = getBlockDefinition((nearbyNode.data as BlockNodeData).type)
    if (!nearbyDef) continue

    // Check: nearby outputs → dropped inputs
    for (const nearbyOut of nearbyDef.outputs) {
      for (const droppedIn of droppedDef.inputs) {
        const score = scoreConnection(nearbyOut, droppedIn)
        if (score > 0) {
          const exists = edges.some(
            (e) =>
              e.source === nearbyId &&
              e.sourceHandle === nearbyOut.id &&
              e.target === droppedNodeId &&
              e.targetHandle === droppedIn.id,
          )
          if (!exists) {
            suggestions.push({
              sourceNodeId: nearbyId,
              sourcePortId: nearbyOut.id,
              targetNodeId: droppedNodeId,
              targetPortId: droppedIn.id,
              score,
              label: `${nearbyDef.name}: ${nearbyOut.label} → ${droppedIn.label}`,
              dataType: nearbyOut.dataType,
            })
          }
        }
      }
    }

    // Check: dropped outputs → nearby inputs
    for (const droppedOut of droppedDef.outputs) {
      for (const nearbyIn of nearbyDef.inputs) {
        const score = scoreConnection(droppedOut, nearbyIn)
        if (score > 0) {
          const exists = edges.some(
            (e) =>
              e.source === droppedNodeId &&
              e.sourceHandle === droppedOut.id &&
              e.target === nearbyId &&
              e.targetHandle === nearbyIn.id,
          )
          if (!exists) {
            suggestions.push({
              sourceNodeId: droppedNodeId,
              sourcePortId: droppedOut.id,
              targetNodeId: nearbyId,
              targetPortId: nearbyIn.id,
              score,
              label: `${droppedOut.label} → ${nearbyDef.name}: ${nearbyIn.label}`,
              dataType: droppedOut.dataType,
            })
          }
        }
      }
    }
  }

  // Sort by score descending, limit to top 5
  return suggestions.sort((a, b) => b.score - a.score).slice(0, 5)
}
