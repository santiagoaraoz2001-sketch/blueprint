import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'

export interface ReplayArtifact {
  port_id: string
  artifact_id: string
  data_type: string
  preview: Record<string, unknown> | null
  size_bytes?: number
}

export interface ReplayError {
  title: string
  message: string
  action: string
}

export interface ReplayNode {
  node_id: string
  block_type: string
  status: 'completed' | 'failed' | 'skipped' | 'cached' | 'not_executed' | 'running'
  started_at: string | null
  duration_ms: number | null
  resolved_config: Record<string, unknown>
  config_sources: Record<string, string>
  decision: 'execute' | 'cache_hit' | 'skipped'
  decision_reason: string | null
  error: ReplayError | null
  input_artifacts: ReplayArtifact[]
  output_artifacts: ReplayArtifact[]
  execution_order: number
  iteration: number | null
  loop_id: string | null
  memory_peak_mb: number | null
}

export interface ReplayLoopSummary {
  controller_id: string
  iterations: number[]
  body_node_ids: string[]
  iteration_count: number
}

export interface ReplayData {
  run_id: string
  status: 'complete' | 'failed' | 'cancelled'
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
  nodes: ReplayNode[]
  loops: ReplayLoopSummary[]
}

export function useReplayData(runId: string | null) {
  return useQuery<ReplayData>({
    queryKey: ['replay', runId],
    queryFn: () => api.get<ReplayData>(`/runs/${runId}/replay`),
    enabled: !!runId,
    staleTime: 60_000,
    retry: 1,
  })
}

export function downloadSupportBundle(runId: string) {
  const url = `/api/runs/${runId}/support-bundle`
  // Use form POST to trigger download
  const a = document.createElement('a')
  a.href = url
  a.style.display = 'none'
  document.body.appendChild(a)

  fetch(url, { method: 'POST' })
    .then(res => res.blob())
    .then(blob => {
      const blobUrl = URL.createObjectURL(blob)
      a.href = blobUrl
      a.download = `blueprint-support-bundle-${runId.slice(0, 8)}.zip`
      a.click()
      URL.revokeObjectURL(blobUrl)
    })
    .finally(() => a.remove())
}
