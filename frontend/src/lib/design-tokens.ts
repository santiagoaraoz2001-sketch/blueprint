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

// Bioluminescent lab palette — deep ink, punchy vivid accents
const DARK: ThemeTokens = {
  bg:       '#060709',
  bgAlt:    '#090C11',
  surface:  'rgba(16,20,28,0.94)',
  raised:   '#12161F',
  border:   '#252E3C',
  borderHi: '#374659',
  text:     '#F2F4F8',
  sec:      '#C4CDDE',
  dim:      '#7A8799',
  muted:    '#1A1F2C',
  surface0: '#0B0D13',
  surface1: '#0F1319',
  surface2: '#141922',
  surface3: '#1B2130',
  surface4: '#222A3C',
  surface5: '#2C3649',
  surface6: '#384557',
  // Vivid bioluminescent accents — fully saturated, high brightness
  cyan:   '#2FFCC8',
  green:  '#3EF07A',
  amber:  '#FFBE45',
  yellow: '#FFE055',
  orange: '#FF8C4A',
  red:    '#FF5E72',
  blue:   '#5B96FF',
  purple: '#A87EFF',
  pink:   '#F070C8',
  teal:   '#35D8F0',
  shadow:      'rgba(0,0,0,0.60)',
  shadowHeavy: 'rgba(0,0,0,0.76)',
  shadowLight: 'rgba(18,24,40,0.28)',
}

const LIGHT: ThemeTokens = {
  bg:       '#F2F4F7',
  bgAlt:    '#EAEDF2',
  surface:  'rgba(255,255,255,0.94)',
  raised:   '#FFFFFF',
  border:   '#D6DAE3',
  borderHi: '#C0C9D8',
  text:     '#1A2130',
  sec:      '#374459',
  dim:      '#667080',
  muted:    '#E8ECF4',
  surface0: '#FAFBFE',
  surface1: '#F4F6FB',
  surface2: '#EDF1F8',
  surface3: '#E5EBF6',
  surface4: '#DAE3F2',
  surface5: '#CFDBEE',
  surface6: '#C4D2EA',
  cyan:   '#0A8870',
  green:  '#2B8A42',
  amber:  '#A5681E',
  yellow: '#9B7D14',
  orange: '#B0521E',
  red:    '#AA2F3E',
  blue:   '#2B52B4',
  purple: '#5F3EB5',
  pink:   '#A03870',
  teal:   '#0F7B84',
  shadow:      'rgba(26,40,64,0.13)',
  shadowHeavy: 'rgba(20,34,56,0.20)',
  shadowLight: 'rgba(58,80,118,0.08)',
}

const ACCENT_BY_NAME: Record<AccentColor, keyof ThemeTokens> = {
  cyan:   'cyan',
  orange: 'orange',
  green:  'green',
  blue:   'blue',
  purple: 'purple',
  pink:   'pink',
}

const VIEW_ACCENT_MAP: Partial<Record<View, keyof ThemeTokens>> = {
  research:      'teal',
  dashboard:     'amber',
  editor:        'teal',
  monitor:       'green',
  output:        'orange',
  results:       'pink',
  visualization: 'purple',
  paper:         'amber',
  settings:      'purple',
  help:          'teal',
  data:          'green',
  datasets:      'orange',
  marketplace:   'teal',
  workshop:      'pink',
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
  return rgbToHex(
    a.r * (1 - ratio) + b.r * ratio,
    a.g * (1 - ratio) + b.g * ratio,
    a.b * (1 - ratio) + b.b * ratio,
  )
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

// Body + UI font
export const F     = "'IBM Plex Sans','Inter','Segoe UI',sans-serif"
export const FCODE = "'JetBrains Mono','SF Mono','Fira Code',monospace"

const FS_BASE = {
  xxs: 10,
  xs:  11,
  sm:  12,
  md:  13,
  lg:  15,
  xl:  17,
  xxl: 20,
  h3:  23,
  h2:  28,
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

// Display / brand font — MUST remain Space Grotesk; this is the identity font
// used in the SPECIFIC LABS logomark SVG wordmark. Do not change.
export const FD = "'Space Grotesk','Helvetica Neue',Arial,sans-serif"

export const MOTION = {
  fast:   0.16,
  base:   0.24,
  slow:   0.38,
  spring: { type: 'spring' as const, stiffness: 260, damping: 26 },
  ease:   [0.16, 1, 0.3, 1] as [number, number, number, number],
}

export const ELEVATION = {
  panel:    `0 8px 24px rgba(0,0,0,0.5), 0 2px 6px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.05)`,
  floating: `0 18px 40px rgba(0,0,0,0.65), 0 4px 12px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.07)`,
  glow:     (color: string) => `0 0 0 1px ${color}30, 0 0 20px ${color}22, 0 0 40px ${color}10`,
}

// Multi-layer glow recipes for bioluminescent accents
export const GLOW = {
  soft:   (c: string) => `0 0 12px ${c}18, 0 0 4px ${c}22`,
  medium: (c: string) => `0 0 20px ${c}28, 0 0 8px ${c}35, 0 0 2px ${c}50`,
  hard:   (c: string) => `0 0 30px ${c}40, 0 0 12px ${c}55, 0 0 4px ${c}70`,
  accent: (c: string) => `0 0 0 1px ${c}28, 0 0 16px ${c}25, 0 0 32px ${c}12`,
}

// Depth shadow recipes tuned for the deep-ink palette
export const DEPTH = {
  card:  `0 4px 16px rgba(0,0,0,0.48), 0 1px 4px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.04)`,
  float: `0 16px 48px rgba(0,0,0,0.62), 0 6px 16px rgba(0,0,0,0.42), inset 0 1px 0 rgba(255,255,255,0.06)`,
  modal: `0 32px 80px rgba(0,0,0,0.72), 0 12px 28px rgba(0,0,0,0.52), inset 0 1px 0 rgba(255,255,255,0.08)`,
}

export const CONNECTOR_COLORS: Record<string, string> = {
  dataset:      '#5FB8E8',
  text:         '#7B9BE3',
  model:        '#B29CEA',
  config:       '#DE7B4F',
  metrics:      '#52D975',
  embedding:    '#D87CB8',
  artifact:     '#48C8D8',
  agent:        '#E06070',
  llm:          '#E8A84A',
  any:          '#E8D05A',
  data:         '#5FB8E8',
  external:     '#5FB8E8',
  training:     '#B29CEA',
  intervention: '#E8D05A',
}

export const CATEGORY_COLORS: Record<string, string> = {
  external:      '#DE9A68',
  data:          '#62B8D9',
  model:         '#9880E8',
  training:      '#7B9BE3',
  metrics:       '#65D68B',
  embedding:     '#D87CB8',
  utilities:     '#98A4B8',
  agents:        '#E06070',
  interventions: '#E8D05A',
  inference:     '#8FD07A',
  endpoints:     '#56C4B0',
}

export const STATUS_COLORS: Record<string, string> = {
  planning:  '#E8A84A',
  active:    '#3EE8C4',
  complete:  '#52D975',
  paused:    '#E8D05A',
  failed:    '#E06070',
  running:   '#E8A84A',
  pending:   '#6E7888',
  idle:      '#6E7888',
  cancelled: '#DE7B4F',
}

export function injectThemeCSSVars(mode: ThemeMode, view?: View) {
  const t = mode === 'light' ? LIGHT : DARK
  const accentColor = (typeof (useSettingsStore as any).getState === 'function'
    ? (useSettingsStore as any).getState().accentColor
    : 'cyan') as AccentColor
  const activeView = view ?? (typeof (useUIStore as any).getState === 'function'
    ? ((useUIStore as any).getState().activeView as View)
    : 'research')
  const activeAccent   = getAdaptiveAccent(t, accentColor, activeView)
  const secondaryHue   = t[(VIEW_ACCENT_MAP[activeView] || 'purple') as keyof ThemeTokens] as string

  const root = document.documentElement
  root.style.setProperty('--bg',           t.bg)
  root.style.setProperty('--bg-alt',       t.bgAlt)
  root.style.setProperty('--text',         t.text)
  root.style.setProperty('--sec',          t.sec)
  root.style.setProperty('--dim',          t.dim)
  root.style.setProperty('--surface0',     t.surface0)
  root.style.setProperty('--surface1',     t.surface1)
  root.style.setProperty('--surface2',     t.surface2)
  root.style.setProperty('--surface3',     t.surface3)
  root.style.setProperty('--surface4',     t.surface4)
  root.style.setProperty('--surface5',     t.surface5)
  root.style.setProperty('--surface6',     t.surface6)
  root.style.setProperty('--border',       t.border)
  root.style.setProperty('--border-hi',    t.borderHi)
  root.style.setProperty('--cyan',         activeAccent)
  root.style.setProperty('--hue-glow',     activeAccent)
  root.style.setProperty('--hue-secondary', secondaryHue)
  // Accent glow at 20% opacity for ambient fill
  const rgb = hexToRgb(activeAccent)
  root.style.setProperty('--accent-glow',  `rgba(${rgb.r},${rgb.g},${rgb.b},0.20)`)
  root.style.setProperty('--shadow',             t.shadow)
  root.style.setProperty('--shadow-heavy',       t.shadowHeavy)
  root.style.setProperty('--shadow-light',       t.shadowLight)
  root.style.setProperty('--scrollbar-thumb',       mode === 'light' ? 'rgba(35,52,79,0.20)' : 'rgba(206,214,229,0.15)')
  root.style.setProperty('--scrollbar-thumb-hover', mode === 'light' ? 'rgba(35,52,79,0.32)' : 'rgba(206,214,229,0.28)')
  root.style.setProperty('--select-bg',    mode === 'light' ? '#FFFFFF' : t.surface3)
  root.style.setProperty('--select-color', t.text)
}
