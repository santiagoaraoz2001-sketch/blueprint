import { useSettingsStore, FONT_SIZE_SCALES } from '@/stores/settingsStore'
import type { ThemeMode, AccentColor } from '@/stores/settingsStore'
import { useUIStore } from '@/stores/uiStore'
import type { View } from '@/stores/uiStore'

export interface ThemeTokens {
  bg: string
  bgAlt: string
  surface: string
  raised: string
  border: string
  borderHi: string
  text: string
  sec: string
  dim: string
  muted: string
  surface0: string
  surface1: string
  surface2: string
  surface3: string
  surface4: string
  surface5: string
  surface6: string
  cyan: string
  green: string
  amber: string
  yellow: string
  orange: string
  red: string
  blue: string
  purple: string
  pink: string
  teal: string
  shadow: string
  shadowHeavy: string
  shadowLight: string
}

const DARK: ThemeTokens = {
  bg: '#07080B',
  bgAlt: '#0B0D11',
  surface: 'rgba(17,18,24,0.9)',
  raised: '#14161D',
  border: '#2C313B',
  borderHi: '#434B58',
  text: '#F4F5F8',
  sec: '#C8CCD5',
  dim: '#8D95A4',
  muted: '#1D2029',
  surface0: '#0D0F14',
  surface1: '#11141B',
  surface2: '#171A23',
  surface3: '#1E232E',
  surface4: '#252B38',
  surface5: '#2D3544',
  surface6: '#364154',
  cyan: '#50D8C0',
  green: '#67D57A',
  amber: '#E3B26A',
  yellow: '#E9D177',
  orange: '#E08A62',
  red: '#E37B83',
  blue: '#7897E6',
  purple: '#A991EB',
  pink: '#DD8FC0',
  teal: '#52C6D0',
  shadow: 'rgba(0,0,0,0.45)',
  shadowHeavy: 'rgba(0,0,0,0.68)',
  shadowLight: 'rgba(32,36,46,0.24)',
}

const LIGHT: ThemeTokens = {
  bg: '#F5F5F7',
  bgAlt: '#ECECF1',
  surface: 'rgba(255,255,255,0.92)',
  raised: '#FFFFFF',
  border: '#D9DCE3',
  borderHi: '#C4CAD6',
  text: '#1F2430',
  sec: '#3B465A',
  dim: '#6D778B',
  muted: '#ECEFF5',
  surface0: '#FCFCFE',
  surface1: '#F6F7FB',
  surface2: '#EFF2F8',
  surface3: '#E8EDF6',
  surface4: '#DEE5F2',
  surface5: '#D3DDEF',
  surface6: '#C9D7EC',
  cyan: '#0D8B74',
  green: '#2F8B46',
  amber: '#A96B22',
  yellow: '#9F8119',
  orange: '#B4572A',
  red: '#AF3543',
  blue: '#2F56B7',
  purple: '#6342B8',
  pink: '#A43C71',
  teal: '#117E88',
  shadow: 'rgba(36,49,74,0.14)',
  shadowHeavy: 'rgba(31,42,62,0.22)',
  shadowLight: 'rgba(67,89,125,0.09)',
}

const ACCENT_BY_NAME: Record<AccentColor, keyof ThemeTokens> = {
  cyan: 'cyan',
  orange: 'orange',
  green: 'green',
  blue: 'blue',
  purple: 'purple',
  pink: 'pink',
}

const VIEW_ACCENT_MAP: Partial<Record<View, keyof ThemeTokens>> = {
  research: 'teal',
  dashboard: 'amber',
  editor: 'teal',
  monitor: 'green',
  output: 'orange',
  results: 'pink',
  visualization: 'purple',
  paper: 'amber',
  settings: 'purple',
  help: 'teal',
  data: 'green',
  datasets: 'orange',
  marketplace: 'teal',
  workshop: 'pink',
}

function hexToRgb(hex: string) {
  const clean = hex.replace('#', '')
  const value = clean.length === 3
    ? clean.split('').map((x) => x + x).join('')
    : clean
  const int = Number.parseInt(value, 16)
  return { r: (int >> 16) & 255, g: (int >> 8) & 255, b: int & 255 }
}

function rgbToHex(r: number, g: number, b: number) {
  const toHex = (v: number) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`
}

function blendHex(base: string, overlay: string, ratio = 0.5) {
  const a = hexToRgb(base)
  const b = hexToRgb(overlay)
  const r = a.r * (1 - ratio) + b.r * ratio
  const g = a.g * (1 - ratio) + b.g * ratio
  const bl = a.b * (1 - ratio) + b.b * ratio
  return rgbToHex(r, g, bl)
}

function getAdaptiveAccent(theme: ThemeTokens, accentColor: AccentColor, view: View): string {
  const userAccent = theme[ACCENT_BY_NAME[accentColor]] as string
  const viewAccent = theme[(VIEW_ACCENT_MAP[view] || 'teal') as keyof ThemeTokens] as string
  return blendHex(viewAccent, userAccent, 0.42)
}

function getActiveTheme() {
  const settings = typeof (useSettingsStore as any).getState === 'function'
    ? (useSettingsStore as any).getState()
    : ({ theme: 'dark', accentColor: 'cyan' } as { theme: ThemeMode; accentColor: AccentColor })
  const theme = settings.theme === 'light' ? LIGHT : DARK
  const view = typeof (useUIStore as any).getState === 'function'
    ? ((useUIStore as any).getState().activeView as View)
    : 'research'
  const accent = getAdaptiveAccent(theme, settings.accentColor, view)
  return { theme, accent, view }
}

export function getTheme(mode: ThemeMode): ThemeTokens {
  return mode === 'light' ? LIGHT : DARK
}

export const T: ThemeTokens = new Proxy(DARK, {
  get(_target, prop: string) {
    const { theme, accent } = getActiveTheme()
    if (prop === 'cyan') return accent
    return (theme as any)[prop]
  },
})

export const F = "'IBM Plex Sans','Inter','Segoe UI',sans-serif"
export const FCODE = "'JetBrains Mono','SF Mono','Fira Code',monospace"

const FS_BASE = {
  xxs: 10,
  xs: 11,
  sm: 12,
  md: 13,
  lg: 15,
  xl: 17,
  xxl: 20,
  h3: 23,
  h2: 28,
}

export type FontSizeTokens = typeof FS_BASE

export const FS: FontSizeTokens = new Proxy(FS_BASE, {
  get(_target, prop: string) {
    const fontSize = typeof (useSettingsStore as any).getState === 'function'
      ? (useSettingsStore as any).getState().fontSize
      : 'default'
    const scale = FONT_SIZE_SCALES[fontSize] ?? 1.0
    const base = (FS_BASE as any)[prop]
    return typeof base === 'number' ? Math.round(base * scale * 100) / 100 : base
  },
})

export const FD = "'Sora','Avenir Next','Segoe UI',sans-serif"

export const MOTION = {
  fast: 0.16,
  base: 0.24,
  slow: 0.38,
  spring: { type: 'spring' as const, stiffness: 260, damping: 26 },
  ease: [0.16, 1, 0.3, 1] as [number, number, number, number],
}

export const ELEVATION = {
  panel: `0 12px 30px ${T.shadow}, inset 0 1px 0 rgba(255,255,255,0.06)`,
  floating: `0 22px 42px ${T.shadowHeavy}, inset 0 1px 0 rgba(255,255,255,0.08)`,
  glow: (color: string) => `0 0 0 1px ${color}35, 0 0 24px ${color}28`,
}

export const CONNECTOR_COLORS: Record<string, string> = {
  dataset: '#5FB8E8',
  text: '#7B9BE3',
  model: '#B29CEA',
  config: '#E08A62',
  metrics: '#67D57A',
  embedding: '#DD8FC0',
  artifact: '#52C6D0',
  agent: '#E37B83',
  llm: '#E3B26A',
  any: '#E9D177',
  data: '#5FB8E8',
  external: '#5FB8E8',
  training: '#B29CEA',
  intervention: '#E9D177',
}

export const CATEGORY_COLORS: Record<string, string> = {
  external: '#DFA074',
  data: '#6BBAD9',
  model: '#A991EB',
  training: '#7B9BE3',
  metrics: '#70D68B',
  embedding: '#DD8FC0',
  utilities: '#9DA7BC',
  agents: '#E37B83',
  interventions: '#E9D177',
  inference: '#96D588',
  endpoints: '#62C6B4',
}

export const STATUS_COLORS: Record<string, string> = {
  planning: '#E3B26A',
  active: '#50D8C0',
  complete: '#67D57A',
  paused: '#E9D177',
  failed: '#E37B83',
  running: '#E3B26A',
  pending: '#8D95A4',
  idle: '#8D95A4',
  cancelled: '#E08A62',
}

export function injectThemeCSSVars(mode: ThemeMode, view?: View) {
  const t = mode === 'light' ? LIGHT : DARK
  const accentColor = (typeof (useSettingsStore as any).getState === 'function'
    ? (useSettingsStore as any).getState().accentColor
    : 'cyan') as AccentColor
  const activeView = view ?? (typeof (useUIStore as any).getState === 'function'
    ? ((useUIStore as any).getState().activeView as View)
    : 'research')
  const activeAccent = getAdaptiveAccent(t, accentColor, activeView)
  const secondaryHue = t[(VIEW_ACCENT_MAP[activeView] || 'purple') as keyof ThemeTokens] as string

  const root = document.documentElement
  root.style.setProperty('--bg', t.bg)
  root.style.setProperty('--bg-alt', t.bgAlt)
  root.style.setProperty('--text', t.text)
  root.style.setProperty('--sec', t.sec)
  root.style.setProperty('--dim', t.dim)
  root.style.setProperty('--surface0', t.surface0)
  root.style.setProperty('--surface1', t.surface1)
  root.style.setProperty('--surface2', t.surface2)
  root.style.setProperty('--border', t.border)
  root.style.setProperty('--border-hi', t.borderHi)
  root.style.setProperty('--cyan', activeAccent)
  root.style.setProperty('--hue-glow', activeAccent)
  root.style.setProperty('--hue-secondary', secondaryHue)
  root.style.setProperty('--shadow', t.shadow)
  root.style.setProperty('--shadow-heavy', t.shadowHeavy)
  root.style.setProperty('--shadow-light', t.shadowLight)
  root.style.setProperty('--scrollbar-thumb', mode === 'light' ? 'rgba(35,52,79,0.22)' : 'rgba(206,214,229,0.18)')
  root.style.setProperty('--scrollbar-thumb-hover', mode === 'light' ? 'rgba(35,52,79,0.34)' : 'rgba(206,214,229,0.32)')
  root.style.setProperty('--select-bg', mode === 'light' ? '#FFFFFF' : '#1E232E')
  root.style.setProperty('--select-color', t.text)
}
