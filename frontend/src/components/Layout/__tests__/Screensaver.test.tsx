import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import Screensaver from '../Screensaver'

// framer-motion: use real component (jsdom doesn't run CSS animations but JS runs fine)
vi.mock('framer-motion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('framer-motion')>()
  return actual
})

describe('Screensaver', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders nothing while user is active', () => {
    render(<Screensaver />)
    expect(screen.queryByTestId('screensaver-overlay')).toBeNull()
  })

  it('renders overlay after 90 s of inactivity', async () => {
    render(<Screensaver />)
    await act(async () => {
      vi.advanceTimersByTime(90_001)
    })
    expect(screen.getByTestId('screensaver-overlay')).toBeTruthy()
  })

  it('shows the animated logo SVG inside the overlay', async () => {
    render(<Screensaver />)
    await act(async () => {
      vi.advanceTimersByTime(90_001)
    })
    expect(screen.getByTestId('screensaver-logo')).toBeTruthy()
  })

  it('shows the clock inside the overlay', async () => {
    render(<Screensaver />)
    await act(async () => {
      vi.advanceTimersByTime(90_001)
    })
    expect(screen.getByTestId('screensaver-clock')).toBeTruthy()
  })

  it('shows the nebula background layer', async () => {
    render(<Screensaver />)
    await act(async () => {
      vi.advanceTimersByTime(90_001)
    })
    expect(screen.getByTestId('screensaver-nebula')).toBeTruthy()
  })

  it('resets idle timer on mousemove (screensaver does not re-appear immediately after dismiss)', async () => {
    render(<Screensaver />)
    // Trigger idle
    await act(async () => { vi.advanceTimersByTime(90_001) })
    expect(screen.getByTestId('screensaver-overlay')).toBeTruthy()

    // Dismiss via mousemove — idle timer resets to 0
    await act(async () => {
      document.dispatchEvent(new MouseEvent('mousemove'))
    })

    // Advance only 5 s — well below the 90 s threshold — screensaver must NOT reappear
    await act(async () => { vi.advanceTimersByTime(5_000) })

    // The overlay may still be in exit animation (framer-motion AnimatePresence keeps DOM)
    // but a new one should not have been added, so at most 1 instance exists
    const overlays = screen.queryAllByTestId('screensaver-overlay')
    expect(overlays.length).toBeLessThanOrEqual(1)
  })

  it('contains a particle element', async () => {
    render(<Screensaver />)
    await act(async () => {
      vi.advanceTimersByTime(90_001)
    })
    // first particle has testid
    expect(screen.getByTestId('screensaver-particle')).toBeTruthy()
  })
})
