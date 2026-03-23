import { describe, expect, it, vi } from 'vitest'
import { getTheme, injectThemeCSSVars } from './design-tokens'
import { useSettingsStore } from '@/stores/settingsStore'

describe('design tokens', () => {
  it('returns dark and light palettes', () => {
    expect(getTheme('dark').bg).toBe('#07080B')
    expect(getTheme('light').bg).toBe('#F5F5F7')
  })

  it('injects css vars for active theme and accent', () => {
    vi.spyOn(useSettingsStore, 'getState').mockReturnValue({
      theme: 'dark',
      accentColor: 'cyan',
    } as any)

    injectThemeCSSVars('dark', 'editor' as any)

    expect(document.documentElement.style.getPropertyValue('--bg')).toBe('#07080B')
    expect(document.documentElement.style.getPropertyValue('--cyan')).toBeTruthy()
  })
})
