import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { createRef } from 'react'
import BlockSuggestions from '../BlockSuggestions'

// Mock pipelineStore
const mockStoreState = {
  selectedNodeId: null as string | null,
  nodes: [] as any[],
  edges: [] as any[],
  addNodeAndConnect: vi.fn(),
}

vi.mock('@/stores/pipelineStore', () => ({
  usePipelineStore: Object.assign(
    (selector: any) => selector(mockStoreState),
    { getState: () => mockStoreState }
  ),
}))

vi.mock('zustand/react/shallow', () => ({
  useShallow: (fn: any) => fn,
}))

vi.mock('@/lib/block-registry', () => ({
  getAllBlocks: () => [
    {
      type: 'filter_sample',
      name: 'Filter & Sample',
      description: 'Filter and sample data',
      category: 'data',
      icon: 'Filter',
      accent: '#62B8D9',
      tags: [],
      aliases: [],
      inputs: [{ id: 'dataset', label: 'Dataset', dataType: 'dataset', required: true }],
      outputs: [{ id: 'dataset', label: 'Filtered Dataset', dataType: 'dataset', required: true }],
      configFields: [],
      defaultConfig: {},
      version: '1.0.0',
      maturity: 'stable',
    },
    {
      type: 'text_chunker',
      name: 'Text Chunker',
      description: 'Split text into chunks',
      category: 'data',
      icon: 'Scissors',
      accent: '#62B8D9',
      tags: [],
      aliases: [],
      inputs: [{ id: 'text', label: 'Text', dataType: 'text', required: true }],
      outputs: [{ id: 'chunks', label: 'Chunks', dataType: 'dataset', required: true }],
      configFields: [],
      defaultConfig: {},
      version: '1.0.0',
      maturity: 'stable',
    },
  ],
  getBlockDefinition: (type: string) => {
    const blocks: Record<string, any> = {
      huggingface_loader: {
        type: 'huggingface_loader',
        name: 'HuggingFace Loader',
        description: 'Load data',
        category: 'external',
        icon: 'Database',
        accent: '#DE9A68',
        inputs: [],
        outputs: [{ id: 'dataset', label: 'Dataset', dataType: 'dataset', required: true }],
        configFields: [],
        defaultConfig: {},
        version: '1.0.0',
      },
    }
    return blocks[type]
  },
  isPortCompatible: (src: string, tgt: string) => {
    if (src === tgt) return true
    if (src === 'any' || tgt === 'any') return true
    if (src === 'dataset' && tgt === 'text') return true
    return false
  },
}))

vi.mock('@/lib/block-registry-types', () => ({
  computeBlockWidth: () => 280,
}))

vi.mock('@/lib/icon-utils', () => ({
  getIcon: () => {
    const MockIcon = (props: any) => <span data-testid="suggestion-icon" {...props} />
    return MockIcon
  },
}))

vi.mock('@/lib/design-tokens', () => ({
  T: {
    bg: '#060709', surface0: '#0B0D13', surface1: '#0F1319', surface2: '#141922',
    surface3: '#1B2130', surface4: '#222A3C', border: '#252E3C', borderHi: '#374659',
    text: '#F2F4F8', sec: '#C4CDDE', dim: '#7A8799', cyan: '#2FFCC8',
    shadow: 'rgba(0,0,0,0.60)',
  },
  F: "'IBM Plex Sans',sans-serif",
  FS: { xxs: 10, xs: 11, sm: 12 },
  CATEGORY_COLORS: { data: '#62B8D9', external: '#DE9A68' },
}))

vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}))

// Shared mock props
const mockFlowToScreenPosition = vi.fn((pos: { x: number; y: number }) => pos)
const mockContainerRef = createRef<HTMLDivElement>()

describe('BlockSuggestions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockStoreState.selectedNodeId = null
    mockStoreState.nodes = []
    mockStoreState.edges = []
  })

  const renderSuggestions = () =>
    render(
      <BlockSuggestions
        flowToScreenPosition={mockFlowToScreenPosition}
        containerRef={mockContainerRef}
      />
    )

  it('renders nothing when no node is selected', () => {
    const { container } = renderSuggestions()
    expect(container.innerHTML).toBe('')
  })

  it('renders suggestions when a node with unconnected output ports is selected', () => {
    mockStoreState.selectedNodeId = 'node-1'
    mockStoreState.nodes = [
      {
        id: 'node-1',
        type: 'blockNode',
        position: { x: 100, y: 100 },
        data: { type: 'huggingface_loader', label: 'HF Loader', category: 'external' },
      },
    ]
    mockStoreState.edges = []

    renderSuggestions()

    // Should show "Connect next" header
    expect(screen.getByText('Connect next')).toBeInTheDocument()

    // Filter & Sample has dataset input matching our dataset output
    expect(screen.getByText('Filter & Sample')).toBeInTheDocument()
  })

  it('does not suggest blocks when all output ports are connected', () => {
    mockStoreState.selectedNodeId = 'node-1'
    mockStoreState.nodes = [
      {
        id: 'node-1',
        type: 'blockNode',
        position: { x: 100, y: 100 },
        data: { type: 'huggingface_loader', label: 'HF Loader', category: 'external' },
      },
      {
        id: 'node-2',
        type: 'blockNode',
        position: { x: 100, y: 300 },
        data: { type: 'filter_sample', label: 'Filter', category: 'data' },
      },
    ]
    mockStoreState.edges = [
      { id: 'e1', source: 'node-1', target: 'node-2', sourceHandle: 'dataset', targetHandle: 'dataset' },
    ]

    renderSuggestions()

    // All outputs are connected, so no suggestions
    expect(screen.queryByText('Connect next')).not.toBeInTheDocument()
  })
})
