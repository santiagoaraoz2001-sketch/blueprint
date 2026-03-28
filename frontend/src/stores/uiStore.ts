import { create } from 'zustand'

export type View = 'dashboard' | 'editor' | 'results' | 'datasets' | 'data' | 'visualization' | 'marketplace' | 'settings' | 'paper' | 'help' | 'workshop' | 'inference' | 'research' | 'research-detail' | 'monitor' | 'output' | 'experiment-dashboard' | 'models' | 'project'

interface UIState {
  activeView: View
  sidebarCollapsed: boolean
  selectedProjectId: string | null
  selectedPipelineId: string | null
  /** The run ID to display in MonitorView */
  selectedRunId: string | null
  /** Navigation parameter for paper-detail view */
  selectedPaperProjectId: string | null
  monitorRunId: string | null
  compareRunIds: string[] | null
  /** Whether the contextual help panel is open */
  helpPanelOpen: boolean
  setView: (view: View) => void
  toggleSidebar: () => void
  setSelectedProject: (id: string | null) => void
  setSelectedPipeline: (id: string | null) => void
  setSelectedRunId: (id: string | null) => void
  /** Navigate to the monitor view for a specific run */
  navigateToMonitor: (runId?: string | null) => void
  /** Navigate to the paper detail view for a project */
  navigateToPaperDetail: (projectId: string) => void
  setMonitorRunId: (id: string | null) => void
  setCompareRunIds: (ids: string[] | null) => void
  openMonitor: (runId: string) => void
  openComparison: (runIds: string[]) => void
  toggleHelpPanel: () => void
}

export const useUIStore = create<UIState>((set) => ({
  activeView: 'research',
  sidebarCollapsed: false,
  selectedProjectId: null,
  selectedPipelineId: null,
  selectedRunId: null,
  selectedPaperProjectId: null,
  monitorRunId: null,
  compareRunIds: null,
  helpPanelOpen: false,
  setView: (view) => set({ activeView: view }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setSelectedProject: (id) => set({ selectedProjectId: id }),
  setSelectedPipeline: (id) => set({ selectedPipelineId: id }),
  setSelectedRunId: (id) => set({ selectedRunId: id }),
  navigateToMonitor: (runId) => set({ activeView: 'monitor', selectedRunId: runId ?? null }),
  navigateToPaperDetail: (projectId) => set({ activeView: 'research-detail', selectedProjectId: projectId, selectedPaperProjectId: projectId }),
  setMonitorRunId: (id) => set({ monitorRunId: id }),
  setCompareRunIds: (ids) => set({ compareRunIds: ids }),
  openMonitor: (runId) => set({ activeView: 'monitor', monitorRunId: runId, compareRunIds: null }),
  openComparison: (runIds) => set({ activeView: 'monitor', compareRunIds: runIds, monitorRunId: null }),
  toggleHelpPanel: () => set((s) => ({ helpPanelOpen: !s.helpPanelOpen })),
}))
