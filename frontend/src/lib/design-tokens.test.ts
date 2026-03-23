import { describe, expect, it, vi } from 'vitest'
import { getTheme, injectThemeCSSVars } from './design-tokens'
import { useSettingsStore } from '@/stores/settingsStore'

describe('design tokens', () => {
  it('returns dark and light palettes', () => {
    expect(getTheme('dark').bg).toBe('#0B0E13')
    expect(getTheme('light').bg).toBe('#F3F5F8')
  })

  it('injects css vars for active theme and accent', () => {
    vi.spyOn(useSettingsStore, 'getState').mockReturnValue({
      theme: 'dark',
      accentColor: 'teal',
    } as any)

    injectThemeCSSVars('dark')

    expect(document.documentElement.style.getPropertyValue('--bg')).toBe('#0B0E13')
    expect(document.documentElement.style.getPropertyValue('--cyan')).toBe('#6CD7D8')
  })
})
