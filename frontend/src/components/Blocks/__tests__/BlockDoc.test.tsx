import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import BlockDoc from '../BlockDoc'

vi.mock('@/lib/block-registry', () => ({
  getBlockDefinition: (type: string) => {
    if (type === 'lora_finetuning') {
      return {
        type: 'lora_finetuning',
        name: 'LoRA Fine-tuning',
        description: 'Fine-tune a model using Low-Rank Adaptation (LoRA) for efficient parameter updates.',
        category: 'training',
        version: '1.2.0',
        icon: 'Cpu',
        accent: '#B29CEA',
        tags: ['lora', 'fine-tuning'],
        aliases: [],
        maturity: 'stable',
        inputs: [
          { id: 'model', label: 'Base Model', dataType: 'model', required: true },
          { id: 'dataset', label: 'Training Dataset', dataType: 'dataset', required: true },
          { id: 'config', label: 'Config', dataType: 'config', required: false },
        ],
        outputs: [
          { id: 'model', label: 'Trained Model', dataType: 'model', required: true },
          { id: 'metrics', label: 'Training Metrics', dataType: 'metrics', required: true },
        ],
        configFields: [
          { name: 'rank', label: 'LoRA Rank', type: 'integer', default: 16, description: 'Rank of the LoRA matrices' },
          { name: 'alpha', label: 'LoRA Alpha', type: 'float', default: 32.0, description: 'Scaling factor' },
          { name: 'epochs', label: 'Epochs', type: 'integer', default: 3, mandatory: true },
        ],
        defaultConfig: { rank: 16, alpha: 32.0, epochs: 3 },
        detail: {
          useCases: ['Adapt a base LLM to a specific domain', 'Fine-tune for instruction following'],
          howItWorks: 'LoRA freezes the pretrained weights and injects trainable low-rank decomposition matrices.',
        },
      }
    }
    return undefined
  },
  getPortColor: (type: string) => {
    const colors: Record<string, string> = {
      model: '#B29CEA',
      dataset: '#5FB8E8',
      config: '#DE7B4F',
      metrics: '#52D975',
    }
    return colors[type] || '#5FB8E8'
  },
}))

vi.mock('@/lib/design-tokens', () => ({
  T: {
    bg: '#060709', surface0: '#0B0D13', surface1: '#0F1319', surface2: '#141922',
    surface3: '#1B2130', surface4: '#222A3C', border: '#252E3C', borderHi: '#374659',
    text: '#F2F4F8', sec: '#C4CDDE', dim: '#7A8799', cyan: '#2FFCC8',
    red: '#FF5E72', shadow: 'rgba(0,0,0,0.60)', shadowHeavy: 'rgba(0,0,0,0.76)',
  },
  F: "'IBM Plex Sans',sans-serif",
  FS: { xxs: 10, xs: 11, sm: 12, md: 13, lg: 15 },
  CATEGORY_COLORS: { training: '#7B9BE3' },
}))

vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ref, ...props }: any) => <div ref={ref} {...props}>{children}</div>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}))

describe('BlockDoc', () => {
  it('renders nothing when blockType is null', () => {
    const { container } = render(
      <BlockDoc blockType={null} visible={true} />
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing when visible is false', () => {
    const { container } = render(
      <BlockDoc blockType="lora_finetuning" visible={false} />
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders block name and category badge', () => {
    render(
      <BlockDoc
        blockType="lora_finetuning"
        visible={true}
        anchor={{ x: 200, y: 200 }}
      />
    )

    expect(screen.getByText('LoRA Fine-tuning')).toBeInTheDocument()
    expect(screen.getByText('training')).toBeInTheDocument()
  })

  it('renders input port information correctly', () => {
    render(
      <BlockDoc
        blockType="lora_finetuning"
        visible={true}
        anchor={{ x: 200, y: 200 }}
      />
    )

    // Port names
    expect(screen.getByText('Base Model')).toBeInTheDocument()
    expect(screen.getByText('Training Dataset')).toBeInTheDocument()
    expect(screen.getByText('Config')).toBeInTheDocument()

    // Port types
    expect(screen.getAllByText('model').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('dataset').length).toBeGreaterThanOrEqual(1)
  })

  it('renders output port information', () => {
    render(
      <BlockDoc
        blockType="lora_finetuning"
        visible={true}
        anchor={{ x: 200, y: 200 }}
      />
    )

    expect(screen.getByText('Trained Model')).toBeInTheDocument()
    expect(screen.getByText('Training Metrics')).toBeInTheDocument()
  })

  it('renders configuration fields with defaults', () => {
    render(
      <BlockDoc
        blockType="lora_finetuning"
        visible={true}
        anchor={{ x: 200, y: 200 }}
      />
    )

    expect(screen.getByText('LoRA Rank')).toBeInTheDocument()
    expect(screen.getByText('LoRA Alpha')).toBeInTheDocument()
    expect(screen.getByText('Epochs')).toBeInTheDocument()

    // Default values
    expect(screen.getByText('16')).toBeInTheDocument()
    expect(screen.getByText('32')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('renders example usage when present', () => {
    render(
      <BlockDoc
        blockType="lora_finetuning"
        visible={true}
        anchor={{ x: 200, y: 200 }}
      />
    )

    expect(screen.getByText('Example Usage')).toBeInTheDocument()
    expect(screen.getByText('Adapt a base LLM to a specific domain')).toBeInTheDocument()
  })

  it('renders type and version in footer', () => {
    render(
      <BlockDoc
        blockType="lora_finetuning"
        visible={true}
        anchor={{ x: 200, y: 200 }}
      />
    )

    // Footer shows type and version
    const footer = screen.getByText(/type: lora_finetuning/i)
    expect(footer).toBeInTheDocument()
  })

  it('shows required indicators for mandatory config fields', () => {
    render(
      <BlockDoc
        blockType="lora_finetuning"
        visible={true}
        anchor={{ x: 200, y: 200 }}
      />
    )

    // Required port indicators (asterisks)
    const asterisks = document.querySelectorAll('span')
    const requiredMarkers = Array.from(asterisks).filter(
      (el) => el.textContent === '*'
    )
    // At least 3 required indicators: 2 required inputs + 1 mandatory config
    expect(requiredMarkers.length).toBeGreaterThanOrEqual(3)
  })
})
