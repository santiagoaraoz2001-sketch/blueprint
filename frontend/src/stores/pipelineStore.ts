import { create } from 'zustand'
import {
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  type OnConnect,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
} from '@xyflow/react'
import { api } from '@/api/client'
import { getBlockDefinition, getPortColor, isPortCompatible, type PortDefinition } from '@/lib/block-registry'
import { getLayoutedElements } from '@/lib/layout-utils'
import { useSettingsStore } from './settingsStore'
import { DEMO_PIPELINE, DEMO_PIPELINES_LIST } from '@/lib/demo-data'
import toast from 'react-hot-toast'
import { useUIStore } from './uiStore'

export interface BlockNodeData {
  type: string
  label: string
  category: string
  icon: string
  accent: string
  config: Record<string, any>
  inputs?: PortDefinition[]
  outputs?: PortDefinition[]
  status: 'idle' | 'running' | 'complete' | 'failed'
  progress: number
  [key: string]: unknown
}

export interface PipelineSummary {
  id: string
  name: string
  block_count: number
  created_at: string
  updated_at: string
}

export interface PipelineTab {
  id: string
  name: string
  nodes: Node<BlockNodeData>[]
  edges: Edge[]
  pipelineId: string | null  // backend pipeline ID
  isDirty: boolean
  runStatus: 'idle' | 'running' | 'complete' | 'failed' | 'cancelled'
  past: { nodes: Node<BlockNodeData>[]; edges: Edge[] }[]
  future: { nodes: Node<BlockNodeData>[]; edges: Edge[] }[]
}

export interface PipelineSnapshot {
  id: string
  timestamp: string
  name: string
  nodes: any[]
  edges: any[]
}

export type NodeExecutionState =
  | 'idle'
  | 'cached'
  | 'will_rerun'
  | 'will_rerun_downstream'
  | 'running'
  | 'complete'
  | 'failed'

export interface RerunMode {
  active: boolean
  sourceRunId: string
  startNodeId: string
  nodeStates: Record<string, NodeExecutionState>
  configOverrides: Record<string, Record<string, any>>
  originalConfigs: Record<string, Record<string, any>>
  downstreamNodes: string[]
  cachedNodes: string[]
}

export interface ResolvedInheritedEntry {
  from_node: string
  value: any
}

export interface ResolvedNodeConfig {
  [key: string]: any
  _inherited?: Record<string, ResolvedInheritedEntry>
}

export interface PropagationKeys {
  global: string[]
  by_category: Record<string, string[]>
}

interface PipelineState {
  id: string | null
  name: string
  nodes: Node<BlockNodeData>[]
  edges: Edge[]
  selectedNodeId: string | null
  focusedErrorNodeId: string | null
  isDirty: boolean

  // Config inheritance from resolve-config API
  resolvedConfigs: Record<string, ResolvedNodeConfig>
  propagationKeys: PropagationKeys | null
  resolveConfigs: (pipelineId: string) => Promise<void>

  // Multi-pipeline management
  pipelines: PipelineSummary[]
  pipelinesLoading: boolean

  // Pipeline Tabs (multiple simultaneous pipelines)
  tabs: PipelineTab[]
  activeTabId: string

  // Undo/Redo history
  past: { nodes: Node<BlockNodeData>[]; edges: Edge[] }[]
  future: { nodes: Node<BlockNodeData>[]; edges: Edge[] }[]
  pushHistory: () => void
  undo: () => void
  redo: () => void

  // Version history
  versions: PipelineSnapshot[]

  onNodesChange: OnNodesChange<Node<BlockNodeData>>
  onEdgesChange: OnEdgesChange
  onConnect: OnConnect

  addNode: (type: string, position: { x: number; y: number }) => void
  addStickyNote: (position: { x: number; y: number }) => void
  updateStickyNote: (id: string, data: Partial<{ text: string; color: string; width: number; height: number }>) => void
  removeNode: (id: string) => void
  removeSelectedNodes: () => void
  duplicateNodes: (nodeIds: string[], offset?: { x: number; y: number }) => void
  updateNodeConfig: (id: string, config: Record<string, any>) => void
  selectNode: (id: string | null) => void
  focusErrorNode: (id: string | null) => void
  saveAsTemplate: (name: string, description: string, category: string) => void
  groupSelectedNodes: () => void
  ungroupSelectedNodes: () => void
  tidyUp: () => void
  setName: (name: string) => void
  loadPipeline: (id: string) => Promise<void>
  savePipeline: () => Promise<void>
  newPipeline: (projectId?: string) => void

  // Multi-pipeline actions
  fetchPipelines: () => Promise<void>
  deletePipeline: (id: string) => Promise<void>
  duplicatePipeline: (id: string) => Promise<void>
  exportPipeline: () => void
  importPipeline: (json: string) => void

  // Tab actions
  addTab: (name?: string) => void
  removeTab: (tabId: string) => void
  switchTab: (tabId: string) => void
  renameTab: (tabId: string, name: string) => void
  duplicateTab: (tabId: string) => void
  updateTabRunStatus: (tabId: string, status: PipelineTab['runStatus']) => void

  // Version history actions
  saveSnapshot: () => void
  restoreVersion: (id: string) => void

  // Agentic workflow
  applyGeneratedWorkflow: (nodes: Node<BlockNodeData>[], edges: Edge[]) => void

  // Re-run mode
  rerunMode: RerunMode | null
  enterRerunMode: (startNodeId: string, sourceRunId: string) => void
  exitRerunMode: (restoreConfigs?: boolean) => void
  updateRerunConfigOverride: (nodeId: string, config: Record<string, any>) => void
  getDownstreamNodes: (startNodeId: string) => string[]
  getUpstreamNodes: (startNodeId: string) => string[]
}

let nodeIdCounter = 0
let tabIdCounter = 0

function _makeTabId() {
  return `tab_${++tabIdCounter}_${Date.now()}`
}

const DEFAULT_TAB_ID = _makeTabId()

function isDemoMode() {
  return useSettingsStore.getState().demoMode
}

/** Retroactively inject port definitions from block-registry for nodes missing them (backward compat). */
function _hydrateNodePorts(nodes: Node<BlockNodeData>[]): Node<BlockNodeData>[] {
  return nodes.map((node) => {
    if (node.data && node.data.type && (!node.data.inputs || !node.data.outputs)) {
      const def = getBlockDefinition(node.data.type)
      if (def) {
        return {
          ...node,
          data: {
            ...node.data,
            inputs: node.data.inputs ?? def.inputs,
            outputs: node.data.outputs ?? def.outputs,
          },
        }
      }
    }
    return node
  })
}

/**
 * Helper: returns the history snapshot portion for a single set() call.
 * Call inside set() with the current state to push history + apply changes atomically.
 */
function _histSnapshot(s: { nodes: Node<BlockNodeData>[]; edges: Edge[]; past: { nodes: Node<BlockNodeData>[]; edges: Edge[] }[] }) {
  return {
    past: [...s.past, { nodes: [...s.nodes], edges: [...s.edges] }].slice(-50),
    future: [] as { nodes: Node<BlockNodeData>[]; edges: Edge[] }[],
  }
}

export const usePipelineStore = create<PipelineState>((set, get) => ({
  id: null,
  name: 'Untitled Pipeline',
  nodes: [],
  edges: [],
  selectedNodeId: null,
  focusedErrorNodeId: null,
  isDirty: false,
  pipelines: [],
  pipelinesLoading: false,
  tabs: [{ id: DEFAULT_TAB_ID, name: 'Pipeline 1', nodes: [], edges: [], pipelineId: null, isDirty: false, runStatus: 'idle', past: [], future: [] }],
  activeTabId: DEFAULT_TAB_ID,
  resolvedConfigs: {},
  propagationKeys: null,
  versions: [],
  past: [],
  future: [],

  pushHistory: () => {
    const { nodes, edges, past } = get()
    set({
      past: [...past, { nodes: [...nodes], edges: [...edges] }].slice(-50),
      future: [],
    })
  },

  undo: () => {
    const { past, future, nodes, edges } = get()
    if (past.length === 0) return
    const previous = past[past.length - 1]
    const newPast = past.slice(0, -1)
    set({
      past: newPast,
      future: [{ nodes: [...nodes], edges: [...edges] }, ...future],
      nodes: previous.nodes,
      edges: previous.edges,
      isDirty: true,
      selectedNodeId: null,
    })
  },

  redo: () => {
    const { past, future, nodes, edges } = get()
    if (future.length === 0) return
    const next = future[0]
    const newFuture = future.slice(1)
    set({
      past: [...past, { nodes: [...nodes], edges: [...edges] }],
      future: newFuture,
      nodes: next.nodes,
      edges: next.edges,
      isDirty: true,
      selectedNodeId: null,
    })
  },

  onNodesChange: (changes) => {
    // Determine if we should save undo history for this change batch.
    // NEVER push history for dimension measurements or mid-drag position updates —
    // these fire at 60fps and would cause "Maximum update depth exceeded".
    const shouldPushHistory = changes.some(c => {
      if (c.type === 'select') return false           // selection UI, not user edit
      if (c.type === 'dimensions') return false       // internal RF measurement
      if (c.type === 'position') return c.dragging !== true  // drag END only
      return true                                     // 'remove', 'add', 'reset'
    })

    const removeNodeIds = new Set<string>()
    changes.forEach(c => {
      if (c.type === 'remove') removeNodeIds.add(c.id)
    })

    let finalChanges = [...changes]
    if (removeNodeIds.size > 0) {
      const { nodes } = get()
      const childrenToRemove = nodes.filter(n => n.parentId && removeNodeIds.has(n.parentId)).map(n => n.id)
      childrenToRemove.forEach(id => {
        if (!removeNodeIds.has(id)) {
          finalChanges.push({ type: 'remove', id })
        }
      })
    }

    const isUserChange = changes.some(c => c.type !== 'dimensions' && c.type !== 'select')

    // SINGLE set() call — merges history snapshot + node changes atomically.
    set((s) => ({
      ...(shouldPushHistory ? _histSnapshot(s) : {}),
      nodes: applyNodeChanges(finalChanges, s.nodes) as Node<BlockNodeData>[],
      ...(isUserChange ? { isDirty: true } : {}),
    }))
  },

  onEdgesChange: (changes) => {
    const isSignificant = changes.some(c => c.type !== 'select')

    // SINGLE set() call — merges history snapshot + edge changes atomically.
    set((s) => ({
      ...(isSignificant ? _histSnapshot(s) : {}),
      edges: applyEdgeChanges(changes, s.edges),
      ...(isSignificant ? { isDirty: true } : {}),
    }))
  },

  onConnect: (connection) => {
    const { nodes } = get()
    const sourceNode = nodes.find((n) => n.id === connection.source)
    const targetNode = nodes.find((n) => n.id === connection.target)

    if (sourceNode && targetNode) {
      const sourceDef = getBlockDefinition(sourceNode.data.type)
      const targetDef = getBlockDefinition(targetNode.data.type)

      if (sourceDef && targetDef) {
        const sourcePort = sourceDef.outputs.find((p) => p.id === connection.sourceHandle)
        const targetPort = targetDef.inputs.find((p) => p.id === connection.targetHandle)

        if (sourcePort && targetPort && !isPortCompatible(sourcePort.dataType, targetPort.dataType)) {
          toast.error(`Type mismatch: ${sourcePort.dataType} \u2192 ${targetPort.dataType}`)
          return
        }

        const edgeColor = sourcePort ? getPortColor(sourcePort.dataType) : '#222222'

        set((s) => ({
          ..._histSnapshot(s),
          edges: addEdge(
            {
              ...connection,
              type: 'smoothstep',
              animated: true,
              style: { stroke: edgeColor, strokeWidth: 1.5 },
            },
            s.edges
          ),
          isDirty: true,
        }))
        return
      }
    }

    set((s) => ({
      ..._histSnapshot(s),
      edges: addEdge(
        { ...connection, type: 'smoothstep', animated: true },
        s.edges
      ),
      isDirty: true,
    }))
  },

  addNode: (type, position) => {
    const def = getBlockDefinition(type)
    if (!def) return
    const id = `block_${++nodeIdCounter}_${Date.now()}`
    const newNode: Node<BlockNodeData> = {
      id,
      type: 'blockNode',
      position,
      data: {
        type: def.type,
        label: def.name,
        category: def.category,
        icon: def.icon,
        accent: def.accent,
        config: { ...def.defaultConfig },
        inputs: def.inputs,
        outputs: def.outputs,
        status: 'idle',
        progress: 0,
      },
    }
    set((s) => ({
      ..._histSnapshot(s),
      nodes: [...s.nodes, newNode],
      isDirty: true,
      selectedNodeId: id,
    }))
  },

  addStickyNote: (position) => {
    const id = `sticky_${++nodeIdCounter}_${Date.now()}`
    const newNode: Node<any> = {
      id,
      type: 'stickyNote',
      position,
      data: {
        text: '',
        color: 'yellow',
        width: 200,
        height: 120,
      },
    }
    set((s) => ({
      ..._histSnapshot(s),
      nodes: [...s.nodes, newNode] as Node<BlockNodeData>[],
      isDirty: true,
      selectedNodeId: id,
    }))
  },

  updateStickyNote: (id, data) => {
    set((s) => ({
      ..._histSnapshot(s),
      nodes: s.nodes.map((n) =>
        n.id === id ? { ...n, data: { ...n.data, ...data } } : n
      ) as Node<BlockNodeData>[],
      isDirty: true,
    }))
  },

  removeNode: (id) => {
    // Find all nodes to remove (the node itself, plus any children if it's a group)
    const nodesToRemove = new Set<string>([id])
    get().nodes.forEach(n => {
      if (n.parentId === id) nodesToRemove.add(n.id)
    })

    set((s) => ({
      ..._histSnapshot(s),
      nodes: s.nodes.filter((n) => !nodesToRemove.has(n.id)),
      edges: s.edges.filter((e) => !nodesToRemove.has(e.source) && !nodesToRemove.has(e.target)),
      selectedNodeId: s.selectedNodeId && nodesToRemove.has(s.selectedNodeId) ? null : s.selectedNodeId,
      isDirty: true,
    }))
  },

  removeSelectedNodes: () => {
    const selected = get().nodes.filter((n) => n.selected)
    if (selected.length === 0) return
    const ids = new Set(selected.map((n) => n.id))
    set((s) => ({
      ..._histSnapshot(s),
      nodes: s.nodes.filter((n) => !ids.has(n.id)),
      edges: s.edges.filter((e) => !ids.has(e.source) && !ids.has(e.target)),
      selectedNodeId: null,
      isDirty: true,
    }))
  },

  duplicateNodes: (nodeIds, offset = { x: 40, y: 40 }) => {
    const { nodes, edges } = get()
    const idSet = new Set(nodeIds)
    const toDuplicate = nodes.filter((n) => idSet.has(n.id))
    if (toDuplicate.length === 0) return

    const idMap = new Map<string, string>()
    const newNodes = toDuplicate.map((n) => {
      const newId = `node-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      idMap.set(n.id, newId)
      return {
        ...n,
        id: newId,
        position: { x: n.position.x + offset.x, y: n.position.y + offset.y },
        selected: true,
        data: { ...n.data, status: 'idle' as const, progress: 0 },
      }
    })

    // Re-wire internal edges
    const internalEdges = edges
      .filter((e) => idSet.has(e.source) && idSet.has(e.target))
      .map((e) => ({
        ...e,
        id: `edge-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        source: idMap.get(e.source) || e.source,
        target: idMap.get(e.target) || e.target,
      }))

    // Deselect originals
    const deselected = nodes.map((n) => ({ ...n, selected: false }))

    set((s) => ({
      ..._histSnapshot(s),
      nodes: [...deselected, ...newNodes],
      edges: [...edges, ...internalEdges],
      isDirty: true,
    }))
  },

  updateNodeConfig: (id, config) => {
    set((s) => ({
      ..._histSnapshot(s),
      nodes: s.nodes.map((n) => {
        if (n.id !== id) return n
        const newConfig = { ...n.data.config }
        for (const [key, value] of Object.entries(config)) {
          if (value === undefined || value === null) {
            delete newConfig[key]  // Remove → reverts to inherited/default
          } else {
            newConfig[key] = value
          }
        }
        return { ...n, data: { ...n.data, config: newConfig } }
      }),
      isDirty: true,
    }))
  },

  selectNode: (id) => set({ selectedNodeId: id }),

  focusErrorNode: (id) => {
    set({ focusedErrorNodeId: id })
    if (id) {
      // Clear the error focus after 3 seconds of pulsing
      setTimeout(() => {
        if (get().focusedErrorNodeId === id) {
          set({ focusedErrorNodeId: null })
        }
      }, 3000)
    }
  },

  groupSelectedNodes: () => {
    const { nodes } = get()
    const selected = nodes.filter((n) => n.selected && !n.parentId)
    if (selected.length < 2) {
      toast.error('Select at least 2 nodes to group')
      return
    }

    // Calculate bounding box + padding
    const padding = 40
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    selected.forEach((n) => {
      minX = Math.min(minX, n.position.x)
      minY = Math.min(minY, n.position.y)
      // Estimate width/height if internal
      maxX = Math.max(maxX, n.position.x + (n.measured?.width || 250))
      maxY = Math.max(maxY, n.position.y + (n.measured?.height || 100))
    })

    const groupWidth = (maxX - minX) + padding * 2
    const groupHeight = (maxY - minY) + padding * 2 + 30 // Extra top padding

    const groupId = `group_${++nodeIdCounter}_${Date.now()}`
    const groupNode: Node<any> = {
      id: groupId,
      type: 'groupNode',
      position: { x: minX - padding, y: minY - padding - 30 },
      style: { width: groupWidth, height: groupHeight },
      data: { label: 'Sub-Flow Group' },
    }

    // Adjust selected nodes to be relative to the group
    const updatedSelected = selected.map((n) => ({
      ...n,
      parentId: groupId,
      position: {
        x: n.position.x - (minX - padding),
        y: n.position.y - (minY - padding - 30),
      },
      selected: false,
    }))

    const idSet = new Set(selected.map((n) => n.id))
    set((s) => ({
      ..._histSnapshot(s),
      nodes: [...s.nodes.filter((n) => !idSet.has(n.id)), groupNode, ...updatedSelected] as Node<BlockNodeData>[],
      isDirty: true,
      selectedNodeId: groupId,
    }))
    toast.success('Nodes grouped')
  },

  ungroupSelectedNodes: () => {
    const { nodes } = get()
    const groups = nodes.filter((n) => n.selected && n.type === 'groupNode')
    if (groups.length === 0) {
      toast.error('Select a group to ungroup')
      return
    }

    // Remove the groups and un-parent their children
    const groupIds = new Set(groups.map((n) => n.id))
    const groupMap = new Map(groups.map((n) => [n.id, n]))

    const nextNodes = nodes.filter((n) => !groupIds.has(n.id)).map((n) => {
      if (n.parentId && groupIds.has(n.parentId)) {
        const group = groupMap.get(n.parentId)!
        return {
          ...n,
          parentId: undefined,
          position: {
            x: n.position.x + group.position.x,
            y: n.position.y + group.position.y,
          },
          selected: true,
        }
      }
      return n
    })

    set((s) => ({
      ..._histSnapshot(s),
      nodes: nextNodes as Node<BlockNodeData>[],
      isDirty: true,
    }))
    toast.success('Flow ungrouped')
  },

  tidyUp: () => {
    const { nodes, edges } = get()
    if (nodes.length === 0) return

    // Calculate new layout
    const layoutedNodes = getLayoutedElements(nodes, edges, 'LR')

    set((s) => ({
      ..._histSnapshot(s),
      nodes: layoutedNodes as Node<BlockNodeData>[],
      isDirty: true,
    }))
    toast.success('Pipeline organized')
  },

  setName: (name) => set({ name, isDirty: true }),

  loadPipeline: async (id) => {
    if (isDemoMode()) {
      // In demo mode, load the demo pipeline for any ID
      const def = DEMO_PIPELINE.definition
      set({
        id: DEMO_PIPELINE.id,
        name: DEMO_PIPELINE.name,
        nodes: _hydrateNodePorts(def.nodes as any[]),
        edges: def.edges as any[],
        isDirty: false,
        selectedNodeId: null,
      })
      return
    }
    try {
      const pipeline = await api.get<any>(`/pipelines/${id}`)
      const def = pipeline.definition || {}
      set({
        id: pipeline.id,
        name: pipeline.name,
        nodes: _hydrateNodePorts(def.nodes || []),
        edges: def.edges || [],
        isDirty: false,
        selectedNodeId: null,
        resolvedConfigs: {},
        propagationKeys: null,
      })
      // Resolve config inheritance after loading pipeline
      get().resolveConfigs(id)
    } catch {
      toast.error('Failed to load pipeline')
    }
  },

  resolveConfigs: async (pipelineId: string) => {
    try {
      const res = await api.post<{ resolved: Record<string, ResolvedNodeConfig>; propagation_keys: PropagationKeys }>(
        `/pipelines/${pipelineId}/resolve-config`
      )
      set({ resolvedConfigs: res.resolved || {}, propagationKeys: res.propagation_keys || null })
    } catch {
      // Silently fail — inheritance display is best-effort
      set({ resolvedConfigs: {}, propagationKeys: null })
    }
  },

  savePipeline: async () => {
    const { id, name, nodes, edges } = get()
    const definition = { nodes, edges }

    // Save a version snapshot before persisting
    get().saveSnapshot()

    if (isDemoMode()) {
      // In demo mode, just mark as saved (in-memory only)
      if (!id) set({ id: `demo-saved-${Date.now()}` })
      set({ isDirty: false })
      return
    }

    if (id) {
      await api.put(`/pipelines/${id}`, { name, definition })
    } else {
      const projectId = useUIStore.getState().selectedProjectId
      const payload: any = { name, definition }
      if (projectId) payload.project_id = projectId

      const created = await api.post<any>('/pipelines', payload)
      set({ id: created.id })
    }
    set({ isDirty: false })
    // Re-resolve config inheritance with persisted data
    const pipelineId = get().id
    if (pipelineId) {
      get().resolveConfigs(pipelineId)
    }
  },

  newPipeline: () => {
    nodeIdCounter = 0
    const { activeTabId } = get()
    set((s) => ({
      id: null,
      name: 'Untitled Pipeline',
      nodes: [],
      edges: [],
      selectedNodeId: null,
      isDirty: false,
      resolvedConfigs: {},
      propagationKeys: null,
      tabs: s.tabs.map((t) =>
        t.id === activeTabId
          ? { ...t, nodes: [], edges: [], pipelineId: null, isDirty: false, name: 'Untitled Pipeline' }
          : t
      ),
    }))
  },

  // Multi-pipeline management
  fetchPipelines: async () => {
    set({ pipelinesLoading: true })
    const projectId = useUIStore.getState().selectedProjectId

    if (isDemoMode()) {
      set({
        pipelines: DEMO_PIPELINES_LIST.map((p) => ({
          id: p.id,
          name: p.name,
          block_count: p.block_count,
          created_at: p.created_at,
          updated_at: p.updated_at,
        })),
        pipelinesLoading: false,
      })
      return
    }
    try {
      const url = projectId ? `/pipelines?project_id=${projectId}` : '/pipelines'
      const list = await api.get<any[]>(url)
      set({
        pipelines: (list || []).map((p: any) => ({
          id: p.id,
          name: p.name || 'Untitled',
          block_count: p.definition?.nodes?.length || 0,
          created_at: p.created_at || '',
          updated_at: p.updated_at || '',
        })),
        pipelinesLoading: false,
      })
    } catch {
      set({ pipelinesLoading: false })
    }
  },

  deletePipeline: async (id) => {
    if (isDemoMode()) {
      set((s) => ({ pipelines: s.pipelines.filter((p) => p.id !== id) }))
      if (get().id === id) get().newPipeline()
      toast.success('Pipeline deleted')
      return
    }

    // Optimistic removal: instantly update the UI, rollback on API failure
    const previousPipelines = [...get().pipelines]
    const wasActive = get().id === id
    set((s) => ({ pipelines: s.pipelines.filter((p) => p.id !== id) }))
    if (wasActive) get().newPipeline()

    try {
      await api.delete(`/pipelines/${id}`)
      toast.success('Pipeline deleted')
    } catch {
      // Rollback: restore the pipeline list on failure
      set({ pipelines: previousPipelines })
      toast.error('Failed to delete pipeline')
    }
  },

  duplicatePipeline: async (id) => {
    if (isDemoMode()) {
      const existing = get().pipelines.find((p) => p.id === id)
      if (existing) {
        const copy: PipelineSummary = {
          ...existing,
          id: `demo-dup-${Date.now()}`,
          name: `${existing.name} (Copy)`,
        }
        set((s) => ({ pipelines: [...s.pipelines, copy] }))
        toast.success('Pipeline duplicated')
      }
      return
    }
    try {
      const pipeline = await api.get<any>(`/pipelines/${id}`)
      const created = await api.post<any>('/pipelines', {
        name: `${pipeline.name} (Copy)`,
        definition: pipeline.definition,
      })
      toast.success('Pipeline duplicated')
      get().fetchPipelines()
      return created
    } catch {
      toast.error('Failed to duplicate pipeline')
    }
  },

  exportPipeline: () => {
    const { name, nodes, edges } = get()
    const data = JSON.stringify({ name, nodes, edges }, null, 2)
    const blob = new Blob([data], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${name.replace(/\s+/g, '_').toLowerCase()}.blueprint.json`
    a.click()
    URL.revokeObjectURL(url)
    toast.success('Pipeline exported')
  },

  importPipeline: (json) => {
    try {
      const data = JSON.parse(json)
      if (!data.nodes || !Array.isArray(data.nodes)) {
        toast.error('Invalid pipeline file: missing nodes array')
        return
      }
      set({
        id: null,
        name: data.name || 'Imported Pipeline',
        nodes: _hydrateNodePorts(data.nodes),
        edges: data.edges || [],
        isDirty: true,
        selectedNodeId: null,
      })
      toast.success('Pipeline imported')
    } catch {
      toast.error('Invalid JSON file')
    }
  },

  // Version history
  saveSnapshot: () => {
    const { name, nodes, edges, versions } = get()
    const snapshot: PipelineSnapshot = {
      id: `snap_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      timestamp: new Date().toISOString(),
      name,
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
    }
    const updated = [snapshot, ...versions].slice(0, 50)
    set({ versions: updated })
  },

  restoreVersion: (id) => {
    const { versions } = get()
    const snapshot = versions.find((v) => v.id === id)
    if (!snapshot) {
      toast.error('Version not found')
      return
    }
    set({
      name: snapshot.name,
      nodes: _hydrateNodePorts(JSON.parse(JSON.stringify(snapshot.nodes))),
      edges: JSON.parse(JSON.stringify(snapshot.edges)),
      isDirty: true,
      selectedNodeId: null,
    })
    toast.success(`Restored version from ${new Date(snapshot.timestamp).toLocaleString()}`)
  },

  applyGeneratedWorkflow: (newNodes, newEdges) => {
    set((s) => ({
      ..._histSnapshot(s),
      nodes: [...s.nodes, ...newNodes] as Node<BlockNodeData>[],
      edges: [...s.edges, ...newEdges],
      isDirty: true,
    }))
    toast.success(`Added ${newNodes.length} blocks to canvas`)
  },

  // ── Re-run Mode ──
  rerunMode: null,

  getDownstreamNodes: (startNodeId: string) => {
    const { edges } = get()
    const downstream = new Set<string>()
    const queue = [startNodeId]
    while (queue.length > 0) {
      const current = queue.shift()!
      const outEdges = edges.filter(e => e.source === current)
      for (const edge of outEdges) {
        if (!downstream.has(edge.target) && edge.target !== startNodeId) {
          downstream.add(edge.target)
          queue.push(edge.target)
        }
      }
    }
    return Array.from(downstream)
  },

  getUpstreamNodes: (startNodeId: string) => {
    const { edges } = get()
    const upstream = new Set<string>()
    const queue = [startNodeId]
    while (queue.length > 0) {
      const current = queue.shift()!
      const inEdges = edges.filter(e => e.target === current)
      for (const edge of inEdges) {
        if (!upstream.has(edge.source) && edge.source !== startNodeId) {
          upstream.add(edge.source)
          queue.push(edge.source)
        }
      }
    }
    return Array.from(upstream)
  },

  enterRerunMode: (startNodeId: string, sourceRunId: string) => {
    const { nodes } = get()
    const store = get()

    // Validate that the start node exists
    const startNode = nodes.find((n) => n.id === startNodeId)
    if (!startNode || startNode.type !== 'blockNode') {
      toast.error('Cannot re-run from this node')
      return
    }

    const downstream = store.getDownstreamNodes(startNodeId)
    const upstream = store.getUpstreamNodes(startNodeId)

    const nodeStates: Record<string, NodeExecutionState> = {}
    const originalConfigs: Record<string, Record<string, any>> = {}

    for (const node of nodes) {
      if (node.type !== 'blockNode') continue
      if (upstream.includes(node.id)) {
        nodeStates[node.id] = 'cached'
      } else if (node.id === startNodeId) {
        nodeStates[node.id] = 'will_rerun'
        // Deep copy original config so edits don't mutate the snapshot
        originalConfigs[node.id] = JSON.parse(JSON.stringify(node.data.config || {}))
      } else if (downstream.includes(node.id)) {
        nodeStates[node.id] = 'will_rerun_downstream'
      } else {
        // Nodes not on the execution path (disconnected branches) are also cached
        nodeStates[node.id] = 'cached'
      }
    }

    set({
      rerunMode: {
        active: true,
        sourceRunId,
        startNodeId,
        nodeStates,
        configOverrides: {},
        originalConfigs,
        downstreamNodes: downstream,
        cachedNodes: upstream,
      },
      selectedNodeId: startNodeId,
    })
  },

  exitRerunMode: (restoreConfigs = true) => {
    const { rerunMode, nodes } = get()
    if (!rerunMode) {
      set({ rerunMode: null })
      return
    }

    if (restoreConfigs && Object.keys(rerunMode.originalConfigs).length > 0) {
      // Restore original configs for nodes that were edited during rerun mode
      const restoredNodes = nodes.map((n) => {
        const original = rerunMode.originalConfigs[n.id]
        if (original) {
          return { ...n, data: { ...n.data, config: JSON.parse(JSON.stringify(original)) } }
        }
        return n
      })
      set({ rerunMode: null, nodes: restoredNodes as Node<BlockNodeData>[] })
    } else {
      set({ rerunMode: null })
    }
  },

  updateRerunConfigOverride: (nodeId: string, config: Record<string, any>) => {
    const { rerunMode } = get()
    if (!rerunMode) return
    set({
      rerunMode: {
        ...rerunMode,
        configOverrides: {
          ...rerunMode.configOverrides,
          [nodeId]: { ...(rerunMode.configOverrides[nodeId] || {}), ...config },
        },
      },
    })
  },

  saveAsTemplate: (name: string, description: string, category: string) => {
    const state = get()
    const templates = JSON.parse(localStorage.getItem('blueprint-custom-templates') || '[]')
    templates.push({
      id: `tmpl_${Date.now()}`,
      name,
      description,
      category,
      nodes: state.nodes,
      edges: state.edges,
    })
    localStorage.setItem('blueprint-custom-templates', JSON.stringify(templates))
  },

  // ── Pipeline Tab Actions ──

  addTab: (tabName?: string) => {
    const { tabs, nodes, edges, id, name, isDirty, activeTabId, past, future } = get()
    // Save current tab state including undo/redo history
    const updatedTabs = tabs.map((t) =>
      t.id === activeTabId ? { ...t, nodes, edges, pipelineId: id, isDirty, name, past, future } : t
    )
    const newTabId = _makeTabId()
    const newTab: PipelineTab = {
      id: newTabId,
      name: tabName || `Pipeline ${tabs.length + 1}`,
      nodes: [],
      edges: [],
      pipelineId: null,
      isDirty: false,
      runStatus: 'idle',
      past: [],
      future: [],
    }
    set({
      tabs: [...updatedTabs, newTab],
      activeTabId: newTabId,
      id: null,
      name: newTab.name,
      nodes: [],
      edges: [],
      isDirty: false,
      selectedNodeId: null,
      past: [],
      future: [],
    })
  },

  removeTab: (tabId: string) => {
    const { tabs, activeTabId } = get()
    if (tabs.length <= 1) {
      toast.error('Cannot close the last tab')
      return
    }
    const idx = tabs.findIndex((t) => t.id === tabId)
    const newTabs = tabs.filter((t) => t.id !== tabId)

    if (tabId === activeTabId) {
      // Switch to adjacent tab and restore its undo/redo history
      const nextTab = newTabs[Math.min(idx, newTabs.length - 1)]
      set({
        tabs: newTabs,
        activeTabId: nextTab.id,
        id: nextTab.pipelineId,
        name: nextTab.name,
        nodes: nextTab.nodes,
        edges: nextTab.edges,
        isDirty: nextTab.isDirty,
        selectedNodeId: null,
        past: nextTab.past || [],
        future: nextTab.future || [],
      })
    } else {
      // Just remove the tab, keep current active
      set({ tabs: newTabs })
    }
  },

  switchTab: (tabId: string) => {
    const { tabs, activeTabId, nodes, edges, id, name, isDirty, past, future } = get()
    if (tabId === activeTabId) return

    // Save current tab state including undo/redo history
    const updatedTabs = tabs.map((t) =>
      t.id === activeTabId ? { ...t, nodes, edges, pipelineId: id, isDirty, name, past, future } : t
    )

    // Load target tab
    const target = updatedTabs.find((t) => t.id === tabId)
    if (!target) return

    set({
      tabs: updatedTabs,
      activeTabId: tabId,
      id: target.pipelineId,
      name: target.name,
      nodes: target.nodes,
      edges: target.edges,
      isDirty: target.isDirty,
      selectedNodeId: null,
      past: target.past || [],
      future: target.future || [],
    })
  },

  renameTab: (tabId: string, newName: string) => {
    const { tabs, activeTabId } = get()
    set({
      tabs: tabs.map((t) => (t.id === tabId ? { ...t, name: newName } : t)),
      ...(tabId === activeTabId ? { name: newName } : {}),
    })
  },

  duplicateTab: (tabId: string) => {
    const { tabs, nodes, edges, id, name, isDirty, activeTabId, past, future } = get()
    // Save current state into tabs first (including undo/redo history)
    const savedTabs = tabs.map((t) =>
      t.id === activeTabId ? { ...t, nodes, edges, pipelineId: id, isDirty, name, past, future } : t
    )
    const sourceTab = savedTabs.find((t) => t.id === tabId)
    if (!sourceTab) return

    const newTabId = _makeTabId()
    const dupTab: PipelineTab = {
      id: newTabId,
      name: `${sourceTab.name} (Copy)`,
      nodes: JSON.parse(JSON.stringify(sourceTab.nodes)),
      edges: JSON.parse(JSON.stringify(sourceTab.edges)),
      pipelineId: null, // new tab = unsaved
      isDirty: true,
      runStatus: 'idle',
      past: [],
      future: [],
    }

    set({
      tabs: [...savedTabs, dupTab],
      activeTabId: newTabId,
      id: null,
      name: dupTab.name,
      nodes: dupTab.nodes,
      edges: dupTab.edges,
      isDirty: true,
      selectedNodeId: null,
      past: [],
      future: [],
    })
    toast.success('Tab duplicated')
  },

  updateTabRunStatus: (tabId: string, status: PipelineTab['runStatus']) => {
    set((s) => ({
      tabs: s.tabs.map((t) => (t.id === tabId ? { ...t, runStatus: status } : t)),
    }))
  },
}))
