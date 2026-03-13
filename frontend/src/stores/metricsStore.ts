import { create } from 'zustand'

// ── Types ──────────────────────────────────────────────────────────────────

export interface MetricPoint {
  value: number
  timestamp: number
}

export interface BlockMetrics {
  category: string
  status: 'pending' | 'running' | 'complete' | 'failed'
  progress: number
  metrics: Record<string, MetricPoint[]> // name → time series
}

export interface SystemMetricSnapshot {
  timestamp: number
  cpu_pct: number
  mem_pct: number
  mem_gb: number
  gpu_mem_pct?: number
}

export interface RunMonitorState {
  blocks: Record<string, BlockMetrics> // nodeId → BlockMetrics
  executionOrder: string[]
  activeBlockId: string | null
  systemMetrics: SystemMetricSnapshot[]
  overallProgress: number
  eta: number | null
  status: 'idle' | 'running' | 'complete' | 'failed' | 'cancelled'
  startedAt: number | null
  pipelineName: string
  projectId: string
}

// ── Store State ────────────────────────────────────────────────────────────

interface MetricsStoreState {
  runs: Record<string, RunMonitorState>

  // Event handlers
  handleNodeStarted: (runId: string, data: any) => void
  handleNodeProgress: (runId: string, data: any) => void
  handleNodeCompleted: (runId: string, data: any) => void
  handleNodeFailed: (runId: string, data: any) => void
  handleMetric: (runId: string, data: any) => void
  handleSystemMetric: (runId: string, data: any) => void
  handleRunCompleted: (runId: string, data: any) => void
  handleRunFailed: (runId: string, data: any) => void
  handleRunCancelled: (runId: string) => void

  // Historical replay
  loadMetricsLog: (runId: string, events: any[]) => void

  // Init helper
  ensureRun: (runId: string) => void
}

function defaultRunState(): RunMonitorState {
  return {
    blocks: {},
    executionOrder: [],
    activeBlockId: null,
    systemMetrics: [],
    overallProgress: 0,
    eta: null,
    status: 'idle',
    startedAt: null,
    pipelineName: '',
    projectId: '',
  }
}

function ensureRunState(runs: Record<string, RunMonitorState>, runId: string): Record<string, RunMonitorState> {
  if (runs[runId]) return runs
  return { ...runs, [runId]: defaultRunState() }
}

// ── Selectors ──────────────────────────────────────────────────────────────

export function getActiveBlock(runId: string): (state: MetricsStoreState) => BlockMetrics | null {
  return (state) => {
    const run = state.runs[runId]
    if (!run || !run.activeBlockId) return null
    return run.blocks[run.activeBlockId] ?? null
  }
}

export function getMetricSeries(
  runId: string,
  nodeId: string,
  metricName: string,
): (state: MetricsStoreState) => MetricPoint[] {
  return (state) => {
    const run = state.runs[runId]
    if (!run) return []
    const block = run.blocks[nodeId]
    if (!block) return []
    return block.metrics[metricName] ?? []
  }
}

export function getLatestSystemMetrics(
  runId: string,
): (state: MetricsStoreState) => SystemMetricSnapshot | null {
  return (state) => {
    const run = state.runs[runId]
    if (!run || run.systemMetrics.length === 0) return null
    return run.systemMetrics[run.systemMetrics.length - 1]
  }
}

export function getAllMetricNames(
  runId: string,
  nodeId: string,
): (state: MetricsStoreState) => string[] {
  return (state) => {
    const run = state.runs[runId]
    if (!run) return []
    const block = run.blocks[nodeId]
    if (!block) return []
    return Object.keys(block.metrics)
  }
}

// ── Store ──────────────────────────────────────────────────────────────────

export const useMetricsStore = create<MetricsStoreState>((set, get) => ({
  runs: {},

  ensureRun: (runId: string) => {
    const { runs } = get()
    if (!runs[runId]) {
      set({ runs: { ...runs, [runId]: defaultRunState() } })
    }
  },

  handleNodeStarted: (runId, data) => {
    set((state) => {
      const runs = ensureRunState(state.runs, runId)
      const run = { ...runs[runId] }
      const nodeId = data.node_id as string

      run.status = 'running'
      run.startedAt = run.startedAt ?? Date.now()
      run.activeBlockId = nodeId

      // Add to execution order if not present
      if (!run.executionOrder.includes(nodeId)) {
        run.executionOrder = [...run.executionOrder, nodeId]
      }

      run.blocks = {
        ...run.blocks,
        [nodeId]: {
          category: data.category ?? 'flow',
          status: 'running',
          progress: 0,
          metrics: run.blocks[nodeId]?.metrics ?? {},
        },
      }

      return { runs: { ...runs, [runId]: run } }
    })
  },

  handleNodeProgress: (runId, data) => {
    set((state) => {
      const runs = ensureRunState(state.runs, runId)
      const run = { ...runs[runId] }
      const nodeId = data.node_id as string
      const existing = run.blocks[nodeId]

      if (existing) {
        run.blocks = {
          ...run.blocks,
          [nodeId]: { ...existing, progress: data.progress ?? existing.progress },
        }
      }
      run.overallProgress = data.overall ?? run.overallProgress
      run.eta = data.eta ?? run.eta

      return { runs: { ...runs, [runId]: run } }
    })
  },

  handleNodeCompleted: (runId, data) => {
    set((state) => {
      const runs = ensureRunState(state.runs, runId)
      const run = { ...runs[runId] }
      const nodeId = data.node_id as string
      const existing = run.blocks[nodeId]

      if (existing) {
        run.blocks = {
          ...run.blocks,
          [nodeId]: { ...existing, status: 'complete', progress: 1 },
        }
      }

      return { runs: { ...runs, [runId]: run } }
    })
  },

  handleNodeFailed: (runId, data) => {
    set((state) => {
      const runs = ensureRunState(state.runs, runId)
      const run = { ...runs[runId] }
      const nodeId = data.node_id as string
      const existing = run.blocks[nodeId]

      if (existing) {
        run.blocks = {
          ...run.blocks,
          [nodeId]: { ...existing, status: 'failed', progress: 0 },
        }
      }

      return { runs: { ...runs, [runId]: run } }
    })
  },

  handleMetric: (runId, data) => {
    set((state) => {
      const runs = ensureRunState(state.runs, runId)
      const run = { ...runs[runId] }
      const nodeId = data.node_id as string
      const name = data.name as string
      const value = data.value as number
      const timestamp = (data.timestamp as number) ?? Date.now() / 1000

      const existing = run.blocks[nodeId] ?? {
        category: data.category ?? 'flow',
        status: 'running',
        progress: 0,
        metrics: {},
      }

      const series = existing.metrics[name] ?? []
      const point: MetricPoint = { value, timestamp }

      run.blocks = {
        ...run.blocks,
        [nodeId]: {
          ...existing,
          metrics: {
            ...existing.metrics,
            [name]: [...series, point],
          },
        },
      }

      return { runs: { ...runs, [runId]: run } }
    })
  },

  handleSystemMetric: (runId, data) => {
    set((state) => {
      const runs = ensureRunState(state.runs, runId)
      const run = { ...runs[runId] }
      const snapshot: SystemMetricSnapshot = {
        timestamp: data.timestamp ?? Date.now() / 1000,
        cpu_pct: data.cpu_pct ?? 0,
        mem_pct: data.mem_pct ?? 0,
        mem_gb: data.mem_gb ?? 0,
        gpu_mem_pct: data.gpu_mem_pct,
      }

      run.systemMetrics = [...run.systemMetrics, snapshot]
      return { runs: { ...runs, [runId]: run } }
    })
  },

  handleRunCompleted: (runId, _data) => {
    set((state) => {
      const runs = ensureRunState(state.runs, runId)
      const run = { ...runs[runId] }
      run.status = 'complete'
      run.overallProgress = 1
      run.activeBlockId = null
      return { runs: { ...runs, [runId]: run } }
    })
  },

  handleRunFailed: (runId, _data) => {
    set((state) => {
      const runs = ensureRunState(state.runs, runId)
      const run = { ...runs[runId] }
      run.status = 'failed'
      run.activeBlockId = null
      return { runs: { ...runs, [runId]: run } }
    })
  },

  handleRunCancelled: (runId) => {
    set((state) => {
      const runs = ensureRunState(state.runs, runId)
      const run = { ...runs[runId] }
      run.status = 'cancelled'
      run.activeBlockId = null
      return { runs: { ...runs, [runId]: run } }
    })
  },

  loadMetricsLog: (runId, events) => {
    set((state) => {
      let runs = ensureRunState(state.runs, runId)
      let run = { ...defaultRunState() }

      for (const evt of events) {
        const type = evt.type ?? evt.event
        switch (type) {
          case 'node_started': {
            const nodeId = evt.node_id
            if (!run.executionOrder.includes(nodeId)) {
              run.executionOrder = [...run.executionOrder, nodeId]
            }
            run.blocks = {
              ...run.blocks,
              [nodeId]: {
                category: evt.category ?? 'flow',
                status: 'running',
                progress: 0,
                metrics: run.blocks[nodeId]?.metrics ?? {},
              },
            }
            run.activeBlockId = nodeId
            run.startedAt = run.startedAt ?? (evt.timestamp ? evt.timestamp * 1000 : Date.now())
            break
          }
          case 'node_completed': {
            const nodeId = evt.node_id
            const existing = run.blocks[nodeId]
            if (existing) {
              run.blocks = {
                ...run.blocks,
                [nodeId]: { ...existing, status: 'complete', progress: 1 },
              }
            }
            break
          }
          case 'metric': {
            const nodeId = evt.node_id
            const name = evt.name as string
            const value = evt.value as number
            const timestamp = evt.timestamp ?? Date.now() / 1000
            const existing = run.blocks[nodeId] ?? {
              category: evt.category ?? 'flow',
              status: 'running',
              progress: 0,
              metrics: {},
            }
            const series = existing.metrics[name] ?? []
            run.blocks = {
              ...run.blocks,
              [nodeId]: {
                ...existing,
                metrics: {
                  ...existing.metrics,
                  [name]: [...series, { value, timestamp }],
                },
              },
            }
            break
          }
          case 'system_metric': {
            run.systemMetrics = [
              ...run.systemMetrics,
              {
                timestamp: evt.timestamp ?? Date.now() / 1000,
                cpu_pct: evt.cpu_pct ?? 0,
                mem_pct: evt.mem_pct ?? 0,
                mem_gb: evt.mem_gb ?? 0,
                gpu_mem_pct: evt.gpu_mem_pct,
              },
            ]
            break
          }
        }
      }

      // Infer final status from block states
      const blockValues = Object.values(run.blocks)
      if (blockValues.some((b) => b.status === 'failed')) {
        run.status = 'failed'
      } else if (blockValues.length > 0 && blockValues.every((b) => b.status === 'complete')) {
        run.status = 'complete'
        run.overallProgress = 1
      } else {
        run.status = 'running'
      }

      return { runs: { ...runs, [runId]: run } }
    })
  },
}))
