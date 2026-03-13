import { create } from 'zustand'

// ── Type Definitions (GAP 3) ──────────────────────────────────────

export interface MetricPoint {
  value: number
  step: number | null
  timestamp: number
}

export interface BlockMetrics {
  nodeId: string
  blockType: string
  category: string // 'training'|'evaluation'|'inference'|'merge'|'data'|'flow'
  label: string
  metrics: Record<string, MetricPoint[]> // metric_name → time series
  status: 'queued' | 'running' | 'complete' | 'failed'
  progress: number // 0-1
  startedAt: number | null
  completedAt: number | null
}

export interface SystemMetricPoint {
  cpu_pct: number
  mem_pct: number
  mem_gb: number
  gpu_mem_pct: number | null
  gpu_mem_gb: number | null
  timestamp: number
}

export interface RunMonitorState {
  blocks: Record<string, BlockMetrics>
  executionOrder: string[]
  activeBlockId: string | null
  systemMetrics: SystemMetricPoint[]
  overallProgress: number
  eta: number | null
  status: 'running' | 'complete' | 'failed' | 'cancelled'
  startedAt: number
  pipelineName: string
  projectId: string | null
}

// ── Store Interface ───────────────────────────────────────────────

interface MetricsStoreState {
  runs: Record<string, RunMonitorState>

  // Selectors
  getActiveBlock: (runId: string) => BlockMetrics | null
  getMetricSeries: (runId: string, blockId: string, metricName: string) => MetricPoint[]
  getRunStatus: (runId: string) => RunMonitorState['status'] | null

  // Actions
  initRun: (runId: string, pipelineName: string, projectId: string | null) => void
  removeRun: (runId: string) => void

  handleMetricEvent: (runId: string, data: {
    node_id: string
    block_type?: string
    category?: string
    label?: string
    name: string
    value: number
    step?: number | null
  }) => void

  handleBlockStatus: (runId: string, nodeId: string, status: BlockMetrics['status'], progress?: number) => void

  handleSystemMetric: (runId: string, data: Omit<SystemMetricPoint, 'timestamp'>) => void

  updateOverallProgress: (runId: string, progress: number, eta: number | null) => void
  setRunStatus: (runId: string, status: RunMonitorState['status']) => void
  setActiveBlock: (runId: string, nodeId: string) => void
  setExecutionOrder: (runId: string, order: string[]) => void
}

// ── Store Implementation ──────────────────────────────────────────

function ensureBlock(run: RunMonitorState, nodeId: string, data?: { block_type?: string; category?: string; label?: string }): BlockMetrics {
  if (!run.blocks[nodeId]) {
    run.blocks[nodeId] = {
      nodeId,
      blockType: data?.block_type || 'unknown',
      category: data?.category || 'flow',
      label: data?.label || nodeId,
      metrics: {},
      status: 'queued',
      progress: 0,
      startedAt: null,
      completedAt: null,
    }
  }
  return run.blocks[nodeId]
}

export const useMetricsStore = create<MetricsStoreState>((set, get) => ({
  runs: {},

  getActiveBlock: (runId) => {
    const run = get().runs[runId]
    if (!run || !run.activeBlockId) return null
    return run.blocks[run.activeBlockId] || null
  },

  getMetricSeries: (runId, blockId, metricName) => {
    const run = get().runs[runId]
    if (!run) return []
    const block = run.blocks[blockId]
    if (!block) return []
    return block.metrics[metricName] || []
  },

  getRunStatus: (runId) => {
    const run = get().runs[runId]
    return run?.status ?? null
  },

  initRun: (runId, pipelineName, projectId) => {
    set((s) => ({
      runs: {
        ...s.runs,
        [runId]: {
          blocks: {},
          executionOrder: [],
          activeBlockId: null,
          systemMetrics: [],
          overallProgress: 0,
          eta: null,
          status: 'running',
          startedAt: Date.now(),
          pipelineName,
          projectId,
        },
      },
    }))
  },

  removeRun: (runId) => {
    set((s) => {
      const { [runId]: _, ...rest } = s.runs
      return { runs: rest }
    })
  },

  handleMetricEvent: (runId, data) => {
    set((s) => {
      const run = s.runs[runId]
      if (!run) return s
      const newRun = { ...run, blocks: { ...run.blocks } }
      const block = ensureBlock(newRun, data.node_id, data)
      const newBlock = { ...block, metrics: { ...block.metrics } }
      const series = [...(newBlock.metrics[data.name] || [])]
      series.push({ value: data.value, step: data.step ?? null, timestamp: Date.now() })
      newBlock.metrics[data.name] = series
      newRun.blocks[data.node_id] = newBlock
      return { runs: { ...s.runs, [runId]: newRun } }
    })
  },

  handleBlockStatus: (runId, nodeId, status, progress) => {
    set((s) => {
      const run = s.runs[runId]
      if (!run) return s
      const newRun = { ...run, blocks: { ...run.blocks } }
      const block = ensureBlock(newRun, nodeId)
      const newBlock = { ...block, status, progress: progress ?? block.progress }
      if (status === 'running' && !newBlock.startedAt) newBlock.startedAt = Date.now()
      if (status === 'complete' || status === 'failed') newBlock.completedAt = Date.now()
      if (status === 'complete') newBlock.progress = 1
      newRun.blocks[nodeId] = newBlock
      // Auto-set active block
      if (status === 'running') newRun.activeBlockId = nodeId
      return { runs: { ...s.runs, [runId]: newRun } }
    })
  },

  handleSystemMetric: (runId, data) => {
    set((s) => {
      const run = s.runs[runId]
      if (!run) return s
      const point: SystemMetricPoint = { ...data, timestamp: Date.now() }
      // Keep last 300 system metric points
      const metrics = [...run.systemMetrics, point].slice(-300)
      return { runs: { ...s.runs, [runId]: { ...run, systemMetrics: metrics } } }
    })
  },

  updateOverallProgress: (runId, progress, eta) => {
    set((s) => {
      const run = s.runs[runId]
      if (!run) return s
      return { runs: { ...s.runs, [runId]: { ...run, overallProgress: progress, eta } } }
    })
  },

  setRunStatus: (runId, status) => {
    set((s) => {
      const run = s.runs[runId]
      if (!run) return s
      return { runs: { ...s.runs, [runId]: { ...run, status } } }
    })
  },

  setActiveBlock: (runId, nodeId) => {
    set((s) => {
      const run = s.runs[runId]
      if (!run) return s
      return { runs: { ...s.runs, [runId]: { ...run, activeBlockId: nodeId } } }
    })
  },

  setExecutionOrder: (runId, order) => {
    set((s) => {
      const run = s.runs[runId]
      if (!run) return s
      return { runs: { ...s.runs, [runId]: { ...run, executionOrder: order } } }
    })
  },
}))
