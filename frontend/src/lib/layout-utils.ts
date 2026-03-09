import dagre from 'dagre'
import { type Node, type Edge } from '@xyflow/react'
import { getBlockDefinition, computeBlockWidth } from '@/lib/block-registry'

const dagreGraph = new dagre.graphlib.Graph()
dagreGraph.setDefaultEdgeLabel(() => ({}))

// Fallback dimensions for unknown blocks
const DEFAULT_WIDTH = 280
const DEFAULT_HEIGHT = 160

/** Get the computed width for a node based on its block definition */
function getNodeWidth(node: Node): number {
    const blockType = (node.data as any)?.type
    if (blockType) {
        const def = getBlockDefinition(blockType)
        if (def) return computeBlockWidth(def)
    }
    return node.measured?.width ?? DEFAULT_WIDTH
}

export function getLayoutedElements<T extends Node>(nodes: T[], edges: Edge[], direction: 'TB' | 'LR' = 'TB'): T[] {
    dagreGraph.setGraph({ rankdir: direction, align: 'UL', edgesep: 60, ranksep: 140, nodesep: 60 })

    nodes.forEach((node) => {
        // We only lay out top-level nodes, grouped nodes flow with their parent
        if (!node.parentId) {
            const w = node.measured?.width ?? getNodeWidth(node)
            const h = node.measured?.height ?? DEFAULT_HEIGHT
            dagreGraph.setNode(node.id, { width: w, height: h })
        }
    })

    edges.forEach((edge) => {
        dagreGraph.setEdge(edge.source, edge.target)
    })

    dagre.layout(dagreGraph)

    return nodes.map((node) => {
        if (node.parentId) return node // Skip layout for sub-nodes

        const nodeWithPosition = dagreGraph.node(node.id)
        if (!nodeWithPosition) return node

        const w = node.measured?.width ?? getNodeWidth(node)
        const h = node.measured?.height ?? DEFAULT_HEIGHT

        // We are shifting the dagre node position (anchor=center center) to the top left
        // so it matches the React Flow node anchor point (top left).
        const newNode = {
            ...node,
            position: {
                x: nodeWithPosition.x - w / 2,
                y: nodeWithPosition.y - h / 2,
            },
            // Ensure target position doesn't conflict with current UI state
            targetPosition: undefined,
            sourcePosition: undefined,
        }

        return newNode
    })
}
