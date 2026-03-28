import { describe, expect, it, vi, beforeEach } from 'vitest'
import { getTheme, injectThemeCSSVars, resolveThemeMode, getMonacoTheme } from '../design-tokens'
import { useSettingsStore } from '@/stores/settingsStore'

describe('theme system — system preference detection', () => {
  beforeEach(() => {
    // Reset to defaults
    vi.restoreAllMocks()
  })

  it('getTheme resolves "system" based on matchMedia', () => {
    // Mock prefers dark
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: true,
      media: '(prefers-color-scheme: dark)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as any)

    const t = getTheme('system')
    expect(t.bg).toBe('#060709') // dark bg
  })

  it('getTheme resolves "system" to light when preference is light', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: false,
      media: '(prefers-color-scheme: dark)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as any)

    const t = getTheme('system')
    expect(t.bg).toBe('#F2F4F7') // light bg
  })

  it('injectThemeCSSVars handles "system" mode', () => {
    vi.spyOn(useSettingsStore, 'getState').mockReturnValue({
      theme: 'system',
      accentColor: 'cyan',
    } as any)

    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: true,
      media: '(prefers-color-scheme: dark)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as any)

    injectThemeCSSVars('system', 'editor' as any)

    expect(document.documentElement.style.getPropertyValue('--bg')).toBe('#060709')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('injectThemeCSSVars sets data-theme attribute', () => {
    vi.spyOn(useSettingsStore, 'getState').mockReturnValue({
      theme: 'light',
      accentColor: 'cyan',
    } as any)

    injectThemeCSSVars('light', 'editor' as any)

    expect(document.documentElement.dataset.theme).toBe('light')
    expect(document.documentElement.style.getPropertyValue('--bg')).toBe('#F2F4F7')
  })

  it('getMonacoTheme returns vs-dark for dark, vs for light', () => {
    vi.spyOn(useSettingsStore, 'getState').mockReturnValue({
      theme: 'dark',
      accentColor: 'cyan',
    } as any)

    expect(getMonacoTheme()).toBe('vs-dark')

    vi.spyOn(useSettingsStore, 'getState').mockReturnValue({
      theme: 'light',
      accentColor: 'cyan',
    } as any)

    expect(getMonacoTheme()).toBe('vs')
  })
})

describe('WCAG AA color contrast', () => {
  function luminance(hex: string) {
    const clean = hex.replace('#', '')
    const r = parseInt(clean.slice(0, 2), 16) / 255
    const g = parseInt(clean.slice(2, 4), 16) / 255
    const b = parseInt(clean.slice(4, 6), 16) / 255
    const srgb = (c: number) => c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
    return 0.2126 * srgb(r) + 0.7152 * srgb(g) + 0.0722 * srgb(b)
  }

  function contrastRatio(c1: string, c2: string) {
    let l1 = luminance(c1)
    let l2 = luminance(c2)
    if (l1 < l2) [l1, l2] = [l2, l1]
    return (l1 + 0.05) / (l2 + 0.05)
  }

  it('dark theme: text on bg meets 4.5:1', () => {
    const dark = getTheme('dark')
    expect(contrastRatio(dark.text, dark.bg)).toBeGreaterThanOrEqual(4.5)
  })

  it('dark theme: sec text on bg meets 4.5:1', () => {
    const dark = getTheme('dark')
    expect(contrastRatio(dark.sec, dark.bg)).toBeGreaterThanOrEqual(4.5)
  })

  it('dark theme: dim text on bg meets 4.5:1', () => {
    const dark = getTheme('dark')
    expect(contrastRatio(dark.dim, dark.bg)).toBeGreaterThanOrEqual(4.5)
  })

  it('dark theme: dim text on surface2 meets 4.5:1', () => {
    const dark = getTheme('dark')
    expect(contrastRatio(dark.dim, dark.surface2)).toBeGreaterThanOrEqual(4.5)
  })

  it('light theme: text on bg meets 4.5:1', () => {
    const light = getTheme('light')
    expect(contrastRatio(light.text, light.bg)).toBeGreaterThanOrEqual(4.5)
  })

  it('light theme: sec text on bg meets 4.5:1', () => {
    const light = getTheme('light')
    expect(contrastRatio(light.sec, light.bg)).toBeGreaterThanOrEqual(4.5)
  })

  it('light theme: dim text on bg meets 4.5:1', () => {
    const light = getTheme('light')
    expect(contrastRatio(light.dim, light.bg)).toBeGreaterThanOrEqual(4.5)
  })

  it('light theme: cyan accent on bg meets 4.5:1', () => {
    const light = getTheme('light')
    expect(contrastRatio(light.cyan, light.bg)).toBeGreaterThanOrEqual(4.5)
  })

  it('light theme: green on bg meets 4.5:1', () => {
    const light = getTheme('light')
    expect(contrastRatio(light.green, light.bg)).toBeGreaterThanOrEqual(4.5)
  })

  it('light theme: amber on bg meets 4.5:1', () => {
    const light = getTheme('light')
    expect(contrastRatio(light.amber, light.bg)).toBeGreaterThanOrEqual(4.5)
  })

  it('light theme: yellow on bg meets 4.5:1', () => {
    const light = getTheme('light')
    expect(contrastRatio(light.yellow, light.bg)).toBeGreaterThanOrEqual(4.5)
  })
})

describe('resolveThemeMode helper', () => {
  it('returns dark when settings theme is dark', () => {
    vi.spyOn(useSettingsStore, 'getState').mockReturnValue({
      theme: 'dark',
      accentColor: 'cyan',
    } as any)
    expect(resolveThemeMode()).toBe('dark')
  })

  it('returns light when settings theme is light', () => {
    vi.spyOn(useSettingsStore, 'getState').mockReturnValue({
      theme: 'light',
      accentColor: 'cyan',
    } as any)
    expect(resolveThemeMode()).toBe('light')
  })

  it('resolves system to dark when OS prefers dark', () => {
    vi.spyOn(useSettingsStore, 'getState').mockReturnValue({
      theme: 'system',
      accentColor: 'cyan',
    } as any)
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: true,
      media: '(prefers-color-scheme: dark)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as any)
    expect(resolveThemeMode()).toBe('dark')
  })

  it('resolves system to light when OS prefers light', () => {
    vi.spyOn(useSettingsStore, 'getState').mockReturnValue({
      theme: 'system',
      accentColor: 'cyan',
    } as any)
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: false,
      media: '(prefers-color-scheme: dark)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as any)
    expect(resolveThemeMode()).toBe('light')
  })
})
