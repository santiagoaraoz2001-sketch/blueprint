import { useEffect, useRef, useCallback } from 'react'
import { useSSE } from './useSSE'
import { useMetricsStore } from '@/stores/metricsStore'

// ── Per-Run Monitor (Session 4) ─────────────────────────────────────────────

interface UseRunMonitorResult {
  isConnected: boolean
  activeBlock: string | null
  overallProgress: number
  eta: number | null
  status: 'idle' | 'running' | 'complete' | 'failed' | 'cancelled'
}

/**
 * Subscribes to SSE for a run and routes events to the metricsStore.
 * Does NOT clear the store on unmount (data persists for replay).
 */
export function useRunMonitor(runId: string | null): UseRunMonitorResult {
  const isConnectedRef = useRef(false)
  const notificationPermissionRequested = useRef(false)

  const store = useMetricsStore

  // Ensure run state exists
  useEffect(() => {
    if (runId) {
      store.getState().ensureRun(runId)
    }
  }, [runId])

  // Request notification permission on first pipeline start
  useEffect(() => {
    if (
      runId &&
      !notificationPermissionRequested.current &&
      typeof Notification !== 'undefined' &&
      Notification.permission === 'default'
    ) {
      notificationPermissionRequested.current = true
      Notification.requestPermission()
    }
  }, [runId])

  const handleEvent = useCallback(
    (event: string, data: any) => {
      if (!runId) return
      isConnectedRef.current = true

      const s = store.getState()

      switch (event) {
        case 'node_started':
          s.handleNodeStarted(runId, data)
          break
        case 'node_progress':
          s.handleNodeProgress(runId, data)
          break
        case 'node_completed':
          s.handleNodeCompleted(runId, data)
          break
        case 'node_failed':
          s.handleNodeFailed(runId, data)
          break
        case 'metric':
          s.handleMetric(runId, data)
          break
        case 'system_metric':
          s.handleSystemMetric(runId, data)
          break
        case 'run_completed':
          s.handleRunCompleted(runId, data)
          // Desktop notification
          if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            new Notification('Experiment Complete', {
              body: `Run ${runId.slice(0, 8)} finished in ${data.duration ? Math.round(data.duration) + 's' : 'unknown time'}`,
              tag: runId,
            })
          }
          break
        case 'run_failed':
          s.handleRunFailed(runId, data)
          // Desktop notification
          if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            new Notification('Experiment Failed', {
              body: `Run ${runId.slice(0, 8)} failed: ${data.error ?? 'unknown error'}`,
              tag: runId,
            })
          }
          break
        case 'run_cancelled':
          s.handleRunCancelled(runId)
          break
      }
    },
    [runId],
  )

  const handleError = useCallback(() => {
    isConnectedRef.current = false
  }, [])

  const url = runId ? `/api/events/runs/${runId}` : null

  useSSE(url, {
    onEvent: handleEvent,
    onError: handleError,
    enabled: !!runId,
  })

  // Read from store reactively
  const runState = useMetricsStore((s) => (runId ? s.runs[runId] : null))

  return {
    isConnected: isConnectedRef.current,
    activeBlock: runState?.activeBlockId ?? null,
    overallProgress: runState?.overallProgress ?? 0,
    eta: runState?.eta ?? null,
    status: runState?.status ?? 'idle',
  }
}

// ── Dashboard Monitor (Session 5) ───────────────────────────────────────────

interface UseDashboardMonitorOptions {
  enabled?: boolean
}

/**
 * Subscribes to the global SSE stream for run events.
 * Updates metricsStore with live progress, metrics, and status changes.
 * Triggers dashboard re-fetch on run_completed / run_failed.
 */
export function useDashboardMonitor(options: UseDashboardMonitorOptions = {}) {
  const { enabled = true } = options
  const updateRunMetrics = useMetricsStore((s) => s.updateRunMetrics)
  const fetchDashboard = useMetricsStore((s) => s.fetchDashboard)

  const handleEvent = useCallback(
    (event: string, data: any) => {
      const runId = data.run_id
      if (!runId) return

      switch (event) {
        case 'run_started':
          updateRunMetrics(runId, {
            runId,
            status: 'running',
            progress: 0,
            eta: data.eta ?? null,
            currentBlock: data.block_name ?? null,
            loss: [],
            accuracy: [],
          })
          break

        case 'node_started':
          updateRunMetrics(runId, {
            runId,
            currentBlock: data.block_name ?? data.node_id ?? null,
          })
          break

        case 'node_progress':
        case 'run_progress':
          updateRunMetrics(runId, {
            runId,
            progress: data.progress ?? data.overall ?? 0,
            eta: data.eta ?? null,
            currentBlock: data.block_name ?? data.node_id ?? null,
            status: 'running',
          })
          break

        case 'metric': {
          const store = useMetricsStore.getState()
          const existing = store.liveMetrics[runId]
          if (data.name === 'loss' && existing) {
            store.appendLossPoint(runId, {
              step: data.step ?? (existing.loss?.length ?? 0),
              value: data.value,
              timestamp: Date.now(),
            })
          }
          break
        }

        case 'run_completed':
          updateRunMetrics(runId, {
            runId,
            status: 'complete',
            progress: 1,
            eta: 0,
          })
          fetchDashboard()
          break

        case 'run_failed':
          updateRunMetrics(runId, {
            runId,
            status: 'failed',
            error: data.error,
          })
          fetchDashboard()
          break
      }
    },
    [updateRunMetrics, fetchDashboard]
  )

  const sseUrl = enabled ? '/api/runs/stream' : null

  return useSSE(sseUrl, {
    onEvent: handleEvent,
    enabled,
  })
}
