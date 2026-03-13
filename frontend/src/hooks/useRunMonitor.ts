import { useEffect, useRef, useCallback } from 'react'
import { useSSE } from './useSSE'
import { useMetricsStore } from '@/stores/metricsStore'

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
