import { useSettingsStore, FONT_SIZE_SCALES } from '@/stores/settingsStore'
import type { ThemeMode } from '@/stores/settingsStore'

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
  bg: '#0B0E13',
  bgAlt: '#111722',
  surface: 'rgba(17,23,34,0.88)',
  raised: '#172031',
  border: '#27334A',
  borderHi: '#3A4A67',
  text: '#F8F9FF',
  sec: '#CED6E5',
  dim: '#8C98B2',
  muted: '#1A2232',
  surface0: '#0F1520',
  surface1: '#131C2A',
  surface2: '#172131',
  surface3: '#1D283C',
  surface4: '#24334A',
  surface5: '#2B3E58',
  surface6: '#32486A',
  cyan: '#49D9CB',
  green: '#3FD389',
  amber: '#E3A554',
  yellow: '#F0CB6A',
  orange: '#EB8D5B',
  red: '#E26E75',
  blue: '#6FB2FF',
  purple: '#B4A8FF',
  pink: '#EC93C6',
  teal: '#6CD7D8',
  shadow: 'rgba(6,8,14,0.35)',
  shadowHeavy: 'rgba(5,7,12,0.62)',
  shadowLight: 'rgba(22,28,41,0.2)',
}

const LIGHT: ThemeTokens = {
  bg: '#F3F5F8',
  bgAlt: '#E8ECF4',
  surface: 'rgba(255,255,255,0.9)',
  raised: '#FFFFFF',
  border: '#D7DDE8',
  borderHi: '#C0C9D8',
  text: '#1A2232',
  sec: '#33445C',
  dim: '#677690',
  muted: '#EDF1F8',
  surface0: '#FBFCFF',
  surface1: '#F6F8FC',
  surface2: '#EFF3FA',
  surface3: '#E8EEF8',
  surface4: '#DDE6F3',
  surface5: '#D3DFF0',
  surface6: '#C7D7EC',
  cyan: '#0E8B7F',
  green: '#208A51',
  amber: '#AD6B1C',
  yellow: '#9A7A14',
  orange: '#B3562A',
  red: '#AF3743',
  blue: '#1D5CC3',
  purple: '#6544C3',
  pink: '#AB396E',
  teal: '#0A7F88',
  shadow: 'rgba(36,49,74,0.14)',
  shadowHeavy: 'rgba(31,42,62,0.22)',
  shadowLight: 'rgba(67,89,125,0.09)',
}

export function getTheme(mode: ThemeMode): ThemeTokens {
  return mode === 'light' ? LIGHT : DARK
}

export const T: ThemeTokens = new Proxy(DARK, {
  get(_target, prop: string) {
    const { theme: mode, accentColor } = useSettingsStore.getState()
    const theme = mode === 'light' ? LIGHT : DARK
    if (prop === 'cyan') {
      return (theme as any)[accentColor] || theme.cyan
    }
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
    const scale = FONT_SIZE_SCALES[useSettingsStore.getState().fontSize] ?? 1.0
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
  dataset: '#4BC3F2',
  text: '#72A8FF',
  model: '#B09DFF',
  config: '#EB8D5B',
  metrics: '#57D99A',
  embedding: '#E98ABD',
  artifact: '#58C5D7',
  agent: '#EA7784',
  llm: '#E3A554',
  any: '#F0CB6A',
  data: '#4BC3F2',
  external: '#4BC3F2',
  training: '#B09DFF',
  intervention: '#F0CB6A',
}

export const CATEGORY_COLORS: Record<string, string> = {
  external: '#E89A66',
  data: '#56C6EE',
  model: '#B4A8FF',
  training: '#72A8FF',
  metrics: '#58D29C',
  embedding: '#EC93C6',
  utilities: '#9EB2D1',
  agents: '#EA7784',
  interventions: '#F0CB6A',
  inference: '#91D873',
  endpoints: '#66CAD9',
}

export const STATUS_COLORS: Record<string, string> = {
  planning: '#E3A554',
  active: '#49D9CB',
  complete: '#3FD389',
  paused: '#F0CB6A',
  failed: '#E26E75',
  running: '#E3A554',
  pending: '#8C98B2',
  idle: '#8C98B2',
  cancelled: '#EB8D5B',
}

export function injectThemeCSSVars(mode: ThemeMode) {
  const t = mode === 'light' ? LIGHT : DARK
  const { accentColor } = useSettingsStore.getState()
  const activeAccent = (t as any)[accentColor] || t.cyan

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
  root.style.setProperty('--shadow', t.shadow)
  root.style.setProperty('--shadow-heavy', t.shadowHeavy)
  root.style.setProperty('--shadow-light', t.shadowLight)
  root.style.setProperty('--scrollbar-thumb', mode === 'light' ? 'rgba(35,52,79,0.22)' : 'rgba(206,214,229,0.18)')
  root.style.setProperty('--scrollbar-thumb-hover', mode === 'light' ? 'rgba(35,52,79,0.34)' : 'rgba(206,214,229,0.32)')
  root.style.setProperty('--select-bg', mode === 'light' ? '#FFFFFF' : '#1D283C')
  root.style.setProperty('--select-color', t.text)
}
