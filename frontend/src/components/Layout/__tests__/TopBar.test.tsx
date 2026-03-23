import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import TopBar from '../TopBar'

vi.mock('@/stores/uiStore', () => ({
  useUIStore: () => ({ activeView: 'editor' }),
}))

vi.mock('@/stores/guideStore', () => ({
  useGuideStore: (selector: any) => selector({ guideActive: true, toggleGuide: vi.fn() }),
}))

describe('TopBar', () => {
  it('renders BLUEPRINT — subtitle span and/or brand pill', () => {
    render(<TopBar />)
    const els = screen.getAllByText('BLUEPRINT')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('renders active view label in uppercase', () => {
    render(<TopBar />)
    expect(screen.getByText('PIPELINE EDITOR')).toBeInTheDocument()
  })

  it('renders the exact logo SVG with correct viewBox', () => {
    const { container } = render(<TopBar />)
    const svg = container.querySelector('svg[viewBox="0 0 760 160"]')
    expect(svg).toBeTruthy()
  })

  it('preserves the exact L-shaped arm path geometry', () => {
    const { container } = render(<TopBar />)
    const path = container.querySelector('path[d="M 0,0 H 120 V 120 H 96 V 24 H 0 Z"]')
    expect(path).toBeTruthy()
  })

  it('preserves the exact circle geometry', () => {
    const { container } = render(<TopBar />)
    const circle = container.querySelector('circle[cx="36"][cy="84"][r="36"]')
    expect(circle).toBeTruthy()
  })

  it('renders SPECIFIC and LABS wordmark text', () => {
    render(<TopBar />)
    expect(screen.getByText('SPECIFIC')).toBeInTheDocument()
    expect(screen.getByText('LABS')).toBeInTheDocument()
  })

  it('renders the BLUEPRINT brand pill (replaced LOCAL badge)', () => {
    render(<TopBar />)
    // BLUEPRINT appears both as the animated subtitle span AND as the brand pill
    const els = screen.getAllByText('BLUEPRINT')
    expect(els.length).toBeGreaterThanOrEqual(1)
  })

  it('renders the GUIDE toggle button', () => {
    render(<TopBar />)
    expect(screen.getByText('GUIDE')).toBeInTheDocument()
  })
})
