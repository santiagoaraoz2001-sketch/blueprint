import { create } from 'zustand'

export type View = 'dashboard' | 'editor' | 'results' | 'datasets' | 'data' | 'visualization' | 'marketplace' | 'settings' | 'paper' | 'help' | 'workshop' | 'inference' | 'research' | 'research-detail'

interface UIState {
  activeView: View
  sidebarCollapsed: boolean
  selectedProjectId: string | null
  selectedPipelineId: string | null
  setView: (view: View) => void
  toggleSidebar: () => void
  setSelectedProject: (id: string | null) => void
  setSelectedPipeline: (id: string | null) => void
}

export const useUIStore = create<UIState>((set) => ({
  activeView: 'research',
  sidebarCollapsed: false,
  selectedProjectId: null,
  selectedPipelineId: null,
  setView: (view) => set({ activeView: view }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setSelectedProject: (id) => set({ selectedProjectId: id }),
  setSelectedPipeline: (id) => set({ selectedPipelineId: id }),
}))
