import { useCallback, useRef, useState, useEffect, useMemo } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useReactFlow,
  type NodeTypes,
  type Connection,
  BackgroundVariant,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { T } from '@/lib/design-tokens'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useShallow } from 'zustand/react/shallow'
import { getBlockDefinition, getPortColor, isPortCompatible } from '@/lib/block-registry'
import BlockNode from './BlockNode'
import StickyNote from './StickyNote'
import GroupNode from './GroupNode'
import QuickPalette from './QuickPalette'
import EdgePreviewPanel from './EdgePreviewPanel'
import InheritanceOverlay, { OVERLAY_COLORS } from './InheritanceOverlay'
import NodeContextMenu from './NodeContextMenu'
import RerunOverlay from './RerunOverlay'

const nodeTypes: NodeTypes = {
  blockNode: BlockNode as any,
  stickyNote: StickyNote as any,
  groupNode: GroupNode as any,
}

export default function PipelineCanvas() {
  const { fitView } = useReactFlow()
  const {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    addNode,
    selectNode,
    inheritanceOverlay,
    deactivateInheritanceOverlay,
  } = usePipelineStore(useShallow((s) => ({
    nodes: s.nodes,
    edges: s.edges,
    onNodesChange: s.onNodesChange,
    onEdgesChange: s.onEdgesChange,
    onConnect: s.onConnect,
    addNode: s.addNode,
    selectNode: s.selectNode,
    inheritanceOverlay: s.inheritanceOverlay,
    deactivateInheritanceOverlay: s.deactivateInheritanceOverlay,
  })))

  // Drop zone visual feedback
  const [isDragOver, setIsDragOver] = useState(false)

  // Node context menu
  const [contextMenu, setContextMenu] = useState<{
    visible: boolean
    x: number
    y: number
    nodeId: string
  }>({ visible: false, x: 0, y: 0, nodeId: '' })

  const [paletteParams, setPaletteParams] = useState<{
    visible: boolean
    x: number
    y: number
    sourceType: string
    sourceNodeId: string
    sourceHandleId: string
  }>({
    visible: false,
    x: 0,
    y: 0,
    sourceType: '',
    sourceNodeId: '',
    sourceHandleId: '',
  })

  // Edge hover preview state
  const [hoveredEdgeParams, setHoveredEdgeParams] = useState<{
    visible: boolean
    x: number
    y: number
    dataType: string
  }>({
    visible: false,
    x: 0,
    y: 0,
    dataType: '',
  })

  // Track dragging start so we know the type when dropped
  const edgeTempRef = useRef<{ nodeId: string; handleId: string; type: string } | null>(null)

  const reactFlowRef = useRef<HTMLDivElement>(null)

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setIsDragOver(true)
  }, [])

  const onDragLeave = useCallback((e: React.DragEvent) => {
    // Only reset if leaving the canvas entirely (not entering child)
    if (!reactFlowRef.current?.contains(e.relatedTarget as Node)) {
      setIsDragOver(false)
    }
  }, [])

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragOver(false)
      const blockType = e.dataTransfer.getData('application/blueprint-block')
      if (!blockType) return

      const bounds = reactFlowRef.current?.getBoundingClientRect()
      if (!bounds) return

      const position = {
        x: e.clientX - bounds.left - 100,
        y: e.clientY - bounds.top - 30,
      }

      addNode(blockType, position)
    },
    [addNode]
  )

  // Connection validation — only allow compatible port types
  const isValidConnection = useCallback((connection: Connection | { source?: string; target?: string; sourceHandle?: string | null; targetHandle?: string | null }) => {
    const state = usePipelineStore.getState()
    const sourceNode = state.nodes.find((n) => n.id === connection.source)
    const targetNode = state.nodes.find((n) => n.id === connection.target)
    if (!sourceNode || !targetNode) return false
    if (connection.source === connection.target) return false

    const sourceDef = getBlockDefinition(sourceNode.data.type)
    const targetDef = getBlockDefinition(targetNode.data.type)
    if (!sourceDef || !targetDef) return true

    const sourcePort = sourceDef.outputs.find((p) => p.id === connection.sourceHandle)
    const targetPort = targetDef.inputs.find((p) => p.id === connection.targetHandle)
    if (!sourcePort || !targetPort) return true

    return isPortCompatible(sourcePort.dataType, targetPort.dataType)
  }, [])

  const onNodeClick = useCallback(
    (_: any, node: any) => {
      // Dismiss inheritance overlay on any click (spec: "click anywhere to exit")
      deactivateInheritanceOverlay()
      selectNode(node.id)
    },
    [selectNode, deactivateInheritanceOverlay]
  )

  const onPaneClick = useCallback(() => {
    selectNode(null)
    setPaletteParams((p: any) => ({ ...p, visible: false }))
    setContextMenu((p) => ({ ...p, visible: false }))
    deactivateInheritanceOverlay()
  }, [selectNode, deactivateInheritanceOverlay])

  // Node right-click context menu
  const onNodeContextMenu = useCallback((event: React.MouseEvent, node: any) => {
    event.preventDefault()
    setContextMenu({
      visible: true,
      x: event.clientX,
      y: event.clientY,
      nodeId: node.id,
    })
  }, [])

  const onConnectStart = useCallback((_: any, params: { nodeId: string | null; handleId: string | null; handleType: string | null }) => {
    if (!params.nodeId || !params.handleId || params.handleType !== 'source') return
    const node = usePipelineStore.getState().nodes.find(n => n.id === params.nodeId)
    if (!node) return
    const def = getBlockDefinition(node.data.type)
    if (!def) return
    const port = def.outputs.find(o => o.id === params.handleId)
    if (port) {
      edgeTempRef.current = { nodeId: params.nodeId, handleId: params.handleId, type: port.dataType }
    }
  }, [])

  const onConnectEnd = useCallback((event: any) => {
    const targetIsPane = event.target.classList.contains('react-flow__pane')

    if (targetIsPane && edgeTempRef.current) {
      // Open Quick Palette at mouse coords
      setPaletteParams({
        visible: true,
        x: event.clientX,
        y: event.clientY,
        sourceType: edgeTempRef.current.type,
        sourceNodeId: edgeTempRef.current.nodeId,
        sourceHandleId: edgeTempRef.current.handleId,
      })
    }
    edgeTempRef.current = null
  }, [])

  // ----- Edge Hover Preview -----
  const mousePosRef = useRef({ x: 0, y: 0 })
  // Use ref for visible flag so the effect runs once (no listener churn on hover toggle)
  const hoveredVisibleRef = useRef(hoveredEdgeParams.visible)
  hoveredVisibleRef.current = hoveredEdgeParams.visible

  useEffect(() => {
    const handleGlobalMouseMove = (e: MouseEvent) => {
      mousePosRef.current = { x: e.clientX, y: e.clientY }
      if (hoveredVisibleRef.current) {
        setHoveredEdgeParams((p: any) => ({ ...p, x: e.clientX, y: e.clientY }))
      }
    }
    window.addEventListener('mousemove', handleGlobalMouseMove)
    return () => window.removeEventListener('mousemove', handleGlobalMouseMove)
  }, [])

  const onEdgeMouseEnter = useCallback((_: React.MouseEvent, edge: any) => {
    const state = usePipelineStore.getState()
    const sourceNode = state.nodes.find(n => n.id === edge.source)
    if (!sourceNode) return
    const def = getBlockDefinition(sourceNode.data.type)
    if (!def) return
    const port = def.outputs.find(o => o.id === edge.sourceHandle)
    if (!port) return

    setHoveredEdgeParams({
      visible: true,
      x: mousePosRef.current.x,
      y: mousePosRef.current.y,
      dataType: port.dataType,
    })
  }, [])

  const onEdgeMouseLeave = useCallback(() => {
    setHoveredEdgeParams(p => ({ ...p, visible: false }))
  }, [])

  const handlePaletteSelect = (newBlockType: string) => {
    const bounds = reactFlowRef.current?.getBoundingClientRect()
    if (!bounds) return

    // Add node
    const position = {
      x: paletteParams.x - bounds.left,
      y: paletteParams.y - bounds.top,
    }

    // We add the node, wait a tick, then connect the edge
    usePipelineStore.getState().addNode(newBlockType, position)

    setTimeout(() => {
      const state = usePipelineStore.getState()
      const newestNode = state.nodes[state.nodes.length - 1]
      const newDef = getBlockDefinition(newBlockType)
      if (newestNode && newDef) {
        // Find best input port match
        const targetPort = newDef.inputs.find((i) => i.dataType === paletteParams.sourceType || i.dataType === 'any')
        if (targetPort) {
          state.onConnect({
            source: paletteParams.sourceNodeId,
            sourceHandle: paletteParams.sourceHandleId,
            target: newestNode.id,
            targetHandle: targetPort.id,
          })
        }
      }
    }, 50)

    setPaletteParams((p: { visible: boolean; x: number; y: number; sourceType: string; sourceNodeId: string; sourceHandleId: string; }) => ({ ...p, visible: false }))
  }

  // ── Keyboard shortcuts: Copy, Paste, Delete, Select All, Escape, Fit View, Redo ──
  const clipboardRef = useRef<{ nodeIds: string[] } | null>(null)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't intercept when user is typing in an input/textarea
      const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return

      const meta = e.metaKey || e.ctrlKey
      const { nodes } = usePipelineStore.getState()
      const selectedIds = nodes.filter((n) => n.selected).map((n) => n.id)

      if (meta && e.key === 'c') {
        // Copy
        if (selectedIds.length > 0) {
          clipboardRef.current = { nodeIds: selectedIds }
        }
      } else if (meta && e.key === 'v') {
        // Paste
        if (clipboardRef.current && clipboardRef.current.nodeIds.length > 0) {
          usePipelineStore.getState().duplicateNodes(clipboardRef.current.nodeIds)
        }
      } else if (meta && e.key === 'a') {
        // Select all
        e.preventDefault()
        const changes = nodes.map((n) => ({ type: 'select' as const, id: n.id, selected: true }))
        usePipelineStore.getState().onNodesChange(changes)
      } else if (meta && e.key === 'y') {
        // Redo (Cmd/Ctrl+Y alternative)
        e.preventDefault()
        usePipelineStore.getState().redo()
      } else if (e.key === 'Escape') {
        // Dismiss inheritance overlay first, then deselect
        const overlay = usePipelineStore.getState().inheritanceOverlay
        if (overlay) {
          usePipelineStore.getState().deactivateInheritanceOverlay()
          return
        }
        // Exit rerun mode if active
        const { rerunMode, exitRerunMode } = usePipelineStore.getState()
        if (rerunMode?.active) {
          exitRerunMode()
          return
        }
        // Deselect all
        const changes = nodes
          .filter((n) => n.selected)
          .map((n) => ({ type: 'select' as const, id: n.id, selected: false }))
        if (changes.length > 0) {
          usePipelineStore.getState().onNodesChange(changes)
        }
        selectNode(null)
        setContextMenu((p) => ({ ...p, visible: false }))
      } else if (e.key === 'f' || e.key === 'F') {
        // Fit view (frame all)
        if (!meta) {
          e.preventDefault()
          fitView({ duration: 400, padding: 0.2 })
        }
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (selectedIds.length > 0) {
          e.preventDefault()
          usePipelineStore.getState().removeSelectedNodes()
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [fitView, selectNode])

  // Close context menu on outside click
  useEffect(() => {
    if (!contextMenu.visible) return
    const handler = () => setContextMenu((p) => ({ ...p, visible: false }))
    window.addEventListener('click', handler)
    return () => window.removeEventListener('click', handler)
  }, [contextMenu.visible])

  // Recompute edge colors for loaded pipelines (onConnect already sets them for new edges).
  // Also applies inheritance overlay styling when active.
  const coloredEdges = useMemo(() => {
    const currentNodes = usePipelineStore.getState().nodes
    // Pre-build a Set for O(1) participating-edge lookup
    const participatingSet = inheritanceOverlay
      ? new Set(inheritanceOverlay.participatingEdges)
      : null

    return edges.map((edge) => {
      // Base color computation
      let baseStroke = edge.style?.stroke
      if (!baseStroke || baseStroke === T.borderHi) {
        const sourceNode = currentNodes.find((n) => n.id === edge.source)
        const def = sourceNode ? getBlockDefinition((sourceNode.data as any)?.type) : undefined
        const port = def?.outputs.find((o) => o.id === edge.sourceHandle)
        baseStroke = port ? getPortColor(port.dataType) : T.borderHi
      }

      // Inheritance overlay styling
      if (participatingSet) {
        const isParticipating = participatingSet.has(edge.id)
        return {
          ...edge,
          style: {
            ...edge.style,
            stroke: isParticipating ? OVERLAY_COLORS.inheriting : baseStroke,
            strokeWidth: isParticipating ? 3 : 1.5,
            opacity: isParticipating ? 1 : 0.15,
          },
          className: isParticipating ? 'inheritance-edge' : '',
          animated: isParticipating,
        }
      }

      return { ...edge, style: { ...edge.style, stroke: baseStroke, strokeWidth: 1.5 } }
    })
  }, [edges, inheritanceOverlay])

  return (
    <div
      ref={reactFlowRef}
      onDragLeave={onDragLeave}
      style={{
        flex: 1,
        height: '100%',
        position: 'relative',
        transition: 'box-shadow 0.2s',
        boxShadow: isDragOver ? `inset 0 0 0 2px ${T.cyan}60, inset 0 0 40px ${T.cyan}10` : 'none',
      }}
    >
      <QuickPalette
        visible={paletteParams.visible}
        x={paletteParams.x}
        y={paletteParams.y}
        sourceType={paletteParams.sourceType}
        sourceNodeId={paletteParams.sourceNodeId}
        sourceHandleId={paletteParams.sourceHandleId}
        onSelect={handlePaletteSelect}
        onClose={() => setPaletteParams((p: { visible: boolean; x: number; y: number; sourceType: string; sourceNodeId: string; sourceHandleId: string; }) => ({ ...p, visible: false }))}
      />

      <EdgePreviewPanel
        visible={hoveredEdgeParams.visible}
        x={hoveredEdgeParams.x}
        y={hoveredEdgeParams.y}
        dataType={hoveredEdgeParams.dataType}
      />

      <InheritanceOverlay />

      {/* 3D perspective grid underlay */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          overflow: 'hidden',
          pointerEvents: 'none',
          zIndex: 0,
        }}
      >
        <div
          style={{
            position: 'absolute',
            bottom: 0,
            left: '-20%',
            width: '140%',
            height: '60%',
            transform: 'perspective(400px) rotateX(55deg)',
            transformOrigin: 'bottom center',
            backgroundImage:
              `linear-gradient(${T.cyan}08 1px, transparent 1px), linear-gradient(90deg, ${T.cyan}08 1px, transparent 1px)`,
            backgroundSize: '32px 32px',
            maskImage: 'linear-gradient(to top, rgba(0,0,0,0.3) 0%, transparent 80%)',
            WebkitMaskImage: 'linear-gradient(to top, rgba(0,0,0,0.3) 0%, transparent 80%)',
            animation: 'grid-scroll 4s linear infinite',
          }}
        />
      </div>
      <ReactFlow
        nodes={nodes}
        edges={coloredEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onConnectStart={onConnectStart}
        onConnectEnd={onConnectEnd}
        onEdgeMouseEnter={onEdgeMouseEnter}
        onEdgeMouseLeave={onEdgeMouseLeave}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onNodeClick={onNodeClick}
        onNodeContextMenu={onNodeContextMenu}
        onPaneClick={onPaneClick}
        isValidConnection={isValidConnection}
        nodeTypes={nodeTypes}
        fitView
        snapToGrid
        snapGrid={[16, 16]}
        defaultEdgeOptions={{
          type: 'smoothstep',
          animated: true,
        }}
        connectionLineStyle={{ stroke: T.cyan, strokeWidth: 2 }}
        style={{ background: 'transparent' }}
        proOptions={{ hideAttribution: true }}
        multiSelectionKeyCode="Shift"
        selectionOnDrag
      >
        <Background
          color={`${T.border}`}
          gap={16}
          size={1}
          variant={BackgroundVariant.Dots}
        />
        <Controls
          style={{
            background: T.surface2,
            border: `1px solid ${T.border}`,
            borderRadius: 0,
          }}
        />
        <MiniMap
          nodeColor={(node: any) => {
            return node.data?.accent || T.dim
          }}
          maskColor={T.shadowHeavy}
          style={{
            background: T.surface1,
            border: `1px solid ${T.border}`,
            borderRadius: 0,
          }}
        />
      </ReactFlow>

      {/* Node context menu */}
      <NodeContextMenu
        visible={contextMenu.visible}
        x={contextMenu.x}
        y={contextMenu.y}
        nodeId={contextMenu.nodeId}
        onClose={() => setContextMenu((p) => ({ ...p, visible: false }))}
      />

      {/* Re-run mode overlay */}
      <RerunOverlay />
    </div>
  )
}
