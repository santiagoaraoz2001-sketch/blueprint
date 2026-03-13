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

/** Stub for dashboard SSE monitoring — real implementation TBD */
export function useDashboardMonitor(_opts?: { enabled?: boolean }) {
  // No-op: dashboard live updates will be wired in a future session
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

  // Poll system hardware metrics while run is active
  useEffect(() => {
    if (!runId) return

    const pollSystem = async () => {
      try {
        const hw = await api.get<any>('/system/hardware')
        if (!hw) return
        const cpu = hw.cpu
        const ram = hw.ram
        const gpus = hw.gpus || []
        const gpu = gpus[0]

        useMetricsStore.getState().addSystemMetric(runId, {
          timestamp: Date.now(),
          cpu: cpu?.percent ?? 0,
          memory: ram?.used_gb ?? 0,
          memoryTotal: ram?.total_gb ?? 0,
          gpu: gpu?.utilization ?? undefined,
          gpuMemory: gpu?.memory_used_gb ?? undefined,
          gpuMemoryTotal: gpu?.memory_total_gb ?? undefined,
        })
      } catch {
        // Silently fail — system metrics are non-critical
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
