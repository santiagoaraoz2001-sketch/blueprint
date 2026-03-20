import { useEffect, useRef } from 'react'
import { sseManager } from '@/services/sseManager'
import { useMetricsStore } from '@/stores/metricsStore'
import { useRunStore } from '@/stores/runStore'
import { api } from '@/api/client'

const SYSTEM_POLL_INTERVAL = 5000

interface UseRunMonitorResult {
  isConnected: boolean
  activeBlockId: string | null
  overallProgress: number
  eta: number | null
  status: 'running' | 'complete' | 'failed' | null
}

/** Monitor all active runs for the dashboard overview. Subscribes to SSE events
 *  for the currently active run and polls system metrics. */
export function useDashboardMonitor(opts?: { enabled?: boolean }) {
  const enabled = opts?.enabled !== false
  const activeRunId = useRunStore((s) => s.activeRunId)

  useEffect(() => {
    if (!enabled || !activeRunId) return

    const unsubscribe = sseManager.subscribe(activeRunId, (event, data) => {
      if (event.startsWith('__sse_')) return
      const store = useMetricsStore.getState()
      if (!store.runs[activeRunId]) store.initRun(activeRunId)
      store.handleEvent(activeRunId, event, data)
    })

    return () => unsubscribe()
  }, [enabled, activeRunId])

  // System metrics polling for dashboard
  useEffect(() => {
    if (!enabled || !activeRunId) return

    const timer = setInterval(async () => {
      try {
        const hw = await api.get<any>('/system/metrics')
        if (!hw) return
        useMetricsStore.getState().addSystemMetric(activeRunId, {
          timestamp: Date.now(),
          cpu: hw.cpu_percent ?? 0,
          memory: hw.memory_gb ?? 0,
          memoryTotal: hw.memory_total_gb ?? 0,
        })
      } catch {
        // Non-critical
      }
    }, SYSTEM_POLL_INTERVAL)

    return () => clearInterval(timer)
  }, [enabled, activeRunId])
}

export function useRunMonitor(runId: string | null): UseRunMonitorResult {
  const systemTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Subscribe to SSE events via the shared manager (metrics-specific handling)
  useEffect(() => {
    if (!runId) return

    const unsubscribe = sseManager.subscribe(runId, (event, data) => {
      // Skip internal meta-events — runStore handles those
      if (event.startsWith('__sse_')) return

      const store = useMetricsStore.getState()
      if (!store.runs[runId]) {
        store.initRun(runId)
      }

      store.handleEvent(runId, event, data)
    })

    return () => unsubscribe()
  }, [runId])

  // Poll live system metrics while run is active
  useEffect(() => {
    if (!runId) return

    const pollSystem = async () => {
      try {
        const hw = await api.get<any>('/system/metrics')
        if (!hw) return

        useMetricsStore.getState().addSystemMetric(runId, {
          timestamp: Date.now(),
          cpu: hw.cpu_percent ?? 0,
          memory: hw.memory_gb ?? 0,
          memoryTotal: hw.memory_total_gb ?? 0,
          gpu: hw.gpu_percent ?? undefined,
        })
      } catch {
        // Non-critical — polling will retry on next interval
      }
    }

    // Initial poll
    pollSystem()

    systemTimerRef.current = setInterval(pollSystem, SYSTEM_POLL_INTERVAL)

    return () => {
      if (systemTimerRef.current) {
        clearInterval(systemTimerRef.current)
        systemTimerRef.current = null
      }
    }
  }, [runId])

  // Load run metadata (config snapshot, block categories) on mount
  useEffect(() => {
    if (!runId) return

    const loadRunMeta = async () => {
      try {
        const run = await api.get<any>(`/runs/${runId}`)
        if (!run) return

        const store = useMetricsStore.getState()

        // For completed/failed runs, load full historical data directly
        if (run.status === 'complete' || run.status === 'failed') {
          store.loadHistoricalRun(runId, run)
          return
        }

        // For running runs, initialize with block metadata from config snapshot
        const configSnapshot = run.config_snapshot || {}
        const nodes: any[] = configSnapshot.nodes || []

        const blockMeta: Record<string, { category: string; label: string }> = {}
        nodes.forEach((node: any) => {
          const data = node.data || {}
          blockMeta[node.id] = {
            category: data.category || 'data',
            label: data.label || data.type || node.id,
          }
        })

        if (!store.runs[runId]) {
          store.initRun(runId, {
            pipelineName: configSnapshot.name || run.pipeline_id || '',
            configSnapshot,
            blockMeta,
          })
        }
      } catch {
        // Run might not exist yet or be in progress
      }
    }

    loadRunMeta()
  }, [runId])

  // Read current state from stores
  const run = useMetricsStore((s) => (runId ? s.runs[runId] : null))
  const sseStatus = useRunStore((s) => s.sseStatus)

  return {
    isConnected: sseStatus === 'connected',
    activeBlockId: run?.activeBlockId ?? null,
    overallProgress: run?.overallProgress ?? 0,
    eta: run?.eta ?? null,
    status: run?.status ?? null,
  }
}
