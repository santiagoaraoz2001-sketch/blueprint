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
  it('renders app brand and active view label', () => {
    render(<TopBar />)
    expect(screen.getByText('BLUEPRINT')).toBeInTheDocument()
    expect(screen.getByText('Build')).toBeInTheDocument()
  })
})
