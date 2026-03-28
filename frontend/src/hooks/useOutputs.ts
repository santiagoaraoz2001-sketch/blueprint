/**
 * TanStack Query hooks for the Global Outputs Monitor.
 *
 * All server state for the outputs dashboard flows through these hooks —
 * no raw fetch or Zustand for this data.
 */

import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'

// ── Types ────────────────────────────────────────────────────────

export interface ArtifactItem {
  id: string
  run_id: string
  pipeline_id: string
  node_id: string
  block_type: string
  name: string
  artifact_type: string
  file_path: string
  size_bytes: number
  hash: string | null
  metadata: Record<string, unknown> | null
  created_at: string
}

export interface RunWithArtifacts {
  id: string
  pipeline_id: string
  pipeline_name: string | null
  project_id: string | null
  status: string
  started_at: string
  finished_at: string | null
  duration_seconds: number | null
  error_message: string | null
  metrics: Record<string, unknown> | null
  artifacts: ArtifactItem[]
}

export interface LiveRunItem {
  run_id: string
  pipeline_name: string
  project_name: string
  current_block: string
  current_block_index: number
  total_blocks: number
  block_progress: number
  overall_progress: number
  eta_seconds: number | null
  status: string
  started_at: string
  updated_at: string
}

export interface OutputsDashboard {
  runs: RunWithArtifacts[]
  live_runs: LiveRunItem[]
  total_runs: number
  total_artifacts: number
  artifact_type_counts: Record<string, number>
}

// ── Query Keys ───────────────────────────────────────────────────

export const outputsKeys = {
  all: ['outputs'] as const,
  dashboard: (filters: { projectId?: string | null; status?: string | null; limit?: number; offset?: number }) =>
    ['outputs', 'dashboard', filters] as const,
  runs: (filters: { projectId?: string | null; pipelineId?: string | null; status?: string | null }) =>
    ['outputs', 'runs', filters] as const,
  artifacts: (filters: { projectId?: string | null; pipelineId?: string | null; artifactType?: string | null }) =>
    ['outputs', 'artifacts', filters] as const,
  artifact: (id: string) => ['outputs', 'artifact', id] as const,
  live: () => ['outputs', 'live'] as const,
}

// ── Hooks ────────────────────────────────────────────────────────

/**
 * Fetch the aggregate outputs dashboard.
 * Refetches every 10s while a run is active, 30s otherwise.
 */
export function useOutputsDashboard(opts: {
  projectId?: string | null
  status?: string | null
  limit?: number
  offset?: number
  enabled?: boolean
} = {}) {
  const { projectId, status, limit = 50, offset = 0, enabled = true } = opts

  return useQuery({
    queryKey: outputsKeys.dashboard({ projectId, status, limit, offset }),
    queryFn: async () => {
      const params = new URLSearchParams()
      if (projectId) params.set('project_id', projectId)
      if (status) params.set('status', status)
      params.set('limit', String(limit))
      params.set('offset', String(offset))
      const qs = params.toString()
      return api.get<OutputsDashboard>(`/outputs/dashboard${qs ? `?${qs}` : ''}`)
    },
    enabled,
    staleTime: 10_000,
    refetchInterval: 30_000,
  })
}

/**
 * Fetch runs with nested artifacts. Supports project/pipeline/status filtering.
 */
export function useOutputRuns(opts: {
  projectId?: string | null
  pipelineId?: string | null
  status?: string | null
  limit?: number
  enabled?: boolean
} = {}) {
  const { projectId, pipelineId, status, limit = 50, enabled = true } = opts

  return useQuery({
    queryKey: outputsKeys.runs({ projectId, pipelineId, status }),
    queryFn: async () => {
      const params = new URLSearchParams()
      if (projectId) params.set('project_id', projectId)
      if (pipelineId) params.set('pipeline_id', pipelineId)
      if (status) params.set('status', status)
      if (limit) params.set('limit', String(limit))
      const qs = params.toString()
      return api.get<RunWithArtifacts[]>(`/outputs/runs${qs ? `?${qs}` : ''}`)
    },
    enabled,
    staleTime: 10_000,
  })
}

/**
 * Fetch artifacts with filtering. Used for cross-pipeline artifact picker.
 */
export function useOutputArtifacts(opts: {
  projectId?: string | null
  pipelineId?: string | null
  runId?: string | null
  artifactType?: string | null
  limit?: number
  enabled?: boolean
} = {}) {
  const { projectId, pipelineId, runId, artifactType, limit = 100, enabled = true } = opts

  return useQuery({
    queryKey: outputsKeys.artifacts({ projectId, pipelineId, artifactType, ...(runId ? { runId } : {}) }),
    queryFn: async () => {
      const params = new URLSearchParams()
      if (projectId) params.set('project_id', projectId)
      if (pipelineId) params.set('pipeline_id', pipelineId)
      if (runId) params.set('run_id', runId)
      if (artifactType) params.set('artifact_type', artifactType)
      if (limit) params.set('limit', String(limit))
      const qs = params.toString()
      return api.get<ArtifactItem[]>(`/outputs/artifacts${qs ? `?${qs}` : ''}`)
    },
    enabled,
    staleTime: 15_000,
  })
}

/**
 * Fetch a single artifact by ID.
 */
export function useArtifact(artifactId: string | null) {
  return useQuery({
    queryKey: outputsKeys.artifact(artifactId || ''),
    queryFn: () => api.get<ArtifactItem>(`/outputs/artifacts/${artifactId}`),
    enabled: !!artifactId,
    staleTime: 60_000,
  })
}

/**
 * Structured preview of an artifact's file content.
 * Server-side parsing handles CSV, JSONL, Parquet, text, etc.
 */
export interface ArtifactPreviewData {
  artifact_id: string
  rows: Record<string, unknown>[]
  columns: string[]
  total_rows: number
  format: string
  error?: string
}

export function useArtifactPreview(artifactId: string | null, opts?: { rows?: number }) {
  const rows = opts?.rows ?? 20
  return useQuery({
    queryKey: ['outputs', 'artifact-preview', artifactId, rows] as const,
    queryFn: () => api.get<ArtifactPreviewData>(
      `/outputs/artifacts/${artifactId}/preview?rows=${rows}`
    ),
    enabled: !!artifactId,
    staleTime: 60_000,
  })
}

/**
 * Fetch currently running pipelines. Polls every 5s.
 */
export function useLiveRuns(enabled = true) {
  return useQuery({
    queryKey: outputsKeys.live(),
    queryFn: () => api.get<LiveRunItem[]>('/outputs/live'),
    enabled,
    staleTime: 5_000,
    refetchInterval: 5_000,
  })
}
