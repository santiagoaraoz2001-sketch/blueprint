import { create } from 'zustand'

export type View = 'dashboard' | 'editor' | 'results' | 'datasets' | 'data' | 'visualization' | 'marketplace' | 'settings' | 'paper' | 'help' | 'workshop' | 'inference' | 'monitor' | 'paper-detail'

interface UIState {
  activeView: View
  sidebarCollapsed: boolean
  selectedProjectId: string | null
  selectedPipelineId: string | null
  /** The run ID to display in MonitorView */
  selectedRunId: string | null
  /** Navigation parameter for paper-detail view */
  selectedPaperProjectId: string | null
  setView: (view: View) => void
  toggleSidebar: () => void
  setSelectedProject: (id: string | null) => void
  setSelectedPipeline: (id: string | null) => void
  setSelectedRunId: (id: string | null) => void
  /** Navigate to the monitor view for a specific run */
  navigateToMonitor: (runId?: string | null) => void
  /** Navigate to the paper detail view for a project */
  navigateToPaperDetail: (projectId: string) => void
}

export const useUIStore = create<UIState>((set) => ({
  activeView: 'dashboard',
  sidebarCollapsed: false,
  selectedProjectId: null,
  selectedPipelineId: null,
  selectedRunId: null,
  selectedPaperProjectId: null,
  setView: (view) => set({ activeView: view }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setSelectedProject: (id) => set({ selectedProjectId: id }),
  setSelectedPipeline: (id) => set({ selectedPipelineId: id }),
  setSelectedRunId: (id) => set({ selectedRunId: id }),
  navigateToMonitor: (runId) => set({ activeView: 'monitor', selectedRunId: runId ?? null }),
  navigateToPaperDetail: (projectId) => set({ activeView: 'paper-detail', selectedPaperProjectId: projectId }),
}))
