import { create } from 'zustand'

export interface ConfigPreset {
  id: string
  blockType: string
  name: string
  description: string
  config: Record<string, any>
  createdAt: string
  isPublished: boolean
}

const STORAGE_KEY = 'blueprint-config-presets'

function loadPresets(): ConfigPreset[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function savePresets(presets: ConfigPreset[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(presets))
}

interface PresetState {
  presets: ConfigPreset[]
  savePreset: (blockType: string, name: string, description: string, config: Record<string, any>) => void
  deletePreset: (id: string) => void
  publishPreset: (id: string) => void
  unpublishPreset: (id: string) => void
  getPresetsForBlock: (blockType: string) => ConfigPreset[]
}

export const usePresetStore = create<PresetState>((set, get) => ({
  presets: loadPresets(),

  savePreset: (blockType, name, description, config) => {
    const preset: ConfigPreset = {
      id: `preset-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      blockType,
      name,
      description,
      config: { ...config },
      createdAt: new Date().toISOString(),
      isPublished: false,
    }
    const updated = [...get().presets, preset]
    savePresets(updated)
    set({ presets: updated })
  },

  deletePreset: (id) => {
    const updated = get().presets.filter((p) => p.id !== id)
    savePresets(updated)
    set({ presets: updated })
  },

  publishPreset: (id) => {
    const updated = get().presets.map((p) => (p.id === id ? { ...p, isPublished: true } : p))
    savePresets(updated)
    set({ presets: updated })
  },

  unpublishPreset: (id) => {
    const updated = get().presets.map((p) => (p.id === id ? { ...p, isPublished: false } : p))
    savePresets(updated)
    set({ presets: updated })
  },

  getPresetsForBlock: (blockType) => {
    return get().presets.filter((p) => p.blockType === blockType)
  },
}))
