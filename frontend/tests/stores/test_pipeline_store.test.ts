/**
 * Pipeline Store unit tests — covers add/remove node, add/remove edge,
 * undo/redo, and save/load state.
 *
 * Uses Vitest with jsdom environment. The store is tested as a pure
 * Zustand store by directly calling actions and asserting state changes.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'

// Mock the api client before importing the store
vi.mock('@/api/client', () => ({
  api: {
    get: vi.fn().mockResolvedValue(null),
    post: vi.fn().mockResolvedValue({ id: 'test-pipeline-id', name: 'Test' }),
    put: vi.fn().mockResolvedValue({ id: 'test-pipeline-id', name: 'Test' }),
    delete: vi.fn().mockResolvedValue(null),
  },
}))

// Mock react-hot-toast
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

// Mock audio
vi.mock('@/lib/audio', () => ({
  playSound: vi.fn(),
}))

// Mock demo data
vi.mock('@/lib/demo-data', () => ({
  DEMO_PIPELINE: { id: 'demo', name: 'Demo', nodes: [], edges: [] },
  DEMO_PIPELINES_LIST: [],
}))

// Mock layout utils
vi.mock('@/lib/layout-utils', () => ({
  getLayoutedElements: vi.fn((nodes: unknown[], edges: unknown[]) => ({ nodes, edges })),
}))

// Mock block-registry
vi.mock('@/lib/block-registry', () => ({
  getBlockDefinition: vi.fn(() => ({
    type: 'data_loader',
    name: 'Data Loader',
    category: 'data',
    icon: 'database',
    accent: '#5FB8E8',
    inputs: [{ id: 'input', label: 'Input', dataType: 'any', required: false }],
    outputs: [{ id: 'output', label: 'Output', dataType: 'dataset', required: false }],
    defaultConfig: {},
    configFields: [],
  })),
  getPortColor: vi.fn(() => '#5FB8E8'),
  isPortCompatible: vi.fn(() => true),
  resolvePort: vi.fn(),
  findBestInputPort: vi.fn(),
}))

// Mock auto-wiring
vi.mock('@/lib/auto-wiring', () => ({
  suggestConnections: vi.fn(() => []),
  findNearbyNodes: vi.fn(() => []),
}))

// Mock settingsStore
vi.mock('@/stores/settingsStore', () => ({
  useSettingsStore: {
    getState: () => ({ demoMode: false }),
    subscribe: vi.fn(),
  },
}))

// Mock uiStore
vi.mock('@/stores/uiStore', () => ({
  useUIStore: {
    getState: () => ({ sidebarCollapsed: false }),
    subscribe: vi.fn(),
  },
}))

// Mock history utils
vi.mock('@/lib/history', () => ({
  inferOperationType: vi.fn(() => 'edit'),
  serializeHistory: vi.fn(() => '[]'),
  serializeHistoryMeta: vi.fn(() => '{}'),
  deserializeHistory: vi.fn(() => ({ past: [], future: [] })),
}))

import { usePipelineStore } from '@/stores/pipelineStore'

describe('PipelineStore', () => {
  beforeEach(() => {
    // Reset store to initial state
    const store = usePipelineStore.getState()
    store.reset?.()
    usePipelineStore.setState({
      id: null,
      name: 'Untitled Pipeline',
      nodes: [],
      edges: [],
      selectedNodeId: null,
      isDirty: false,
      past: [],
      future: [],
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('Node operations', () => {
    it('adds a node to the canvas', () => {
      const store = usePipelineStore.getState()
      store.addNode('data_loader', { x: 100, y: 200 })

      const { nodes } = usePipelineStore.getState()
      expect(nodes.length).toBe(1)
      expect(nodes[0].data.type).toBe('data_loader')
      expect(nodes[0].position).toEqual({ x: 100, y: 200 })
    })

    it('removes a node from the canvas', () => {
      const store = usePipelineStore.getState()
      store.addNode('data_loader', { x: 0, y: 0 })

      const { nodes: nodesAfterAdd } = usePipelineStore.getState()
      expect(nodesAfterAdd.length).toBe(1)
      const nodeId = nodesAfterAdd[0].id

      store.removeNode(nodeId)
      const { nodes: nodesAfterRemove } = usePipelineStore.getState()
      expect(nodesAfterRemove.length).toBe(0)
    })

    it('selects a node', () => {
      const store = usePipelineStore.getState()
      store.addNode('data_loader', { x: 0, y: 0 })
      const { nodes } = usePipelineStore.getState()
      const nodeId = nodes[0].id

      store.selectNode(nodeId)
      expect(usePipelineStore.getState().selectedNodeId).toBe(nodeId)

      store.selectNode(null)
      expect(usePipelineStore.getState().selectedNodeId).toBeNull()
    })

    it('updates node config', () => {
      const store = usePipelineStore.getState()
      store.addNode('data_loader', { x: 0, y: 0 })
      const { nodes } = usePipelineStore.getState()
      const nodeId = nodes[0].id

      store.updateNodeConfig(nodeId, { source: 'test.csv', batch_size: 32 })
      const updatedNode = usePipelineStore.getState().nodes.find((n) => n.id === nodeId)
      expect(updatedNode?.data.config).toEqual(
        expect.objectContaining({ source: 'test.csv', batch_size: 32 })
      )
    })
  })

  describe('Edge operations', () => {
    it('adds an edge via onConnect', () => {
      const store = usePipelineStore.getState()
      store.addNode('data_loader', { x: 0, y: 0 })
      store.addNode('data_loader', { x: 200, y: 0 })

      const { nodes } = usePipelineStore.getState()
      const srcId = nodes[0].id
      const tgtId = nodes[1].id

      store.onConnect({
        source: srcId,
        target: tgtId,
        sourceHandle: 'output',
        targetHandle: 'input',
      })

      const { edges } = usePipelineStore.getState()
      expect(edges.length).toBe(1)
      expect(edges[0].source).toBe(srcId)
      expect(edges[0].target).toBe(tgtId)
    })

    it('removes edges when a node is removed', () => {
      const store = usePipelineStore.getState()
      store.addNode('data_loader', { x: 0, y: 0 })
      store.addNode('data_loader', { x: 200, y: 0 })
      const { nodes: added } = usePipelineStore.getState()

      store.onConnect({
        source: added[0].id,
        target: added[1].id,
        sourceHandle: 'output',
        targetHandle: 'input',
      })

      expect(usePipelineStore.getState().edges.length).toBe(1)

      store.removeNode(added[0].id)
      const { edges, nodes } = usePipelineStore.getState()
      expect(nodes.length).toBe(1)
      expect(edges.length).toBe(0)
    })
  })

  describe('Undo/Redo', () => {
    it('undoes the last operation', () => {
      const store = usePipelineStore.getState()
      store.addNode('data_loader', { x: 0, y: 0 })
      expect(usePipelineStore.getState().nodes.length).toBe(1)

      store.undo()
      expect(usePipelineStore.getState().nodes.length).toBe(0)
    })

    it('redoes an undone operation', () => {
      const store = usePipelineStore.getState()
      store.addNode('data_loader', { x: 0, y: 0 })
      expect(usePipelineStore.getState().nodes.length).toBe(1)

      store.undo()
      expect(usePipelineStore.getState().nodes.length).toBe(0)

      store.redo()
      expect(usePipelineStore.getState().nodes.length).toBe(1)
    })

    it('clears future on new action after undo', () => {
      const store = usePipelineStore.getState()
      store.addNode('data_loader', { x: 0, y: 0 })
      store.addNode('data_loader', { x: 200, y: 0 })
      expect(usePipelineStore.getState().nodes.length).toBe(2)

      store.undo()
      expect(usePipelineStore.getState().nodes.length).toBe(1)
      expect(usePipelineStore.getState().future.length).toBeGreaterThan(0)

      // New action should clear future
      store.addNode('data_loader', { x: 400, y: 0 })
      expect(usePipelineStore.getState().nodes.length).toBe(2)
      expect(usePipelineStore.getState().future.length).toBe(0)
    })
  })

  describe('Pipeline name', () => {
    it('sets the pipeline name', () => {
      const store = usePipelineStore.getState()
      store.setName('My Custom Pipeline')
      expect(usePipelineStore.getState().name).toBe('My Custom Pipeline')
    })
  })
})
