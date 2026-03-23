import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api } from '@/api/client'

export type ThemeMode = 'dark' | 'light'
export type FontChoice = 'jetbrains' | 'inter' | 'fira' | 'ibm-plex'
export type FontSizeScale = 'compact' | 'default' | 'comfortable' | 'large'
export type AccentColor = 'cyan' | 'orange' | 'green' | 'blue' | 'purple' | 'pink'
export type UiMode = 'simple' | 'professional'

export interface PanelLayoutEntry {
  panelId: string
  order: number
  width: number   // grid units
  height: number  // grid units
  visible: boolean
  config: Record<string, unknown>
}

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

export interface FeatureFlags {
  marketplace: boolean
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
  features: FeatureFlags | null

  // Plugin panel layouts
  panelLayouts: Record<string, PanelLayoutEntry>

  // UI mode
  uiMode: UiMode
  hasSeenWelcome: boolean

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
  fetchFeatures: () => Promise<void>

  setPanelLayout: (panelId: string, entry: Partial<PanelLayoutEntry>) => void
  removePanelLayout: (panelId: string) => void

  setUiMode: (mode: UiMode) => void
  setHasSeenWelcome: (seen: boolean) => void

  setAudioAlertsEnabled: (enabled: boolean) => void
  setAudioVolume: (volume: number) => void
  setAudioOnStepComplete: (enabled: boolean) => void
  setAudioOnPipelineComplete: (enabled: boolean) => void
  setAudioOnError: (enabled: boolean) => void
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      theme: 'dark' as ThemeMode,
      accentColor: 'cyan' as AccentColor,
      font: 'jetbrains' as FontChoice,
      fontSize: 'default' as FontSizeScale,
      demoMode: false,
      autoSaveInterval: 5000,
      apiKeys: {} as Record<string, string>,
      hardware: null,
      hardwareLoading: false,
      features: null,

      panelLayouts: {} as Record<string, PanelLayoutEntry>,

      uiMode: 'simple' as UiMode,
      hasSeenWelcome: false,

      audioAlertsEnabled: false,
      audioVolume: 0.5,
      audioOnStepComplete: true,
      audioOnPipelineComplete: true,
      audioOnError: true,

      setTheme: (theme) => set({ theme }),
      setAccentColor: (accentColor) => set({ accentColor }),
      setFont: (font) => set({ font }),
      setFontSize: (fontSize) => set({ fontSize }),
      setDemoMode: (demoMode) => set({ demoMode }),
      setAutoSaveInterval: (autoSaveInterval) => set({ autoSaveInterval }),
      setApiKey: (provider, key) => {
        const apiKeys = { ...get().apiKeys, [provider]: key }
        set({ apiKeys })
      },
      getApiKey: (provider) => {
        return get().apiKeys[provider] ?? ''
      },
      fetchFeatures: async () => {
        try {
          const data = await api.get<FeatureFlags>('/system/features')
          set({ features: data })
        } catch {
          // Default to all features disabled if fetch fails
          set({ features: { marketplace: false } })
        }
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

      setPanelLayout: (panelId, entry) => {
        const layouts = { ...get().panelLayouts }
        layouts[panelId] = { ...layouts[panelId], ...entry } as PanelLayoutEntry
        set({ panelLayouts: layouts })
      },
      removePanelLayout: (panelId) => {
        const layouts = { ...get().panelLayouts }
        delete layouts[panelId]
        set({ panelLayouts: layouts })
      },

      setUiMode: (uiMode) => set({ uiMode }),
      setHasSeenWelcome: (hasSeenWelcome) => set({ hasSeenWelcome }),

      setAudioAlertsEnabled: (enabled) => set({ audioAlertsEnabled: enabled }),
      setAudioVolume: (volume) => set({ audioVolume: volume }),
      setAudioOnStepComplete: (enabled) => set({ audioOnStepComplete: enabled }),
      setAudioOnPipelineComplete: (enabled) => set({ audioOnPipelineComplete: enabled }),
      setAudioOnError: (enabled) => set({ audioOnError: enabled }),
    }),
    {
      name: 'blueprint-settings',
      version: 2,
      partialize: (state) => ({
        theme: state.theme,
        accentColor: state.accentColor,
        font: state.font,
        fontSize: state.fontSize,
        demoMode: state.demoMode,
        autoSaveInterval: state.autoSaveInterval,
        apiKeys: state.apiKeys,
        panelLayouts: state.panelLayouts,
        uiMode: state.uiMode,
        hasSeenWelcome: state.hasSeenWelcome,
        audioAlertsEnabled: state.audioAlertsEnabled,
        audioVolume: state.audioVolume,
        audioOnStepComplete: state.audioOnStepComplete,
        audioOnPipelineComplete: state.audioOnPipelineComplete,
        audioOnError: state.audioOnError,
      }),
      migrate: (persisted, version) => {
        // Backward compat: read from old per-key localStorage if no persisted state yet
        if (!persisted || version === 0) {
          const load = <T,>(key: string, fallback: T): T => {
            try {
              const stored = localStorage.getItem(`blueprint_${key}`)
              return stored ? JSON.parse(stored) : fallback
            } catch {
              return fallback
            }
          }
          return {
            theme: load<ThemeMode>('theme', 'dark'),
            accentColor: load<AccentColor>('accentColor', 'cyan'),
            font: load<FontChoice>('font', 'jetbrains'),
            fontSize: load<FontSizeScale>('fontSize', 'default'),
            demoMode: load<boolean>('demoMode', false),
            autoSaveInterval: load<number>('autoSaveInterval', 5000),
            apiKeys: load<Record<string, string>>('apiKeys', {}),
            panelLayouts: load<Record<string, PanelLayoutEntry>>('panelLayouts', {}),
            uiMode: 'simple' as UiMode,
            hasSeenWelcome: false,
            audioAlertsEnabled: load<boolean>('audioAlertsEnabled', false),
            audioVolume: load<number>('audioVolume', 0.5),
            audioOnStepComplete: load<boolean>('audioOnStepComplete', true),
            audioOnPipelineComplete: load<boolean>('audioOnPipelineComplete', true),
            audioOnError: load<boolean>('audioOnError', true),
          }
        }
        if (version === 1) {
          return {
            ...(persisted as Record<string, unknown>),
            panelLayouts: {},
            uiMode: 'simple' as UiMode,
            hasSeenWelcome: false,
          }
        }
        return persisted as Record<string, unknown>
      },
    }
  )
)
