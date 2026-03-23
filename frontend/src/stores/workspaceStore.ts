import { create } from 'zustand'
import { api } from '@/api/client'

interface WorkspaceSettings {
  root_path: string | null
  auto_fill_paths: boolean
  watcher_enabled: boolean
}

interface WorkspaceStatus {
  root_path: string | null
  watcher_running: boolean
  folder_health: Record<string, boolean>
  inbox_count: number
}

interface WorkspaceState {
  settings: WorkspaceSettings
  status: WorkspaceStatus | null
  paths: Record<string, string>
  autoFillEnabled: boolean
  loading: boolean

  fetchSettings: () => Promise<void>
  updateSettings: (update: Partial<WorkspaceSettings>) => Promise<void>
  fetchStatus: () => Promise<void>
  fetchPaths: () => Promise<void>
  openInFinder: () => Promise<void>
  initialize: () => Promise<void>
}

export const useWorkspaceStore = create<WorkspaceState>()((set, get) => ({
  settings: { root_path: null, auto_fill_paths: true, watcher_enabled: true },
  status: null,
  paths: {},
  autoFillEnabled: false,
  loading: false,

  fetchSettings: async () => {
    set({ loading: true })
    try {
      const data = await api.get<WorkspaceSettings>('/workspace/settings')
      set({ settings: data, loading: false })
    } catch {
      set({ loading: false })
    }
  },

  updateSettings: async (update) => {
    set({ loading: true })
    try {
      const data = await api.put<WorkspaceSettings>('/workspace/settings', update)
      set({ settings: data, loading: false })
      // Refresh paths and status after settings change
      get().fetchPaths()
      get().fetchStatus()
    } catch {
      set({ loading: false })
    }
  },

  fetchStatus: async () => {
    try {
      const data = await api.get<WorkspaceStatus>('/workspace/status')
      set({ status: data })
    } catch {
      // Non-critical
    }
  },

  fetchPaths: async () => {
    try {
      const data = await api.get<{ paths: Record<string, string>; auto_fill_paths: boolean }>('/workspace/paths')
      set({ paths: data.paths, autoFillEnabled: data.auto_fill_paths })
    } catch {
      set({ paths: {}, autoFillEnabled: false })
    }
  },

  openInFinder: async () => {
    try {
      await api.post('/workspace/open', {})
    } catch {
      // Non-critical
    }
  },

  initialize: async () => {
    try {
      await api.post('/workspace/initialize', {})
      get().fetchStatus()
    } catch {
      // Non-critical
    }
  },
}))
