import { create } from 'zustand'
import { api } from '@/api/client'

export type ThemeMode = 'dark' | 'light'
export type FontChoice = 'jetbrains' | 'inter' | 'fira' | 'ibm-plex'
export type FontSizeScale = 'compact' | 'default' | 'comfortable' | 'large'
export type AccentColor = 'cyan' | 'orange' | 'green' | 'blue' | 'purple' | 'pink'

export const FONT_SIZE_SCALES: Record<FontSizeScale, number> = {
  compact: 0.85,
  default: 1.0,
  comfortable: 1.15,
  large: 1.3,
}

export const FONT_SIZE_LABELS: Record<FontSizeScale, string> = {
  compact: 'Compact',
  default: 'Default',
  comfortable: 'Comfortable',
  large: 'Large',
}

export const FONT_MAP: Record<FontChoice, string> = {
  jetbrains: "'JetBrains Mono','SF Mono','Fira Code',monospace",
  inter: "'Inter','Helvetica Neue',Arial,sans-serif",
  fira: "'Fira Code','JetBrains Mono','SF Mono',monospace",
  'ibm-plex': "'IBM Plex Mono','JetBrains Mono','SF Mono',monospace",
}

export const FONT_LABELS: Record<FontChoice, string> = {
  jetbrains: 'JetBrains Mono',
  inter: 'Inter',
  fira: 'Fira Code',
  'ibm-plex': 'IBM Plex Mono',
}

export interface HardwareCapabilities {
  gpu_available: boolean
  gpu_backend: string
  max_vram_gb: number
  usable_memory_gb: number
  max_model_size: string
  can_fine_tune: boolean
  can_run_local_llm: boolean
  disk_ok: boolean
  accelerators: Record<string, boolean>
}

interface SettingsState {
  theme: ThemeMode
  accentColor: AccentColor
  font: FontChoice
  fontSize: FontSizeScale
  demoMode: boolean
  autoSaveInterval: number
  apiKeys: Record<string, string>
  hardware: HardwareCapabilities | null
  hardwareLoading: boolean

  // Audio alerts
  audioAlertsEnabled: boolean
  audioVolume: number
  audioOnStepComplete: boolean
  audioOnPipelineComplete: boolean
  audioOnError: boolean

  setTheme: (theme: ThemeMode) => void
  setAccentColor: (color: AccentColor) => void
  setFont: (font: FontChoice) => void
  setFontSize: (size: FontSizeScale) => void
  setDemoMode: (enabled: boolean) => void
  setAutoSaveInterval: (ms: number) => void
  setApiKey: (provider: string, key: string) => void
  getApiKey: (provider: string) => string
  fetchHardware: () => Promise<void>

  setAudioAlertsEnabled: (enabled: boolean) => void
  setAudioVolume: (volume: number) => void
  setAudioOnStepComplete: (enabled: boolean) => void
  setAudioOnPipelineComplete: (enabled: boolean) => void
  setAudioOnError: (enabled: boolean) => void
}

function loadFromStorage<T>(key: string, fallback: T): T {
  try {
    const stored = localStorage.getItem(`blueprint_${key}`)
    return stored ? JSON.parse(stored) : fallback
  } catch {
    return fallback
  }
}

function saveToStorage(key: string, value: unknown) {
  localStorage.setItem(`blueprint_${key}`, JSON.stringify(value))
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  theme: loadFromStorage<ThemeMode>('theme', 'dark'),
  accentColor: loadFromStorage<AccentColor>('accentColor', 'cyan'),
  font: loadFromStorage<FontChoice>('font', 'jetbrains'),
  fontSize: loadFromStorage<FontSizeScale>('fontSize', 'default'),
  demoMode: loadFromStorage<boolean>('demoMode', false),
  autoSaveInterval: loadFromStorage<number>('autoSaveInterval', 5000),
  apiKeys: loadFromStorage<Record<string, string>>('apiKeys', {}),
  hardware: null,
  hardwareLoading: false,

  audioAlertsEnabled: loadFromStorage<boolean>('audioAlertsEnabled', false),
  audioVolume: loadFromStorage<number>('audioVolume', 0.5),
  audioOnStepComplete: loadFromStorage<boolean>('audioOnStepComplete', true),
  audioOnPipelineComplete: loadFromStorage<boolean>('audioOnPipelineComplete', true),
  audioOnError: loadFromStorage<boolean>('audioOnError', true),

  setTheme: (theme) => {
    saveToStorage('theme', theme)
    set({ theme })
  },
  setAccentColor: (accentColor) => {
    saveToStorage('accentColor', accentColor)
    set({ accentColor })
  },
  setFont: (font) => {
    saveToStorage('font', font)
    set({ font })
  },
  setFontSize: (fontSize) => {
    saveToStorage('fontSize', fontSize)
    set({ fontSize })
  },
  setDemoMode: (demoMode) => {
    saveToStorage('demoMode', demoMode)
    set({ demoMode })
  },
  setAutoSaveInterval: (autoSaveInterval) => {
    saveToStorage('autoSaveInterval', autoSaveInterval)
    set({ autoSaveInterval })
  },
  setApiKey: (provider, key) => {
    const apiKeys = { ...get().apiKeys, [provider]: key }
    saveToStorage('apiKeys', apiKeys)
    set({ apiKeys })
  },
  getApiKey: (provider) => {
    return get().apiKeys[provider] ?? ''
  },
  fetchHardware: async () => {
    set({ hardwareLoading: true })
    try {
      const data = await api.get<HardwareCapabilities>('/system/capabilities')
      set({ hardware: data, hardwareLoading: false })
    } catch {
      set({ hardwareLoading: false })
    }
  },

  setAudioAlertsEnabled: (enabled) => {
    saveToStorage('audioAlertsEnabled', enabled)
    set({ audioAlertsEnabled: enabled })
  },
  setAudioVolume: (volume) => {
    saveToStorage('audioVolume', volume)
    set({ audioVolume: volume })
  },
  setAudioOnStepComplete: (enabled) => {
    saveToStorage('audioOnStepComplete', enabled)
    set({ audioOnStepComplete: enabled })
  },
  setAudioOnPipelineComplete: (enabled) => {
    saveToStorage('audioOnPipelineComplete', enabled)
    set({ audioOnPipelineComplete: enabled })
  },
  setAudioOnError: (enabled) => {
    saveToStorage('audioOnError', enabled)
    set({ audioOnError: enabled })
  },
}))
