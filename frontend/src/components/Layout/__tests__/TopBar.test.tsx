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
  it('renders active view breadcrumb label', () => {
    render(<TopBar />)
    expect(screen.getByText('Build')).toBeInTheDocument()
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

  it('renders SPECIFIC and LABS text in the logotype', () => {
    render(<TopBar />)
    expect(screen.getByText('SPECIFIC')).toBeInTheDocument()
    expect(screen.getByText('LABS')).toBeInTheDocument()
  })

  it('does NOT render a "Blueprint" label next to the logo (removed from framing)', () => {
    render(<TopBar />)
    // "Blueprint" as a standalone text node should be absent — logotype is in SVG now
    const blueprintEl = screen.queryByText((content) => content.trim() === 'Blueprint')
    expect(blueprintEl).toBeNull()
  })

  it('renders the Guide toggle button', () => {
    render(<TopBar />)
    expect(screen.getByText('Guide')).toBeInTheDocument()
  })
})
