/**
 * Typed SSE event payloads matching backend publish_event() calls.
 *
 * These are NOT part of the OpenAPI schema (SSE is a streaming protocol).
 * Maintained manually to match backend/engine/executor.py event shapes.
 */

export interface SSENodeStarted {
  node_id: string
  block_type: string
  label: string
  started_at: string
}

export interface SSENodeProgress {
  node_id: string
  progress: number
  overall?: number
  eta?: number
}

export interface SSENodeLog {
  node_id: string
  message: string
  level?: 'info' | 'warn' | 'error'
}

export interface SSENodeOutput {
  node_id: string
  outputs: Record<string, unknown>
}

export interface SSENodeCompleted {
  node_id: string
  block_type: string
  label: string
  duration_s: number
  completed_at: string
  outputs?: Record<string, unknown>
}

export interface SSENodeFailed {
  node_id: string
  error: string
  block_type?: string
  traceback?: string
}

export interface SSENodeCached {
  node_id: string
  source_run_id: string
}

export interface SSENodeIteration {
  node_id: string
  iteration: number
  max_iterations: number
}

export interface SSENodeRetry {
  node_id: string
  attempt: number
  max_attempts: number
  error: string
}

export interface SSEMetric {
  node_id: string
  metric_name: string
  value: number
  step: number
  timestamp: string
  category?: string
}

export interface SSESystemMetric {
  cpu_percent: number
  memory_percent: number
  memory_gb: number
  memory_total_gb: number
  gpu_percent?: number | null
  timestamp: string
}

export interface SSERunCompleted {
  run_id: string
  duration_s: number
  completed_at: string
}

export interface SSERunFailed {
  run_id: string
  error: string
}

export interface SSERunCancelled {
  run_id: string
  cancelled_at: string
}

/** Discriminated union of all SSE event types */
export type SSEEvent =
  | { type: 'node_started'; data: SSENodeStarted }
  | { type: 'node_progress'; data: SSENodeProgress }
  | { type: 'node_log'; data: SSENodeLog }
  | { type: 'node_output'; data: SSENodeOutput }
  | { type: 'node_completed'; data: SSENodeCompleted }
  | { type: 'node_failed'; data: SSENodeFailed }
  | { type: 'node_cached'; data: SSENodeCached }
  | { type: 'node_iteration'; data: SSENodeIteration }
  | { type: 'node_retry'; data: SSENodeRetry }
  | { type: 'metric'; data: SSEMetric }
  | { type: 'system_metric'; data: SSESystemMetric }
  | { type: 'run_completed'; data: SSERunCompleted }
  | { type: 'run_failed'; data: SSERunFailed }
  | { type: 'run_cancelled'; data: SSERunCancelled }

/** Helper to narrow SSE event data by type */
export type SSEEventData<T extends SSEEvent['type']> = Extract<SSEEvent, { type: T }>['data']
