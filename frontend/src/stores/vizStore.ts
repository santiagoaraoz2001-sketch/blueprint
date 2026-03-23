import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type ChartType = 'bar' | 'line' | 'area' | 'scatter' | 'heatmap' | 'box' | 'histogram' | 'radar' | 'treemap'

export interface ChartStyle {
  colorScheme: string
  showLegend: boolean
  showGrid: boolean
}

export interface ChartLayout {
  x: number
  y: number
  w: number
  h: number
}

export interface ChartPanel {
  id: string
  title: string
  chartType: ChartType
  dataTableId: string
  xField: string
  yField: string
  colorField?: string
  style: ChartStyle
  layout: ChartLayout
}

export interface Dashboard {
  id: string
  name: string
  panels: ChartPanel[]
}

let idCounter = 0
function nextId(prefix: string) {
  return `${prefix}_${++idCounter}_${Date.now()}`
}

interface VizState {
  dashboards: Dashboard[]
  activeDashboardId: string | null

  // Actions
  createDashboard: (name: string) => string
  deleteDashboard: (id: string) => void
  renameDashboard: (id: string, name: string) => void
  setActiveDashboard: (id: string | null) => void
  getActiveDashboard: () => Dashboard | null

  addPanel: (dashboardId: string, panel: Omit<ChartPanel, 'id'>) => string
  updatePanel: (dashboardId: string, panelId: string, updates: Partial<ChartPanel>) => void
  removePanel: (dashboardId: string, panelId: string) => void
  updatePanelLayout: (dashboardId: string, panelId: string, layout: ChartLayout) => void
}

// Default demo dashboard
const DEMO_DASHBOARD: Dashboard = {
  id: 'demo-dashboard',
  name: 'ML Experiment Results',
  panels: [
    {
      id: 'demo-panel-1',
      title: 'Model Accuracy Comparison',
      chartType: 'bar',
      dataTableId: 'demo-ml-experiments',
      xField: 'model',
      yField: 'accuracy',
      style: { colorScheme: 'default', showLegend: true, showGrid: true },
      layout: { x: 0, y: 0, w: 6, h: 4 },
    },
    {
      id: 'demo-panel-2',
      title: 'Training Loss Over Epochs',
      chartType: 'line',
      dataTableId: 'demo-ml-experiments',
      xField: 'model',
      yField: 'loss',
      style: { colorScheme: 'default', showLegend: true, showGrid: true },
      layout: { x: 6, y: 0, w: 6, h: 4 },
    },
    {
      id: 'demo-panel-3',
      title: 'Accuracy vs F1 Score',
      chartType: 'scatter',
      dataTableId: 'demo-ml-experiments',
      xField: 'accuracy',
      yField: 'f1_score',
      colorField: 'model',
      style: { colorScheme: 'default', showLegend: true, showGrid: true },
      layout: { x: 0, y: 4, w: 12, h: 4 },
    },
  ],
}

export const useVizStore = create<VizState>()(
  persist(
    (set, get) => ({
      dashboards: [DEMO_DASHBOARD],
      activeDashboardId: 'demo-dashboard',

      createDashboard: (name) => {
        const id = nextId('dash')
        set((s) => ({
          dashboards: [...s.dashboards, { id, name, panels: [] }],
          activeDashboardId: id,
        }))
        return id
      },

      deleteDashboard: (id) => {
        set((s) => ({
          dashboards: s.dashboards.filter((d) => d.id !== id),
          activeDashboardId: s.activeDashboardId === id ? (s.dashboards[0]?.id || null) : s.activeDashboardId,
        }))
      },

      renameDashboard: (id, name) => {
        set((s) => ({
          dashboards: s.dashboards.map((d) => (d.id === id ? { ...d, name } : d)),
        }))
      },

      setActiveDashboard: (id) => set({ activeDashboardId: id }),

      getActiveDashboard: () => {
        const { dashboards, activeDashboardId } = get()
        return dashboards.find((d) => d.id === activeDashboardId) || null
      },

      addPanel: (dashboardId, panel) => {
        const id = nextId('panel')
        set((s) => ({
          dashboards: s.dashboards.map((d) => {
            if (d.id !== dashboardId) return d
            return { ...d, panels: [...d.panels, { ...panel, id }] }
          }),
        }))
        return id
      },

      updatePanel: (dashboardId, panelId, updates) => {
        set((s) => ({
          dashboards: s.dashboards.map((d) => {
            if (d.id !== dashboardId) return d
            return {
              ...d,
              panels: d.panels.map((p) => (p.id === panelId ? { ...p, ...updates } : p)),
            }
          }),
        }))
      },

      removePanel: (dashboardId, panelId) => {
        set((s) => ({
          dashboards: s.dashboards.map((d) => {
            if (d.id !== dashboardId) return d
            return { ...d, panels: d.panels.filter((p) => p.id !== panelId) }
          }),
        }))
      },

      updatePanelLayout: (dashboardId, panelId, layout) => {
        set((s) => ({
          dashboards: s.dashboards.map((d) => {
            if (d.id !== dashboardId) return d
            return {
              ...d,
              panels: d.panels.map((p) => (p.id === panelId ? { ...p, layout } : p)),
            }
          }),
        }))
      },
    }),
    {
      name: 'blueprint-viz-storage',
    }
  )
)
