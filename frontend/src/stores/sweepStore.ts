import { create } from 'zustand'
import { api } from '@/api/client'
import { sseManager } from '@/services/sseManager'

export interface SweepConfig {
  [key: string]: any
}

export interface SweepResult {
  config: SweepConfig
  metric: number | null
  run_id: string
  config_index: number
  error?: string
}

export interface HeatmapData {
  x_param: string
  y_param: string
  x_values: any[]
  y_values: any[]
  grid: (number | null)[][]
  best: SweepResult | null
}

export interface SweepSummary {
  sweep_id: string
  pipeline_id: string
  target_node_id: string
  metric_name: string
  search_type: string
  status: string
  num_configs: number
  num_completed: number
  created_at: string | null
}

interface SweepState {
  // Active sweep
  activeSweepId: string | null
  status: 'idle' | 'pending' | 'running' | 'complete' | 'failed'
  configs: SweepConfig[]
  results: SweepResult[]
  heatmapData: HeatmapData | null
  progress: { total: number; completed: number; percent: number }
  error: string | null

  // Sweep list
  sweeps: SweepSummary[]

  // SSE
  _sseUnsubscribe: (() => void) | null

  // Actions
  createSweep: (params: {
    pipeline_id: string
    target_node_id: string
    metric_name: string
    search_type: 'grid' | 'random'
    ranges: Record<string, any>
    n_samples?: number
  }) => Promise<string | null>

  startSweep: (sweepId: string) => Promise<void>
  fetchResults: (sweepId: string, xParam?: string, yParam?: string) => Promise<void>
  fetchStatus: (sweepId: string) => Promise<void>
  fetchSweeps: (pipelineId?: string) => Promise<void>
  connectSSE: (sweepId: string) => void
  disconnectSSE: () => void
  reset: () => void
}

export const useSweepStore = create<SweepState>((set, get) => ({
  activeSweepId: null,
  status: 'idle',
  configs: [],
  results: [],
  heatmapData: null,
  progress: { total: 0, completed: 0, percent: 0 },
  error: null,
  sweeps: [],
  _sseUnsubscribe: null,

  createSweep: async (params) => {
    try {
      const res = await api.post<{
        sweep_id: string
        num_configs: number
        configs: SweepConfig[]
        status: string
      }>('/sweeps/create', params)

      set({
        activeSweepId: res.sweep_id,
        status: 'pending',
        configs: res.configs,
        results: [],
        heatmapData: null,
        progress: { total: res.num_configs, completed: 0, percent: 0 },
        error: null,
      })

      return res.sweep_id
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to create sweep'
      set({ error: msg })
      return null
    }
  },

  startSweep: async (sweepId: string) => {
    try {
      const res = await api.post<{
        sweep_id: string
        status: string
        num_runs: number
        run_ids: string[]
      }>(`/sweeps/${sweepId}/start`)

      set({
        activeSweepId: sweepId,
        status: 'running',
        results: [],
        progress: { total: res.num_runs, completed: 0, percent: 0 },
        error: null,
      })

      // Connect SSE for live updates
      get().connectSSE(sweepId)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to start sweep'
      set({ status: 'failed', error: msg })
    }
  },

  fetchResults: async (sweepId, xParam, yParam) => {
    try {
      let path = `/sweeps/${sweepId}/results`
      const params = new URLSearchParams()
      if (xParam) params.set('x_param', xParam)
      if (yParam) params.set('y_param', yParam)
      const qs = params.toString()
      if (qs) path += `?${qs}`

      const res = await api.get<any>(path)

      if (xParam && yParam) {
        // Heatmap response
        set({ heatmapData: res })
      } else {
        // Full results response
        set({
          results: res.results || [],
          status: res.status === 'complete' ? 'complete' : get().status,
        })
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to fetch results'
      set({ error: msg })
    }
  },

  fetchStatus: async (sweepId) => {
    try {
      const res = await api.get<{
        sweep_id: string
        status: string
        total: number
        completed: number
        pending: number
        percent: number
      }>(`/sweeps/${sweepId}/status`)

      set({
        progress: {
          total: res.total,
          completed: res.completed,
          percent: res.percent,
        },
        status: res.status as any,
      })
    } catch {
      // Ignore status fetch errors
    }
  },

  fetchSweeps: async (pipelineId) => {
    try {
      let path = '/sweeps'
      if (pipelineId) path += `?pipeline_id=${pipelineId}`
      const res = await api.get<SweepSummary[]>(path)
      set({ sweeps: res })
    } catch {
      // Ignore list fetch errors
    }
  },

  connectSSE: (sweepId: string) => {
    const { _sseUnsubscribe } = get()
    if (_sseUnsubscribe) _sseUnsubscribe()

    const unsubscribe = sseManager.subscribe(sweepId, (event, data) => {
      if (event === '__sse_stale' || event === '__sse_failed' ||
          event === '__sse_reconnecting' || event === '__sse_connected') {
        return
      }

      const state = get()

      if (event === 'sweep_run_completed') {
        const newResult: SweepResult = {
          config: data.config,
          metric: data.metric,
          run_id: data.run_id,
          config_index: data.config_index,
        }
        set({
          results: [...state.results, newResult],
          progress: {
            total: data.total,
            completed: data.completed,
            percent: data.total > 0 ? Math.round(data.completed / data.total * 100) : 0,
          },
        })
      }

      if (event === 'sweep_run_failed') {
        const failResult: SweepResult = {
          config: data.config || {},
          metric: null,
          run_id: data.run_id,
          config_index: data.config_index,
          error: data.error,
        }
        set({
          results: [...state.results, failResult],
          progress: {
            total: data.total,
            completed: data.completed,
            percent: data.total > 0 ? Math.round(data.completed / data.total * 100) : 0,
          },
        })
      }

      if (event === 'sweep_completed') {
        set({ status: 'complete' })
        get().disconnectSSE()
      }
    })

    set({ _sseUnsubscribe: unsubscribe })
  },

  disconnectSSE: () => {
    const { _sseUnsubscribe } = get()
    if (_sseUnsubscribe) _sseUnsubscribe()
    set({ _sseUnsubscribe: null })
  },

  reset: () => {
    const { _sseUnsubscribe } = get()
    if (_sseUnsubscribe) _sseUnsubscribe()
    set({
      activeSweepId: null,
      status: 'idle',
      configs: [],
      results: [],
      heatmapData: null,
      progress: { total: 0, completed: 0, percent: 0 },
      error: null,
      _sseUnsubscribe: null,
    })
  },
}))
