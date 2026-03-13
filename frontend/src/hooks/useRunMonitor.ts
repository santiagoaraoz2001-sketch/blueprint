import { useSSE } from './useSSE'
import { useMetricsStore } from '@/stores/metricsStore'
import { useCallback } from 'react'

/**
 * Subscribes to SSE events for a specific run and pipes them into the metricsStore.
 * Used by ActivityFeed (for live sparklines) and MonitorView.
 */
export function useRunMonitor(runId: string | null, enabled = true) {
  const store = useMetricsStore
  const sseUrl = runId ? `/api/events/runs/${runId}` : null

  const handleEvent = useCallback(
    (event: string, data: any) => {
      if (!runId) return
      const s = store.getState()

      switch (event) {
        case 'node_started':
          s.handleBlockStatus(runId, data.node_id, 'running')
          if (data.block_type || data.category) {
            // Ensure block metadata is set
            s.handleMetricEvent(runId, {
              node_id: data.node_id,
              block_type: data.block_type,
              category: data.category,
              label: data.label,
              name: '__started',
              value: 1,
              step: 0,
            })
          }
          break

        case 'node_progress':
          s.handleBlockStatus(runId, data.node_id, 'running', data.progress)
          s.updateOverallProgress(runId, data.overall ?? s.runs[runId]?.overallProgress ?? 0, data.eta ?? null)
          break

        case 'node_completed':
          s.handleBlockStatus(runId, data.node_id, 'complete')
          break

        case 'node_failed':
          s.handleBlockStatus(runId, data.node_id, 'failed')
          break

        case 'metric':
          s.handleMetricEvent(runId, {
            node_id: data.node_id,
            block_type: data.block_type,
            category: data.category,
            label: data.label,
            name: data.name,
            value: data.value,
            step: data.step ?? null,
          })
          break

        case 'system_metrics':
          s.handleSystemMetric(runId, {
            cpu_pct: data.cpu_pct ?? 0,
            mem_pct: data.mem_pct ?? 0,
            mem_gb: data.mem_gb ?? 0,
            gpu_mem_pct: data.gpu_mem_pct ?? null,
            gpu_mem_gb: data.gpu_mem_gb ?? null,
          })
          break

        case 'run_completed':
          s.setRunStatus(runId, 'complete')
          s.updateOverallProgress(runId, 1, 0)
          break

        case 'run_failed':
          s.setRunStatus(runId, 'failed')
          break

        case 'run_cancelled':
          s.setRunStatus(runId, 'cancelled')
          break

        case 'execution_order':
          if (data.order) s.setExecutionOrder(runId, data.order)
          break
      }
    },
    [runId],
  )

  useSSE(sseUrl, { onEvent: handleEvent, enabled: enabled && !!runId })

  return {
    run: useMetricsStore((s) => s.runs[runId ?? '']),
    progress: useMetricsStore((s) => s.runs[runId ?? '']?.overallProgress ?? 0),
    eta: useMetricsStore((s) => s.runs[runId ?? '']?.eta ?? null),
    status: useMetricsStore((s) => s.runs[runId ?? '']?.status ?? null),
  }
}
