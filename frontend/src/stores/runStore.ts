import { create } from 'zustand'
import { api } from '@/api/client'
import { useSettingsStore } from './settingsStore'
import { playSound } from '@/lib/audio'

export interface NodeStatus {
  nodeId: string
  status: 'pending' | 'running' | 'complete' | 'failed'
  progress: number
  error?: string
}

/** Typed SSE event data from the pipeline executor */
export interface SSEEventData {
  run_id?: string
  node_id?: string
  progress?: number
  overall?: number
  eta?: number
  error?: string
  event?: string
}

interface RunState {
  activeRunId: string | null
  pipelineId: string | null
  status: 'idle' | 'running' | 'complete' | 'failed' | 'cancelled'
  nodeStatuses: Record<string, NodeStatus>
  nodeOutputs: Record<string, Record<string, any>>
  overallProgress: number
  eta: number | null
  elapsed: number
  error: string | null
  logs: string[]
  _demoTimer: number | null

  // Actions
  startRun: (pipelineId: string) => Promise<void>
  stopRun: () => Promise<void>
  handleSSEEvent: (event: string, data: SSEEventData) => void
  reset: () => void
}

function isDemoMode() {
  return useSettingsStore.getState().demoMode
}

export const useRunStore = create<RunState>((set, get) => ({
  activeRunId: null,
  pipelineId: null,
  status: 'idle',
  nodeStatuses: {},
  nodeOutputs: {},
  overallProgress: 0,
  eta: null,
  elapsed: 0,
  error: null,
  logs: [],
  _demoTimer: null,

  startRun: async (pipelineId: string) => {
    if (isDemoMode()) {
      // Simulate a pipeline run in demo mode
      set({
        activeRunId: `demo-run-${Date.now()}`,
        pipelineId,
        status: 'running',
        nodeStatuses: {},
        overallProgress: 0,
        eta: 30,
        elapsed: 0,
        error: null,
      })
      // Simulate progress updates every 500ms
      let progress = 0
      const timer = window.setInterval(() => {
        progress += 0.05
        if (progress >= 1) {
          window.clearInterval(timer)
          set({ status: 'complete', overallProgress: 1, eta: 0 })
          return
        }
        set((s) => ({
          overallProgress: progress,
          elapsed: s.elapsed + 0.5,
          eta: Math.max(0, (1 - progress) * 30),
        }))
      }, 500)
      set({ _demoTimer: timer })
      return
    }
    try {
      await api.post<{ status: string; pipeline_id: string }>(
        `/pipelines/${pipelineId}/execute`
      )
      set({
        pipelineId,
        status: 'running',
        nodeStatuses: {},
        nodeOutputs: {},
        overallProgress: 0,
        eta: null,
        elapsed: 0,
        error: null,
        logs: [],
      })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to start run'
      set({ status: 'failed', error: msg })
    }
  },

  stopRun: async () => {
    const { activeRunId, _demoTimer } = get()
    if (!activeRunId) return
    if (isDemoMode()) {
      if (_demoTimer) window.clearInterval(_demoTimer)
      set({ status: 'cancelled', error: 'Stopped by user', _demoTimer: null })
      return
    }
    try {
      await api.post(`/runs/${activeRunId}/stop`)
      set({ status: 'cancelled', error: 'Stopped by user' })
    } catch {
      // Ignore stop errors
    }
  },

  handleSSEEvent: (event: string, data: SSEEventData) => {
    const state = get()

    switch (event) {
      case 'node_started':
        set({
          activeRunId: data.run_id || state.activeRunId,
          nodeStatuses: {
            ...state.nodeStatuses,
            [data.node_id || '']: {
              nodeId: data.node_id || '',
              status: 'running',
              progress: 0,
            },
          },
        })
        break

      case 'node_progress':
        set({
          overallProgress: data.overall || state.overallProgress,
          eta: data.eta ?? state.eta,
          nodeStatuses: {
            ...state.nodeStatuses,
            [data.node_id || '']: {
              ...state.nodeStatuses[data.node_id || ''],
              progress: data.progress || 0,
            },
          },
        })
        break

      case 'node_completed':
        set({
          nodeStatuses: {
            ...state.nodeStatuses,
            [data.node_id || '']: {
              nodeId: data.node_id || '',
              status: 'complete',
              progress: 1,
            },
          },
        })
        playSound('step_complete')
        break

      case 'node_failed':
        set({
          nodeStatuses: {
            ...state.nodeStatuses,
            [data.node_id || '']: {
              nodeId: data.node_id || '',
              status: 'failed',
              progress: 0,
              error: data.error,
            },
          },
        })
        playSound('error')
        break

      case 'run_completed':
        set({
          activeRunId: data.run_id,
          status: 'complete',
          overallProgress: 1,
        })
        playSound('pipeline_complete')
        break

      case 'node_log':
        set((s) => ({
          logs: [...s.logs.slice(-499), (data as any).message || ''],
        }))
        break

      case 'metric':
        set((s) => ({
          logs: [...s.logs.slice(-499), `[metric] ${(data as any).name}: ${(data as any).value}`],
        }))
        break

      case 'node_output':
        set((s) => ({
          nodeOutputs: {
            ...s.nodeOutputs,
            [(data as any).node_id || '']: (data as any).outputs || {},
          },
          logs: [...s.logs.slice(-499), `[output] Block ${(data as any).node_id}: ${Object.keys((data as any).outputs || {}).join(', ')}`],
        }))
        break

      case 'run_failed':
        set({
          activeRunId: data.run_id,
          status: 'failed',
          error: data.error,
        })
        playSound('error')
        break
    }
  },

  reset: () => {
    // Clear demo timer on reset to prevent leaks
    const { _demoTimer } = get()
    if (_demoTimer) window.clearInterval(_demoTimer)
    set({
      activeRunId: null,
      pipelineId: null,
      status: 'idle',
      nodeStatuses: {},
      nodeOutputs: {},
      overallProgress: 0,
      eta: null,
      elapsed: 0,
      error: null,
      logs: [],
      _demoTimer: null,
    })
  },
}))
