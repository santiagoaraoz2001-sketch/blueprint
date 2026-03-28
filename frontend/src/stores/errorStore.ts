/**
 * errorStore — centralized store for pipeline errors, system warnings,
 * and capability-based block availability.
 */

import { create } from 'zustand'
import { api } from '@/api/client'

export type ErrorSeverity = 'error' | 'warning' | 'info'

export interface PipelineError {
  id: string
  nodeId?: string
  nodeName?: string
  title: string
  message: string
  action?: string
  severity: ErrorSeverity
  details?: string
  /** Recovery action type for one-click fix */
  recoveryType?: 'start_service' | 'open_config' | 'suggest_connection' | 'clear_cache'
  recoveryPayload?: Record<string, string>
  timestamp: number
}

export interface BlockAvailability {
  available: boolean
  missing: string[]
}

export interface CapabilityReport {
  capabilities: Record<string, boolean>
  platform: {
    os: string
    arch: string
    python_version: string
    gpu_name: string | null
    gpu_backend: string
  }
  installed_profile: 'base' | 'inference' | 'training' | 'full'
}

interface ErrorStore {
  /** Active pipeline/system errors */
  errors: PipelineError[]
  /** Per-block availability from capability detection */
  blockAvailability: Record<string, BlockAvailability>
  /** Full capability report */
  capabilityReport: CapabilityReport | null
  /** System banners (e.g. "Ollama not running") */
  systemBanners: PipelineError[]
  /** Whether the error panel is open */
  panelOpen: boolean

  // Actions
  addError: (error: Omit<PipelineError, 'id' | 'timestamp'>) => void
  removeError: (id: string) => void
  clearErrors: () => void
  clearNodeErrors: (nodeId: string) => void
  setPanelOpen: (open: boolean) => void
  togglePanel: () => void

  addSystemBanner: (banner: Omit<PipelineError, 'id' | 'timestamp'>) => void
  dismissBanner: (id: string) => void

  fetchCapabilities: () => Promise<void>
  fetchBlockAvailability: () => Promise<void>
}

let _nextId = 0

export const useErrorStore = create<ErrorStore>((set, get) => ({
  errors: [],
  blockAvailability: {},
  capabilityReport: null,
  systemBanners: [],
  panelOpen: false,

  addError: (error) => {
    const id = `err-${++_nextId}`
    set((s) => ({
      errors: [...s.errors, { ...error, id, timestamp: Date.now() }],
    }))
  },

  removeError: (id) => {
    set((s) => ({ errors: s.errors.filter((e) => e.id !== id) }))
  },

  clearErrors: () => set({ errors: [] }),

  clearNodeErrors: (nodeId) => {
    set((s) => ({ errors: s.errors.filter((e) => e.nodeId !== nodeId) }))
  },

  setPanelOpen: (open) => set({ panelOpen: open }),
  togglePanel: () => set((s) => ({ panelOpen: !s.panelOpen })),

  addSystemBanner: (banner) => {
    const id = `banner-${++_nextId}`
    set((s) => ({
      systemBanners: [...s.systemBanners, { ...banner, id, timestamp: Date.now() }],
    }))
  },

  dismissBanner: (id) => {
    set((s) => ({ systemBanners: s.systemBanners.filter((b) => b.id !== id) }))
  },

  fetchCapabilities: async () => {
    try {
      const report = await api.get<CapabilityReport>('/system/capabilities/detailed')
      set({ capabilityReport: report })

      // Auto-generate system banners for missing services
      const caps = report.capabilities
      const { systemBanners } = get()

      // Ollama not running
      if (!caps.ollama && !systemBanners.some((b) => b.title === 'Ollama Not Running')) {
        get().addSystemBanner({
          title: 'Ollama Not Running',
          message: 'Local LLM inference requires Ollama. Start it to enable inference blocks.',
          action: 'Start Ollama',
          severity: 'warning',
          recoveryType: 'start_service',
          recoveryPayload: { name: 'ollama' },
        })
      }
    } catch {
      // Non-critical — capabilities are a convenience feature
    }
  },

  fetchBlockAvailability: async () => {
    try {
      const blocks = await api.get<Array<{ type: string; availability?: BlockAvailability }>>(
        '/registry/blocks?include_availability=true'
      )
      const availability: Record<string, BlockAvailability> = {}
      for (const block of blocks) {
        if (block.availability) {
          availability[block.type] = block.availability
        }
      }
      set({ blockAvailability: availability })
    } catch {
      // Non-critical
    }
  },
}))
