import { create } from 'zustand'
import { api } from '@/api/client'
import { useSettingsStore } from './settingsStore'

interface GpuInfo {
  name: string
  vram_gb: number
  type: string // 'metal' | 'cuda' | 'rocm' | 'unknown'
}

interface HardwareProfile {
  cpu: { cores: number; threads: number; freq_mhz: number; arch: string; brand: string }
  ram: { total_gb: number; available_gb: number }
  gpu: GpuInfo[]
  disk: { free_gb: number }
  accelerators: { mlx: boolean; cuda: boolean; mps: boolean; coreml: boolean }
}

interface HardwareState {
  profile: HardwareProfile | null
  loading: boolean
  error: string | null
  fetchHardware: () => Promise<void>
}

// Demo hardware profile for offline / demo mode
const DEMO_PROFILE: HardwareProfile = {
  cpu: { cores: 10, threads: 10, freq_mhz: 3228, arch: 'arm64', brand: 'Apple M3 Pro' },
  ram: { total_gb: 36, available_gb: 18 },
  gpu: [{ name: 'Apple M3 Pro', vram_gb: 36, type: 'metal' }],
  disk: { free_gb: 245 },
  accelerators: { mlx: true, cuda: false, mps: true, coreml: true },
}

export const useHardwareStore = create<HardwareState>((set) => ({
  profile: null,
  loading: false,
  error: null,

  fetchHardware: async () => {
    set({ loading: true })

    if (useSettingsStore.getState().demoMode) {
      set({ profile: DEMO_PROFILE, loading: false, error: null })
      return
    }

    try {
      const data = await api.get<HardwareProfile>('/system/hardware')
      set({ profile: data, loading: false, error: null })
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to detect hardware'
      set({ loading: false, error: msg })
    }
  },
}))
