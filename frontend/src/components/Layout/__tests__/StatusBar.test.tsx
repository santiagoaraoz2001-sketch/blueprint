import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatusBar from '../StatusBar'

vi.mock('@/components/Layout/NotificationBell', () => ({
  default: () => <div data-testid="bell" />,
}))

vi.mock('@/stores/runStore', () => ({
  useRunStore: () => ({
    status: 'running',
    overallProgress: 0.45,
    elapsed: 90,
    eta: 30,
  }),
}))

vi.mock('@/stores/settingsStore', () => {
  const state = {
    theme: 'dark',
    accentColor: 'cyan',
    fontSize: 'medium',
    demoMode: false,
    hardware: { gpu_available: true, gpu_backend: 'mps', usable_memory_gb: 32, max_vram_gb: 24, max_model_size: '14b' },
    hardwareLoading: false,
    fetchHardware: vi.fn(),
  }
  const useSettingsStore = () => state
  ;(useSettingsStore as any).getState = () => state
  return {
    useSettingsStore,
    FONT_SIZE_SCALES: { small: 0.9, medium: 1, large: 1.1 },
  }
})

describe('StatusBar', () => {
  it('shows running status and progress details', () => {
    render(<StatusBar />)
    expect(screen.getByText('Running')).toBeInTheDocument()
    expect(screen.getByText('45%')).toBeInTheDocument()
    expect(screen.getByTestId('bell')).toBeInTheDocument()
  })
})
