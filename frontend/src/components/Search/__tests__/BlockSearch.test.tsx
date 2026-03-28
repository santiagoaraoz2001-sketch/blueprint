import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import BlockSearch from '../BlockSearch'

// Mock the registry to return predictable blocks
vi.mock('@/lib/block-registry', () => ({
  getAllBlocks: () => [
    {
      type: 'lora_finetuning',
      name: 'LoRA Fine-tuning',
      description: 'Fine-tune a model using LoRA adapters',
      category: 'training',
      icon: 'Cpu',
      accent: '#B29CEA',
      tags: ['lora', 'fine-tuning', 'peft'],
      aliases: ['lora', 'adapter training'],
      inputs: [
        { id: 'model', label: 'Model', dataType: 'model', required: true },
        { id: 'dataset', label: 'Dataset', dataType: 'dataset', required: true },
      ],
      outputs: [{ id: 'model', label: 'Trained Model', dataType: 'model', required: true }],
      configFields: [],
      defaultConfig: {},
      version: '1.0.0',
      maturity: 'stable',
    },
    {
      type: 'qlora_finetuning',
      name: 'QLoRA Fine-tuning',
      description: 'Quantized LoRA fine-tuning for memory efficiency',
      category: 'training',
      icon: 'Cpu',
      accent: '#B29CEA',
      tags: ['qlora', 'quantized', 'fine-tuning'],
      aliases: [],
      inputs: [
        { id: 'model', label: 'Model', dataType: 'model', required: true },
        { id: 'dataset', label: 'Dataset', dataType: 'dataset', required: true },
      ],
      outputs: [{ id: 'model', label: 'Trained Model', dataType: 'model', required: true }],
      configFields: [],
      defaultConfig: {},
      version: '1.0.0',
      maturity: 'stable',
    },
    {
      type: 'huggingface_loader',
      name: 'HuggingFace Dataset Loader',
      description: 'Load a dataset from HuggingFace Hub',
      category: 'external',
      icon: 'Database',
      accent: '#DE9A68',
      tags: ['huggingface', 'dataset', 'loader'],
      aliases: ['hf dataset'],
      inputs: [],
      outputs: [{ id: 'dataset', label: 'Dataset', dataType: 'dataset', required: true }],
      configFields: [],
      defaultConfig: {},
      version: '1.0.0',
      maturity: 'stable',
    },
    {
      type: 'llm_inference',
      name: 'LLM Inference',
      description: 'Run inference with a language model',
      category: 'inference',
      icon: 'MessageSquare',
      accent: '#E8A84A',
      tags: ['llm', 'inference', 'chat'],
      aliases: [],
      inputs: [{ id: 'prompt', label: 'Prompt', dataType: 'text', required: true }],
      outputs: [{ id: 'response', label: 'Response', dataType: 'text', required: true }],
      configFields: [],
      defaultConfig: {},
      version: '1.0.0',
      maturity: 'stable',
    },
  ],
  getPortColor: () => '#5FB8E8',
  isPortCompatible: () => true,
}))

vi.mock('@/lib/search-aliases', () => ({
  BLOCK_ALIASES: {},
  CATEGORY_ALIASES: {},
}))

vi.mock('@/lib/icon-utils', () => ({
  getIcon: () => {
    const MockIcon = (props: any) => <span data-testid="mock-icon" {...props} />
    return MockIcon
  },
}))

vi.mock('@/lib/design-tokens', () => ({
  T: {
    bg: '#060709', bgAlt: '#090C11', surface: 'rgba(16,20,28,0.94)',
    raised: '#12161F', border: '#252E3C', borderHi: '#374659',
    text: '#F2F4F8', sec: '#C4CDDE', dim: '#7A8799', muted: '#1A1F2C',
    surface0: '#0B0D13', surface1: '#0F1319', surface2: '#141922',
    surface3: '#1B2130', surface4: '#222A3C', surface5: '#2C3649',
    surface6: '#384557', cyan: '#2FFCC8', green: '#3EF07A',
    amber: '#FFBE45', red: '#FF5E72', blue: '#5B96FF', purple: '#A87EFF',
    shadow: 'rgba(0,0,0,0.60)', shadowHeavy: 'rgba(0,0,0,0.76)',
    shadowLight: 'rgba(18,24,40,0.28)',
  },
  F: "'IBM Plex Sans',sans-serif",
  FS: { xxs: 10, xs: 11, sm: 12, md: 13, lg: 15, xl: 17, xxl: 20, h3: 23, h2: 28 },
  CATEGORY_COLORS: {
    external: '#DE9A68', data: '#62B8D9', model: '#9880E8', training: '#7B9BE3',
    metrics: '#65D68B', inference: '#8FD07A',
  },
  DEPTH: {
    modal: '0 32px 80px rgba(0,0,0,0.72)',
  },
}))

vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}))

// Mock localStorage for test environment
const localStorageData: Record<string, string> = {}
const localStorageMock = {
  getItem: vi.fn((key: string) => localStorageData[key] ?? null),
  setItem: vi.fn((key: string, value: string) => { localStorageData[key] = value }),
  removeItem: vi.fn((key: string) => { delete localStorageData[key] }),
  clear: vi.fn(() => { Object.keys(localStorageData).forEach((k) => delete localStorageData[k]) }),
  key: vi.fn(),
  length: 0,
}
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

const mockAddBlock = vi.fn()
const mockShowBlockDoc = vi.fn()
const mockGetViewportCenter = vi.fn(() => ({ x: 400, y: 300 }))

describe('BlockSearch', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.keys(localStorageData).forEach((k) => delete localStorageData[k])
  })

  const renderSearch = () =>
    render(
      <BlockSearch
        onAddBlock={mockAddBlock}
        onShowBlockDoc={mockShowBlockDoc}
        getViewportCenter={mockGetViewportCenter}
      />
    )

  it('opens on Cmd+K and closes on Escape', () => {
    renderSearch()

    // Should not be visible initially
    expect(screen.queryByPlaceholderText('Search blocks by name, type, or capability...')).not.toBeInTheDocument()

    // Open with Cmd+K
    act(() => {
      fireEvent.keyDown(window, { key: 'k', metaKey: true })
    })

    expect(screen.getByPlaceholderText('Search blocks by name, type, or capability...')).toBeInTheDocument()

    // Close with Escape
    const input = screen.getByPlaceholderText('Search blocks by name, type, or capability...')
    fireEvent.keyDown(input, { key: 'Escape' })

    expect(screen.queryByPlaceholderText('Search blocks by name, type, or capability...')).not.toBeInTheDocument()
  })

  it('filters blocks by name — searching "lora" returns lora blocks', () => {
    renderSearch()

    // Open search
    act(() => {
      fireEvent.keyDown(window, { key: 'k', metaKey: true })
    })

    const input = screen.getByPlaceholderText('Search blocks by name, type, or capability...')
    fireEvent.change(input, { target: { value: 'lora' } })

    // Should show both lora blocks
    expect(screen.getByText('LoRA Fine-tuning')).toBeInTheDocument()
    expect(screen.getByText('QLoRA Fine-tuning')).toBeInTheDocument()
    // Should NOT show unrelated blocks
    expect(screen.queryByText('HuggingFace Dataset Loader')).not.toBeInTheDocument()
    expect(screen.queryByText('LLM Inference')).not.toBeInTheDocument()
  })

  it('filters blocks by description text', () => {
    renderSearch()

    act(() => {
      fireEvent.keyDown(window, { key: 'k', metaKey: true })
    })

    const input = screen.getByPlaceholderText('Search blocks by name, type, or capability...')
    fireEvent.change(input, { target: { value: 'language model' } })

    expect(screen.getByText('LLM Inference')).toBeInTheDocument()
  })

  it('filters blocks by port data_type — searching "dataset" finds blocks with dataset ports', () => {
    renderSearch()

    act(() => {
      fireEvent.keyDown(window, { key: 'k', metaKey: true })
    })

    const input = screen.getByPlaceholderText('Search blocks by name, type, or capability...')
    fireEvent.change(input, { target: { value: 'dataset' } })

    // HuggingFace loader has dataset output, LoRA has dataset input
    expect(screen.getByText('HuggingFace Dataset Loader')).toBeInTheDocument()
    expect(screen.getByText('LoRA Fine-tuning')).toBeInTheDocument()
  })

  it('shows category badge for each result', () => {
    renderSearch()

    act(() => {
      fireEvent.keyDown(window, { key: 'k', metaKey: true })
    })

    const input = screen.getByPlaceholderText('Search blocks by name, type, or capability...')
    fireEvent.change(input, { target: { value: 'lora' } })

    // Category badges should be visible
    expect(screen.getAllByText('training').length).toBeGreaterThanOrEqual(1)
  })

  it('shows port summary for each result', () => {
    renderSearch()

    act(() => {
      fireEvent.keyDown(window, { key: 'k', metaKey: true })
    })

    const input = screen.getByPlaceholderText('Search blocks by name, type, or capability...')
    fireEvent.change(input, { target: { value: 'lora' } })

    // Port summary for LoRA: 2 inputs, 1 output
    expect(screen.getAllByText('2 in, 1 out').length).toBeGreaterThanOrEqual(1)
  })

  it('adds block to canvas on Enter', () => {
    renderSearch()

    act(() => {
      fireEvent.keyDown(window, { key: 'k', metaKey: true })
    })

    const input = screen.getByPlaceholderText('Search blocks by name, type, or capability...')
    fireEvent.change(input, { target: { value: 'lora' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(mockAddBlock).toHaveBeenCalledWith('lora_finetuning', { x: 400, y: 300 })
  })

  it('calls onShowBlockDoc on Shift+Enter', () => {
    renderSearch()

    act(() => {
      fireEvent.keyDown(window, { key: 'k', metaKey: true })
    })

    const input = screen.getByPlaceholderText('Search blocks by name, type, or capability...')
    fireEvent.change(input, { target: { value: 'lora' } })
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true })

    expect(mockShowBlockDoc).toHaveBeenCalledWith('lora_finetuning')
    expect(mockAddBlock).not.toHaveBeenCalled()
  })

  it('navigates results with arrow keys', () => {
    renderSearch()

    act(() => {
      fireEvent.keyDown(window, { key: 'k', metaKey: true })
    })

    const input = screen.getByPlaceholderText('Search blocks by name, type, or capability...')
    fireEvent.change(input, { target: { value: 'lora' } })

    // Move to second result and select
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    fireEvent.keyDown(input, { key: 'Enter' })

    // Second result should be QLoRA (alphabetically after LoRA by score)
    expect(mockAddBlock).toHaveBeenCalledWith('qlora_finetuning', { x: 400, y: 300 })
  })

  it('tracks recently used blocks in localStorage', () => {
    renderSearch()

    act(() => {
      fireEvent.keyDown(window, { key: 'k', metaKey: true })
    })

    const input = screen.getByPlaceholderText('Search blocks by name, type, or capability...')
    fireEvent.change(input, { target: { value: 'lora' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    // Verify localStorage was updated
    const recent = JSON.parse(localStorage.getItem('blueprint-recently-used-blocks') || '[]')
    expect(recent).toContain('lora_finetuning')
  })
})
