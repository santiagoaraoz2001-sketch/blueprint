import { create } from 'zustand'

export interface ConfigPreset {
  id: string
  blockType: string
  name: string
  description: string
  config: Record<string, any>
  createdAt: string
  isPublished: boolean
  builtin?: boolean
}

const STORAGE_KEY = 'blueprint-config-presets'

function loadLocalPresets(): ConfigPreset[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveLocalPresets(presets: ConfigPreset[]) {
  // Only cache non-builtin presets locally
  const userPresets = presets.filter(p => !p.builtin)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(userPresets))
}

interface PresetState {
  presets: ConfigPreset[]
  loaded: boolean
  savePreset: (blockType: string, name: string, description: string, config: Record<string, any>) => void
  deletePreset: (id: string) => void
  publishPreset: (id: string) => void
  unpublishPreset: (id: string) => void
  getPresetsForBlock: (blockType: string) => ConfigPreset[]
  fetchPresets: (blockType?: string) => Promise<void>
}

/** Parse a backend preset response into our ConfigPreset shape */
function parseApiPreset(raw: any): ConfigPreset {
  const config = typeof raw.config_json === 'string'
    ? JSON.parse(raw.config_json)
    : raw.config_json || {}
  return {
    id: String(raw.id),
    blockType: raw.block_type,
    name: raw.name,
    description: '',
    config,
    createdAt: raw.created_at || new Date().toISOString(),
    isPublished: false,
    builtin: raw.builtin || false,
  }
}

export const usePresetStore = create<PresetState>((set, get) => ({
  presets: loadLocalPresets(),
  loaded: false,

  fetchPresets: async (blockType?: string) => {
    try {
      const url = blockType
        ? `/api/presets?block_type=${encodeURIComponent(blockType)}`
        : '/api/presets'
      const resp = await fetch(url)
      if (!resp.ok) return
      const data = await resp.json()
      if (!Array.isArray(data)) return

      const apiPresets = data.map(parseApiPreset)

      // Merge: API presets take precedence, keep any local-only presets as fallback
      const apiIds = new Set(apiPresets.map(p => p.id))
      const localOnly = get().presets.filter(p => !apiIds.has(p.id) && !p.builtin)
      const merged = [...apiPresets, ...localOnly]

      saveLocalPresets(merged)
      set({ presets: merged, loaded: true })
    } catch {
      // Silently fall back to local presets
      if (!get().loaded) {
        set({ loaded: true })
      }
    }
  },

  savePreset: async (blockType, name, description, config) => {
    // Save to backend API
    try {
      const resp = await fetch('/api/presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          block_type: blockType,
          name,
          config_json: JSON.stringify(config),
        }),
      })
      if (resp.ok) {
        const data = await resp.json()
        const preset = parseApiPreset(data)
        const updated = [...get().presets, preset]
        saveLocalPresets(updated)
        set({ presets: updated })
        return
      }
    } catch { /* fall through to local save */ }

    // Fallback: save locally
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
    saveLocalPresets(updated)
    set({ presets: updated })
  },

  deletePreset: async (id) => {
    // Try backend first
    try {
      const resp = await fetch(`/api/presets/${id}`, { method: 'DELETE' })
      if (resp.ok || resp.status === 404) {
        // Success or already gone
      }
    } catch { /* ignore */ }

    const updated = get().presets.filter((p) => p.id !== id)
    saveLocalPresets(updated)
    set({ presets: updated })
  },

  publishPreset: (id) => {
    const updated = get().presets.map((p) => (p.id === id ? { ...p, isPublished: true } : p))
    saveLocalPresets(updated)
    set({ presets: updated })
  },

  unpublishPreset: (id) => {
    const updated = get().presets.map((p) => (p.id === id ? { ...p, isPublished: false } : p))
    saveLocalPresets(updated)
    set({ presets: updated })
  },

  getPresetsForBlock: (blockType) => {
    return get().presets.filter((p) => p.blockType === blockType)
  },
}))
