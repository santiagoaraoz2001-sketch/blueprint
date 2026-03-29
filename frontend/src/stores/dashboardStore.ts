import { create } from 'zustand'
import { api } from '@/api/client'

// ── Types ───────────────────────────────────────────────────────────

export interface DashboardRunData {
  run_id: string
  status: string
  started_at: string | null
  duration_ms: number
  metrics: Record<string, number | string>
  config_summary: Record<string, unknown>
  starred: boolean
  tags: string[]
}

export interface DashboardExperiment {
  pipeline_id: string
  pipeline_name: string
  variant_notes: string
  source_pipeline_id: string | null
  config_diff_from_source: Record<string, { old: unknown; new: unknown }>
  runs: DashboardRunData[]
}

export interface DashboardProjectInfo {
  id: string
  name: string
  hypothesis: string | null
  status: string
}

export interface ActiveSequence {
  sequence_id: string
  status: string
  current_index: number
  total: number
  current_pipeline_name: string | null
  pipeline_names: string[]
}

export interface DashboardData {
  project: DashboardProjectInfo
  experiments: DashboardExperiment[]
  active_sequences: ActiveSequence[]
}

export interface ComparisonColumn {
  experiment_name: string
  run_id: string
  values: Record<string, unknown>
}

export interface DiffCell {
  row_key: string
  col_idx: number
  is_different: boolean
}

export interface ComparisonMatrixData {
  columns: ComparisonColumn[]
  diff_cells: DiffCell[]
  row_keys: string[]
  sections: { config: string[]; metrics: string[] }
  available_config_keys: string[]
  available_metric_keys: string[]
}

export type MetricsLogData = Record<string, { step: number; [key: string]: number }[]>

interface DashboardState {
  dashboard: DashboardData | null
  matrix: ComparisonMatrixData | null
  metricsLog: MetricsLogData
  selectedRunIds: string[]
  loading: boolean
  error: string | null

  fetchDashboard: (projectId: string) => Promise<void>
  fetchComparisonMatrix: (projectId: string, runIds?: string[], configKeys?: string[], metricKeys?: string[]) => Promise<void>
  fetchMetricsLogs: (runIds: string[]) => Promise<void>
  toggleRunSelection: (runId: string) => void
  setSelectedRunIds: (ids: string[]) => void
  toggleStar: (runId: string, projectId: string) => Promise<void>
  startSequentialRun: (projectId: string, pipelineIds: string[]) => Promise<void>
  reset: () => void
}

// ── Store ───────────────────────────────────────────────────────────

export const useDashboardStore = create<DashboardState>((set, get) => ({
  dashboard: null,
  matrix: null,
  metricsLog: {},
  selectedRunIds: [],
  loading: false,
  error: null,

  fetchDashboard: async (projectId) => {
    set({ loading: true, error: null })
    try {
      const data = await api.get<DashboardData>(`/projects/${projectId}/dashboard`)
      set({ dashboard: data, loading: false })
    } catch (e: unknown) {
      set({ error: e instanceof Error ? e.message : 'Failed to fetch dashboard', loading: false })
    }
  },

  fetchComparisonMatrix: async (projectId, runIds, configKeys, metricKeys) => {
    try {
      const params = new URLSearchParams()
      if (runIds?.length) params.set('run_ids', runIds.join(','))
      if (configKeys?.length) params.set('config_keys', configKeys.join(','))
      if (metricKeys?.length) params.set('metric_keys', metricKeys.join(','))
      const qs = params.toString()
      const url = `/projects/${projectId}/comparison-matrix${qs ? `?${qs}` : ''}`
      const data = await api.get<ComparisonMatrixData>(url)
      set({ matrix: data })
    } catch (e: unknown) {
      console.error('Failed to fetch comparison matrix:', e)
    }
  },

  fetchMetricsLogs: async (runIds) => {
    if (!runIds.length) {
      set({ metricsLog: {} })
      return
    }
    try {
      const data = await api.post<MetricsLogData>('/runs/batch-metrics-log', { run_ids: runIds })
      set({ metricsLog: data || {} })
    } catch (e: unknown) {
      console.error('Failed to fetch metrics logs:', e)
    }
  },

  toggleStar: async (runId, _projectId) => {
    try {
      const res = await api.post<{ run_id: string; starred: boolean }>(`/runs/${runId}/star`)
      // Optimistic update: update the dashboard in-memory
      set((s) => {
        if (!s.dashboard) return {}
        return {
          dashboard: {
            ...s.dashboard,
            experiments: s.dashboard.experiments.map((exp) => ({
              ...exp,
              runs: exp.runs.map((r) =>
                r.run_id === runId ? { ...r, starred: res.starred } : r
              ),
            })),
          },
        }
      })
    } catch (e: unknown) {
      console.error('Failed to toggle star:', e)
    }
  },

  toggleRunSelection: (runId) => {
    set((s) => {
      const ids = s.selectedRunIds.includes(runId)
        ? s.selectedRunIds.filter((id) => id !== runId)
        : [...s.selectedRunIds, runId]
      return { selectedRunIds: ids }
    })
  },

  setSelectedRunIds: (ids) => set({ selectedRunIds: ids }),

  startSequentialRun: async (projectId, pipelineIds) => {
    try {
      await api.post(`/projects/${projectId}/sequential-run`, { pipeline_ids: pipelineIds })
      // Refresh dashboard to show sequence progress
      get().fetchDashboard(projectId)
    } catch (e: unknown) {
      set({ error: e instanceof Error ? e.message : 'Failed to start sequential run' })
    }
  },

  reset: () => set({
    dashboard: null,
    matrix: null,
    metricsLog: {},
    selectedRunIds: [],
    loading: false,
    error: null,
  }),
}))
