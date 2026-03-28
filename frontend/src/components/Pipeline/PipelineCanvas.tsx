import { useCallback, useRef, useState, useEffect, useMemo } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useReactFlow,
  type NodeTypes,
  type EdgeTypes,
  type Connection,
  BackgroundVariant,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { T, F, FD, FS } from '@/lib/design-tokens'
import { LayoutTemplate, Sparkles as SparklesIcon, Search as SearchIcon } from 'lucide-react'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useValidationStore } from '@/stores/validationStore'
import { useShallow } from 'zustand/react/shallow'
import { getBlockDefinition, getPortColor, isPortCompatible, resolvePort, findBestInputPort, type PortDefinition } from '@/lib/block-registry'
import { computeBlockWidth } from '@/lib/block-registry-types'
import BlockNode from './BlockNode'
import StickyNote from './StickyNote'
import GroupNode from './GroupNode'
import ValidationEdge from './ValidationEdge'
import QuickPalette from './QuickPalette'
import EdgePreviewPanel from './EdgePreviewPanel'
import InheritanceOverlay, { OVERLAY_COLORS } from './InheritanceOverlay'
import NodeContextMenu from './NodeContextMenu'
import RerunOverlay from './RerunOverlay'
import BlockSearch from '@/components/Search/BlockSearch'
import BlockSuggestions from '@/components/Search/BlockSuggestions'
import BlockDoc from '@/components/Blocks/BlockDoc'
import ConfigInspector from '@/components/Config/ConfigInspector'

const nodeTypes: NodeTypes = {
  blockNode: BlockNode as any,
  stickyNote: StickyNote as any,
  groupNode: GroupNode as any,
}

const edgeTypes: EdgeTypes = {
  validationEdge: ValidationEdge as any,
}

export default function PipelineCanvas({ onShowTemplates, onShowAgent }: { onShowTemplates?: () => void; onShowAgent?: () => void } = {}) {
  const { fitView, flowToScreenPosition, screenToFlowPosition } = useReactFlow()
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
    connectionSuggestions,
    autoWiringNodeId,
    clearConnectionSuggestions,
    triggerAutoWiring,
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
    connectionSuggestions: s.connectionSuggestions,
    autoWiringNodeId: s.autoWiringNodeId,
    clearConnectionSuggestions: s.clearConnectionSuggestions,
    triggerAutoWiring: s.triggerAutoWiring,
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
  const [inspectNodeId, setInspectNodeId] = useState<string | null>(null)

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

  // Block documentation popover state
  const [blockDocState, setBlockDocState] = useState<{
    visible: boolean
    blockType: string | null
    anchor: { x: number; y: number; width?: number; height?: number } | null
  }>({ visible: false, blockType: null, anchor: null })

  const showBlockDoc = useCallback((blockType: string, anchor?: { x: number; y: number; width?: number; height?: number }) => {
    setBlockDocState({ visible: true, blockType, anchor: anchor ?? null })
  }, [])

  const hideBlockDoc = useCallback(() => {
    setBlockDocState({ visible: false, blockType: null, anchor: null })
  }, [])

  // Helper to get viewport center in flow coordinates.
  // Uses ReactFlow's screenToFlowPosition for accurate conversion
  // regardless of zoom level or pan offset.
  const getViewportCenter = useCallback(() => {
    const bounds = reactFlowRef.current?.getBoundingClientRect()
    if (!bounds) return { x: 300, y: 300 }
    // Screen-space center of the canvas container
    const screenCenter = {
      x: bounds.left + bounds.width / 2,
      y: bounds.top + bounds.height / 2,
    }
    // Convert screen center → flow coordinates (accounts for zoom + pan)
    return screenToFlowPosition(screenCenter)
  }, [screenToFlowPosition])

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

      // Trigger auto-wiring suggestions for the newly dropped block
      setTimeout(() => {
        const state = usePipelineStore.getState()
        const newestNode = state.nodes[state.nodes.length - 1]
        if (newestNode) {
          triggerAutoWiring(newestNode.id)
        }
      }, 50)
    },
    [addNode, triggerAutoWiring]
  )

  // Auto-wiring: trigger on node drag stop (debounced)
  const dragStopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onNodeDragStop = useCallback((_: any, node: any) => {
    if (dragStopTimerRef.current) clearTimeout(dragStopTimerRef.current)
    dragStopTimerRef.current = setTimeout(() => {
      triggerAutoWiring(node.id)
    }, 200)
  }, [triggerAutoWiring])

  // Cleanup drag stop timer on unmount
  useEffect(() => {
    return () => {
      if (dragStopTimerRef.current) clearTimeout(dragStopTimerRef.current)
    }
  }, [])

  // Auto-dismiss suggestions after 5 seconds
  const suggestionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (connectionSuggestions.length > 0) {
      if (suggestionTimerRef.current) clearTimeout(suggestionTimerRef.current)
      suggestionTimerRef.current = setTimeout(() => {
        clearConnectionSuggestions()
      }, 5000)
    }
    return () => {
      if (suggestionTimerRef.current) clearTimeout(suggestionTimerRef.current)
    }
  }, [connectionSuggestions, clearConnectionSuggestions])

  // Wrap onConnect to also clear suggestions on manual edge creation
  const handleManualConnect = useCallback((connection: Connection) => {
    onConnect(connection)
    clearConnectionSuggestions()
  }, [onConnect, clearConnectionSuggestions])

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

    const sourcePort = resolvePort(sourceDef.outputs, connection.sourceHandle)
    const targetPort = resolvePort(targetDef.inputs, connection.targetHandle)
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
    clearConnectionSuggestions()
  }, [selectNode, deactivateInheritanceOverlay, clearConnectionSuggestions])

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
    const port = resolvePort(def.outputs, params.handleId)
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
    const port = resolvePort(def.outputs, edge.sourceHandle)
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
        // Find best input port — prefer alias-matched ports over plain type matches
        const sourceNode = state.nodes.find((n) => n.id === paletteParams.sourceNodeId)
        const sourceDef = sourceNode ? getBlockDefinition(sourceNode.data.type) : undefined
        const sourcePort = sourceDef?.outputs.find((p: PortDefinition) => p.id === paletteParams.sourceHandleId)

        const targetPort = sourcePort
          ? findBestInputPort(sourcePort, newDef.inputs)
          : newDef.inputs.find((i) => i.dataType === paletteParams.sourceType || i.dataType === 'any')
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

  // Accept a connection suggestion
  const handleAcceptSuggestion = useCallback((s: typeof connectionSuggestions[number]) => {
    onConnect({
      source: s.sourceNodeId,
      sourceHandle: s.sourcePortId,
      target: s.targetNodeId,
      targetHandle: s.targetPortId,
    })
    clearConnectionSuggestions()
  }, [onConnect, clearConnectionSuggestions])

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
        // Dismiss auto-wiring suggestions first
        const { connectionSuggestions: currentSuggestions } = usePipelineStore.getState()
        if (currentSuggestions.length > 0) {
          usePipelineStore.getState().clearConnectionSuggestions()
          return
        }
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
      } else if (meta && e.key === 'd') {
        // Cmd/Ctrl+D — duplicate selected nodes
        e.preventDefault()
        if (selectedIds.length > 0) {
          usePipelineStore.getState().duplicateNodes(selectedIds)
        }
      } else if (meta && e.key === 'Enter') {
        // Cmd/Ctrl+Enter to run pipeline
        e.preventDefault()
        const runBtn = document.querySelector('[data-tour="btn-run-pipeline"]') as HTMLButtonElement
        if (runBtn) runBtn.click()
      } else if (e.shiftKey && e.key === '?') {
        // Shift+? — open keyboard cheatsheet
        e.preventDefault()
        window.dispatchEvent(new CustomEvent('blueprint:toggle-cheatsheet'))
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [fitView, selectNode])

  // Listen for block doc custom events from BlockNode '?' button and palette hover
  useEffect(() => {
    const showHandler = (e: Event) => {
      const { blockType, anchor } = (e as CustomEvent).detail
      showBlockDoc(blockType, anchor)
    }
    const hideHandler = () => hideBlockDoc()
    window.addEventListener('blueprint:show-block-doc', showHandler)
    window.addEventListener('blueprint:hide-block-doc', hideHandler)
    return () => {
      window.removeEventListener('blueprint:show-block-doc', showHandler)
      window.removeEventListener('blueprint:hide-block-doc', hideHandler)
    }
  }, [showBlockDoc, hideBlockDoc])

  // Close context menu on outside click
  useEffect(() => {
    if (!contextMenu.visible) return
    const handler = () => setContextMenu((p) => ({ ...p, visible: false }))
    window.addEventListener('click', handler)
    return () => window.removeEventListener('click', handler)
  }, [contextMenu.visible])

  // Recompute edge colors for loaded pipelines (onConnect already sets them for new edges).
  // Also applies inheritance overlay styling when active, and validation error styling.
  const edgeErrors = useValidationStore((s) => s.edgeErrors)
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
        const port = def ? resolvePort(def.outputs, edge.sourceHandle) : undefined
        baseStroke = port ? getPortColor(port.dataType) : T.borderHi
      }

      // Inheritance overlay styling (takes precedence)
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

      // Validation error edges get custom edge type for red dashed rendering
      const hasEdgeError = !!edgeErrors[edge.id]
      if (hasEdgeError) {
        return {
          ...edge,
          type: 'validationEdge',
          style: { ...edge.style, stroke: baseStroke, strokeWidth: 1.5 },
          animated: false,
        }
      }

      return { ...edge, style: { ...edge.style, stroke: baseStroke, strokeWidth: 1.5 } }
    })
  }, [edges, inheritanceOverlay, edgeErrors])

  return (
    <div
      data-testid="pipeline-canvas"
      ref={reactFlowRef}
      onDragLeave={onDragLeave}
      style={{
        flex: 1,
        height: '100%',
        position: 'relative',
        overflow: 'hidden',
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
      {/* Empty canvas guidance — contained within canvas, not overlapping sidebars */}
      {nodes.length === 0 && (
        <div style={{
          position: 'absolute',
          top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)',
          zIndex: 10,
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          pointerEvents: 'none', gap: 20,
          maxWidth: 360,
        }}>
          <div style={{
            width: 44, height: 44, borderRadius: 10,
            background: `${T.cyan}10`, border: `1px solid ${T.cyan}20`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <SparklesIcon size={22} color={T.cyan} strokeWidth={1.2} />
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{
              fontFamily: FD, fontSize: 16, color: T.sec,
              fontWeight: 500, letterSpacing: '0.04em', marginBottom: 4,
            }}>
              Start building your pipeline
            </div>
            <div style={{
              fontFamily: F, fontSize: FS.xs, color: T.dim,
              maxWidth: 280, lineHeight: 1.5,
            }}>
              Drag a block from the library, or use one of the options below
            </div>
          </div>
          <div style={{
            display: 'flex', gap: 8, pointerEvents: 'auto',
          }}>
            {onShowTemplates && (
              <button
                onClick={onShowTemplates}
                style={{
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                  padding: '12px 14px', background: `${T.blue}08`,
                  border: `1px solid ${T.blue}25`, borderRadius: 8,
                  cursor: 'pointer', transition: 'all 0.15s', minWidth: 90,
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = `${T.blue}15`; e.currentTarget.style.borderColor = `${T.blue}40` }}
                onMouseLeave={(e) => { e.currentTarget.style.background = `${T.blue}08`; e.currentTarget.style.borderColor = `${T.blue}25` }}
              >
                <LayoutTemplate size={16} color={T.blue} />
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.blue, fontWeight: 700 }}>Templates</span>
              </button>
            )}
            {onShowAgent && (
              <button
                onClick={onShowAgent}
                style={{
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                  padding: '12px 14px', background: `${T.purple}08`,
                  border: `1px solid ${T.purple}25`, borderRadius: 8,
                  cursor: 'pointer', transition: 'all 0.15s', minWidth: 90,
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = `${T.purple}15`; e.currentTarget.style.borderColor = `${T.purple}40` }}
                onMouseLeave={(e) => { e.currentTarget.style.background = `${T.purple}08`; e.currentTarget.style.borderColor = `${T.purple}25` }}
              >
                <SparklesIcon size={16} color={T.purple} />
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.purple, fontWeight: 700 }}>AI Generate</span>
              </button>
            )}
            <button
              onClick={() => {
                const el = document.querySelector('input[placeholder="Search components..."]') as HTMLInputElement
                if (el) { el.focus(); el.select() }
              }}
              style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
                padding: '12px 14px', background: `${T.cyan}08`,
                border: `1px solid ${T.cyan}25`, borderRadius: 8,
                cursor: 'pointer', transition: 'all 0.15s', minWidth: 90,
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = `${T.cyan}15`; e.currentTarget.style.borderColor = `${T.cyan}40` }}
              onMouseLeave={(e) => { e.currentTarget.style.background = `${T.cyan}08`; e.currentTarget.style.borderColor = `${T.cyan}25` }}
            >
              <SearchIcon size={16} color={T.cyan} />
              <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.cyan, fontWeight: 700 }}>Add Block</span>
            </button>
          </div>
          <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 4 }}>
            or press <span style={{
              padding: '1px 5px', background: T.surface2, border: `1px solid ${T.border}`,
              borderRadius: 3, fontFamily: F, fontSize: 10, fontWeight: 600,
            }}>Space</span> to search blocks
          </div>
        </div>
      )}

      <ReactFlow
        nodes={nodes}
        edges={coloredEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={handleManualConnect}
        onConnectStart={onConnectStart}
        onConnectEnd={onConnectEnd}
        onEdgeMouseEnter={onEdgeMouseEnter}
        onEdgeMouseLeave={onEdgeMouseLeave}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onNodeDragStop={onNodeDragStop}
        onNodeClick={onNodeClick}
        onNodeContextMenu={onNodeContextMenu}
        onPaneClick={onPaneClick}
        isValidConnection={isValidConnection}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
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
        onShowDoc={(blockType) => showBlockDoc(blockType, { x: contextMenu.x, y: contextMenu.y })}
        onInspectConfig={(nid) => setInspectNodeId(nid)}
      />

      {/* Config Inspector panel */}
      {inspectNodeId && (
        <ConfigInspector
          nodeId={inspectNodeId}
          onClose={() => setInspectNodeId(null)}
        />
      )}

      {/* Re-run mode overlay */}
      <RerunOverlay />

      {/* Block search modal (Cmd+K) */}
      <BlockSearch
        onAddBlock={addNode}
        onShowBlockDoc={(blockType) => showBlockDoc(blockType)}
        getViewportCenter={getViewportCenter}
      />

      {/* Contextual block suggestions when a node is selected */}
      <BlockSuggestions
        flowToScreenPosition={flowToScreenPosition}
        containerRef={reactFlowRef}
      />

      {/* Block documentation popover */}
      <BlockDoc
        blockType={blockDocState.blockType}
        anchor={blockDocState.anchor}
        visible={blockDocState.visible}
        onClose={hideBlockDoc}
      />

      {/* Auto-wiring suggestions popup */}
      {connectionSuggestions.length > 0 && (() => {
        // Position popup near the node that was dropped/moved
        const anchorNodeId = autoWiringNodeId ?? connectionSuggestions[0].targetNodeId
        const anchorNode = nodes.find((n) => n.id === anchorNodeId)
        if (!anchorNode) return null
        const def = getBlockDefinition((anchorNode.data as any)?.type)
        // Use actual measured width if available, fall back to computed width
        const blockW = anchorNode.measured?.width ?? (def ? computeBlockWidth(def) : 280)

        // Convert flow coordinates → screen coordinates
        const screenPos = flowToScreenPosition({
          x: anchorNode.position.x + blockW + 16,
          y: anchorNode.position.y,
        })

        // Offset by the container's bounding rect so it's positioned inside the outer div
        const containerRect = reactFlowRef.current?.getBoundingClientRect()
        const containerW = containerRect?.width ?? 0
        const containerH = containerRect?.height ?? 0
        let popupLeft = screenPos.x - (containerRect?.left ?? 0)
        let popupTop = screenPos.y - (containerRect?.top ?? 0)

        // Clamp to viewport bounds (estimate popup size: 240px wide, ~30px per item + header)
        const popupW = 240
        const popupH = 28 + connectionSuggestions.length * 30
        if (popupLeft + popupW > containerW) popupLeft = Math.max(8, containerW - popupW - 8)
        if (popupTop + popupH > containerH) popupTop = Math.max(8, containerH - popupH - 8)
        if (popupLeft < 8) popupLeft = 8
        if (popupTop < 8) popupTop = 8

        return (
          <div
            style={{
              position: 'absolute',
              left: popupLeft,
              top: popupTop,
              background: T.surface4,
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              padding: 8,
              zIndex: 100,
              maxWidth: popupW,
              boxShadow: T.shadow,
              pointerEvents: 'auto',
            }}
          >
            <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 4 }}>
              Suggested connections:
            </div>
            {connectionSuggestions.map((s) => (
              <button
                key={`${s.sourceNodeId}:${s.sourcePortId}-${s.targetNodeId}:${s.targetPortId}`}
                onClick={() => handleAcceptSuggestion(s)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  width: '100%',
                  padding: '4px 8px',
                  marginBottom: 2,
                  background: 'transparent',
                  border: `1px solid ${T.border}`,
                  borderRadius: 4,
                  color: T.text,
                  fontFamily: F,
                  fontSize: FS.xxs,
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
                onMouseEnter={(e) => {
                  ;(e.currentTarget as HTMLButtonElement).style.background = T.surface2
                  ;(e.currentTarget as HTMLButtonElement).style.borderColor = T.cyan
                }}
                onMouseLeave={(e) => {
                  ;(e.currentTarget as HTMLButtonElement).style.background = 'transparent'
                  ;(e.currentTarget as HTMLButtonElement).style.borderColor = T.border
                }}
              >
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    background: getPortColor(s.dataType),
                    flexShrink: 0,
                  }}
                />
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.label}
                </span>
              </button>
            ))}
          </div>
        )
      })()}
    </div>
  )
}
