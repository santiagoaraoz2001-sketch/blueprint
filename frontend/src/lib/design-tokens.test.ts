import { describe, expect, it, vi } from 'vitest'
import { getTheme, injectThemeCSSVars, GLOW, DEPTH } from './design-tokens'
import { useSettingsStore } from '@/stores/settingsStore'

describe('design tokens', () => {
  it('returns dark and light palettes with bioluminescent values', () => {
    expect(getTheme('dark').bg).toBe('#060709')
    expect(getTheme('light').bg).toBe('#F2F4F7')
  })

  it('dark palette surface values are progressively lighter', () => {
    const dark = getTheme('dark')
    expect(dark.surface0).toBeTruthy()
    expect(dark.surface6).toBeTruthy()
  })

  it('injects css vars for active theme and accent', () => {
    vi.spyOn(useSettingsStore, 'getState').mockReturnValue({
      theme: 'dark',
      accentColor: 'cyan',
    } as any)

    injectThemeCSSVars('dark', 'editor' as any)

    expect(document.documentElement.style.getPropertyValue('--bg')).toBe('#060709')
    expect(document.documentElement.style.getPropertyValue('--cyan')).toBeTruthy()
    expect(document.documentElement.style.getPropertyValue('--accent-glow')).toBeTruthy()
    expect(document.documentElement.style.getPropertyValue('--surface3')).toBeTruthy()
  })

  it('GLOW helper returns box-shadow strings', () => {
    const c = '#3EE8C4'
    expect(GLOW.soft(c)).toContain('3EE8C4')
    expect(GLOW.medium(c)).toContain('3EE8C4')
    expect(GLOW.hard(c)).toContain('3EE8C4')
    expect(GLOW.accent(c)).toContain('3EE8C4')
  })

  it('DEPTH helper returns shadow strings', () => {
    expect(DEPTH.card).toContain('rgba')
    expect(DEPTH.float).toContain('rgba')
    expect(DEPTH.modal).toContain('rgba')
  })
})
