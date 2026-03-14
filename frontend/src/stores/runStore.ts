import { create } from 'zustand'
import { api } from '@/api/client'
import { useSettingsStore } from './settingsStore'
import { playSound } from '@/lib/audio'
import { sseManager } from '@/services/sseManager'

export interface NodeStatus {
  nodeId: string
  status: 'pending' | 'running' | 'complete' | 'failed' | 'cached'
  progress: number
  error?: string
}

export interface PartialRunMeta {
  sourceRunId: string
  startNodeId: string
  reusedNodes: string[]
  configOverrides: Record<string, Record<string, any>>
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
  sseStatus: 'connected' | 'reconnecting' | 'stale' | 'disconnected'
  partialRunMeta: PartialRunMeta | null
  _demoTimer: number | null
  _elapsedTimer: number | null
  _sseUnsubscribe: (() => void) | null

  // Actions
  startRun: (pipelineId: string) => Promise<void>
  startPartialRun: (pipelineId: string, sourceRunId: string, startNodeId: string, configOverrides: Record<string, Record<string, any>>, reusedNodes: string[]) => Promise<void>
  stopRun: () => Promise<void>
  connectSSE: (runId: string) => void
  disconnectSSE: () => void
  handleSSEEvent: (event: string, data: SSEEventData) => void
  reset: () => void
}

function isDemoMode() {
  return useSettingsStore.getState().demoMode
}

function _startElapsedTimer(set: (fn: (s: RunState) => Partial<RunState>) => void): number {
  return window.setInterval(() => {
    set((s) => s.status === 'running' ? { elapsed: s.elapsed + 1 } : {})
  }, 1000)
}

function _clearElapsedTimer(get: () => RunState) {
  const timer = get()._elapsedTimer
  if (timer) window.clearInterval(timer)
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
  sseStatus: 'disconnected' as const,
  partialRunMeta: null,
  _demoTimer: null,
  _elapsedTimer: null,
  _sseUnsubscribe: null,

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
      _clearElapsedTimer(get)
      const res = await api.post<{ status: string; pipeline_id: string; run_id: string }>(
        `/pipelines/${pipelineId}/execute`
      )
      const elapsedTimer = _startElapsedTimer(set)
      set({
        activeRunId: res?.run_id ?? null,
        pipelineId,
        status: 'running',
        nodeStatuses: {},
        nodeOutputs: {},
        overallProgress: 0,
        eta: null,
        elapsed: 0,
        error: null,
        logs: [],
        _elapsedTimer: elapsedTimer,
      })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to start run'
      set({ status: 'failed', error: msg })
    }
  },

  startPartialRun: async (pipelineId: string, sourceRunId: string, startNodeId: string, configOverrides: Record<string, Record<string, any>>, reusedNodes: string[]) => {
    if (isDemoMode()) {
      // Simulate partial run in demo mode
      const meta: PartialRunMeta = { sourceRunId, startNodeId, reusedNodes, configOverrides }
      const cachedStatuses: Record<string, NodeStatus> = {}
      for (const nid of reusedNodes) {
        cachedStatuses[nid] = { nodeId: nid, status: 'cached', progress: 1 }
      }
      set({
        activeRunId: `demo-partial-${Date.now()}`,
        pipelineId,
        status: 'running',
        nodeStatuses: cachedStatuses,
        overallProgress: 0,
        eta: 15,
        elapsed: 0,
        error: null,
        partialRunMeta: meta,
      })
      let progress = 0
      const timer = window.setInterval(() => {
        progress += 0.08
        if (progress >= 1) {
          window.clearInterval(timer)
          set({ status: 'complete', overallProgress: 1, eta: 0 })
          return
        }
        set((s) => ({
          overallProgress: progress,
          elapsed: s.elapsed + 0.5,
          eta: Math.max(0, (1 - progress) * 15),
        }))
      }, 500)
      set({ _demoTimer: timer })
      return
    }
    try {
      _clearElapsedTimer(get)
      const meta: PartialRunMeta = { sourceRunId, startNodeId, reusedNodes, configOverrides }
      const cachedStatuses: Record<string, NodeStatus> = {}
      for (const nid of reusedNodes) {
        cachedStatuses[nid] = { nodeId: nid, status: 'cached', progress: 1 }
      }
      const res = await api.post<{ status: string; pipeline_id: string; run_id: string }>(
        `/pipelines/${pipelineId}/execute-from`,
        { source_run_id: sourceRunId, start_node_id: startNodeId, config_overrides: configOverrides }
      )
      const elapsedTimer = _startElapsedTimer(set)
      set({
        activeRunId: res?.run_id ?? null,
        pipelineId,
        status: 'running',
        nodeStatuses: cachedStatuses,
        nodeOutputs: {},
        overallProgress: 0,
        eta: null,
        elapsed: 0,
        error: null,
        logs: [],
        partialRunMeta: meta,
        _elapsedTimer: elapsedTimer,
      })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to start partial run'
      set({ status: 'failed', error: msg })
    }
  },

  stopRun: async () => {
    const { activeRunId, _demoTimer } = get()
    if (!activeRunId) return
    _clearElapsedTimer(get)
    get().disconnectSSE()
    if (isDemoMode()) {
      if (_demoTimer) window.clearInterval(_demoTimer)
      set({ status: 'cancelled', error: 'Stopped by user', _demoTimer: null, _elapsedTimer: null })
      return
    }
    try {
      await api.post(`/runs/${activeRunId}/stop`)
      set({ status: 'cancelled', error: 'Stopped by user', _elapsedTimer: null })
    } catch {
      // Ignore stop errors
    }
  },

  connectSSE: (runId: string) => {
    const { _sseUnsubscribe } = get()
    if (_sseUnsubscribe) _sseUnsubscribe()

    const unsubscribe = sseManager.subscribe(runId, (event, data) => {
      // Handle meta-events for connection status
      if (event === '__sse_stale' || event === '__sse_failed') {
        set({ sseStatus: 'stale' })
        return
      }
      if (event === '__sse_reconnecting') {
        set({ sseStatus: 'reconnecting' })
        return
      }
      if (event === '__sse_connected') {
        set({ sseStatus: 'connected' })
        return
      }

      // Forward real SSE events to handler
      get().handleSSEEvent(event, data)
    })

    set({ _sseUnsubscribe: unsubscribe, sseStatus: 'connected' })
  },

  disconnectSSE: () => {
    const { _sseUnsubscribe } = get()
    if (_sseUnsubscribe) _sseUnsubscribe()
    set({ _sseUnsubscribe: null, sseStatus: 'disconnected' })
  },

  handleSSEEvent: (event: string, data: SSEEventData) => {
    const state = get()

    switch (event) {
      case 'node_cached':
        set({
          nodeStatuses: {
            ...state.nodeStatuses,
            [data.node_id || '']: {
              nodeId: data.node_id || '',
              status: 'cached',
              progress: 1,
            },
          },
        })
        break

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

      case 'node_progress': {
        const nodeId = data.node_id || ''
        const existing = state.nodeStatuses[nodeId]
        set({
          overallProgress: data.overall || state.overallProgress,
          eta: data.eta ?? state.eta,
          nodeStatuses: {
            ...state.nodeStatuses,
            [nodeId]: {
              nodeId,
              status: existing?.status || 'running',
              progress: data.progress || 0,
            },
          },
        })
        break
      }

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
        _clearElapsedTimer(get)
        set({
          activeRunId: data.run_id,
          status: 'complete',
          overallProgress: 1,
          _elapsedTimer: null,
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
        _clearElapsedTimer(get)
        set({
          activeRunId: data.run_id,
          status: 'failed',
          error: data.error,
          _elapsedTimer: null,
        })
        playSound('error')
        break

      case 'run_cancelled':
        _clearElapsedTimer(get)
        set({
          activeRunId: data.run_id,
          status: 'cancelled',
          error: 'Run cancelled',
          _elapsedTimer: null,
        })
        break
    }
  },

  reset: () => {
    // Clean up SSE, timers on reset to prevent leaks
    const { _demoTimer, _sseUnsubscribe } = get()
    if (_sseUnsubscribe) _sseUnsubscribe()
    if (_demoTimer) window.clearInterval(_demoTimer)
    _clearElapsedTimer(get)
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
      sseStatus: 'disconnected',
      partialRunMeta: null,
      _demoTimer: null,
      _elapsedTimer: null,
      _sseUnsubscribe: null,
    })
  },
}))
