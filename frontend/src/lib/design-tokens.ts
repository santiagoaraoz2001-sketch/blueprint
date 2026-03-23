// Specific Labs — Shared Design Tokens (ported from Control Tower)
// Theme-aware: supports dark and light modes

import { useSettingsStore, FONT_SIZE_SCALES } from '@/stores/settingsStore'
import type { ThemeMode } from '@/stores/settingsStore'

export interface ThemeTokens {
  bg: string; surface: string; raised: string; border: string; borderHi: string
  text: string; sec: string; dim: string; muted: string
  surface0: string; surface1: string; surface2: string; surface3: string
  surface4: string; surface5: string; surface6: string
  cyan: string; green: string; amber: string; yellow: string; orange: string
  red: string; blue: string; purple: string; pink: string
  shadow: string; shadowHeavy: string; shadowLight: string
}

const DARK: ThemeTokens = {
  bg: "#000000", surface: "rgba(5,5,5,0.92)", raised: "#050505",
  border: "#111111", borderHi: "#222222",
  text: "#FFFFFF", sec: "#b5b5b5", dim: "#666666", muted: "#1a1a1a",
  surface0: "#030303", surface1: "#040404", surface2: "#060606",
  surface3: "#080808", surface4: "#0A0A0A", surface5: "#0D0D0D", surface6: "#0E0E0E",
  cyan: "#4af6c3", green: "#22c55e", amber: "#f59e0b", yellow: "#EAB308",
  orange: "#fb8b1e", red: "#ff433d", blue: "#0068ff", purple: "#8B5CF6", pink: "#EC4899",
  shadow: "rgba(0,0,0,0.4)", shadowHeavy: "rgba(0,0,0,0.6)", shadowLight: "rgba(0,0,0,0.2)",
}

const LIGHT: ThemeTokens = {
  bg: "#FBFBFD", surface: "rgba(255,255,255,0.98)", raised: "#FFFFFF",
  border: "#E2E4EA", borderHi: "#D0D3DA",
  text: "#1C1C2E", sec: "#464660", dim: "#8A8AA0", muted: "#F0F0F5",
  surface0: "#FAFAFC", surface1: "#F5F5FA", surface2: "#EDEDF3",
  surface3: "#E5E5EE", surface4: "#DDDDE8", surface5: "#D4D4E0", surface6: "#CCCCD9",
  cyan: "#0B8A5E", green: "#15803D", amber: "#B45309", yellow: "#A16207",
  orange: "#C2410C", red: "#B91C1C", blue: "#1D4ED8", purple: "#6D28D9", pink: "#BE185D",
  shadow: "rgba(0,0,0,0.08)", shadowHeavy: "rgba(0,0,0,0.15)", shadowLight: "rgba(0,0,0,0.04)",
}

export function getTheme(mode: ThemeMode): ThemeTokens {
  return mode === 'light' ? LIGHT : DARK
}

// Live reactive token — reads from settings store on each access
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

// Font — static default
export const F = "'JetBrains Mono','SF Mono','Fira Code',monospace"

// Base font sizes — scaled reactively by the fontSize setting
const FS_BASE = {
  xxs: 5.5, xs: 6, sm: 7, md: 8, lg: 9, xl: 10, xxl: 11, h3: 13, h2: 15,
}

export type FontSizeTokens = typeof FS_BASE

// Reactive font size proxy — reads scale factor from settingsStore on each access
export const FS: FontSizeTokens = new Proxy(FS_BASE, {
  get(_target, prop: string) {
    const scale = FONT_SIZE_SCALES[useSettingsStore.getState().fontSize] ?? 1.0
    const base = (FS_BASE as any)[prop]
    return typeof base === 'number' ? Math.round(base * scale * 100) / 100 : base
  },
})

export const FD = "'Space Grotesk','Helvetica Neue',Arial,sans-serif"

// Connector colors — 10 wire types that flow between blocks
export const CONNECTOR_COLORS: Record<string, string> = {
  dataset:      '#22D3EE',   // cyan — structured tabular data
  text:         '#60A5FA',   // light blue — raw text, prompts, strings
  model:        '#A78BFA',   // violet — model weights, adapters
  config:       '#F97316',   // orange — configuration objects, settings
  metrics:      '#34D399',   // emerald — evaluation scores, stats
  embedding:    '#FB7185',   // rose — vector embeddings
  artifact:     '#38BDF8',   // sky blue — files, reports, packages
  agent:        '#F43F5E',   // crimson — autonomous agent instances
  llm:          '#E8A030',   // warm gold — LLM provider config (distinct from violet model & orange config)
  any:          '#FBBF24',   // amber — generic pass-through
  // Backward compat aliases (old type names → new colors)
  data:         '#22D3EE',   // old catch-all → dataset color
  external:     '#22D3EE',   // old external → dataset color
  training:     '#A78BFA',   // old training → model color
  intervention: '#FBBF24',   // old intervention → any color
}

// Category accent colors — 10 unique colors, direct lookup (no algorithms)
export const CATEGORY_COLORS: Record<string, string> = {
  external:      '#F97316',   // orange — sources (cloud, APIs, file I/O)
  data:          '#22D3EE',   // cyan — transforms (data processing)
  model:         '#A78BFA',   // violet — model ops (loading, merging, inference)
  training:      '#3B82F6',   // blue — training (fine-tuning, optimization)
  metrics:       '#34D399',   // emerald — evaluation (benchmarking, scoring)
  embedding:     '#FB7185',   // rose — vectors (embedding operations)
  utilities:     '#94A3B8',   // slate — flow control (branching, looping)
  agents:        '#F43F5E',   // crimson — agents (autonomous agents)
  interventions: '#FBBF24',   // amber — gates (human-in-the-loop, quality)
  inference:     '#A3E635',   // lime — prompting, generation, LLM operations
  endpoints:     '#38BDF8',   // sky blue — endpoints (save, export, deploy)
}

// Status colors — hardcoded to avoid circular dependency with T proxy
export const STATUS_COLORS: Record<string, string> = {
  planning: '#f59e0b', active: '#4af6c3', complete: '#22c55e',
  paused: '#EAB308', failed: '#ff433d', running: '#f59e0b',
  pending: '#666666', idle: '#666666', cancelled: '#f59e0b',
}

/**
 * Injects CSS variables onto :root so that index.css can react to theme changes.
 * Call this in the App root whenever the theme changes.
 */
export function injectThemeCSSVars(mode: ThemeMode) {
  const t = mode === 'light' ? LIGHT : DARK
  const { accentColor } = useSettingsStore.getState()
  const activeAccent = (t as any)[accentColor] || t.cyan

  const root = document.documentElement
  root.style.setProperty('--bg', t.bg)
  root.style.setProperty('--text', t.text)
  root.style.setProperty('--sec', t.sec)
  root.style.setProperty('--dim', t.dim)
  root.style.setProperty('--surface0', t.surface0)
  root.style.setProperty('--surface1', t.surface1)
  root.style.setProperty('--border', t.border)
  root.style.setProperty('--cyan', activeAccent)
  root.style.setProperty('--scrollbar-thumb', mode === 'light' ? 'rgba(0,0,0,0.12)' : 'rgba(255,255,255,0.08)')
  root.style.setProperty('--scrollbar-thumb-hover', mode === 'light' ? 'rgba(0,0,0,0.22)' : 'rgba(255,255,255,0.15)')
  root.style.setProperty('--select-bg', mode === 'light' ? '#FFFFFF' : '#050505')
  root.style.setProperty('--select-color', mode === 'light' ? t.text : '#b5b5b5')
  root.style.setProperty('--shadow', t.shadow)
  root.style.setProperty('--shadow-heavy', t.shadowHeavy)
  root.style.setProperty('--shadow-light', t.shadowLight)
}
