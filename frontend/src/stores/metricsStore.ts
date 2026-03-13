import { create } from 'zustand'
import { api } from '@/api/client'
import { useSettingsStore } from './settingsStore'

// ── Per-Run Monitoring Types (Session 4) ────────────────────────────────────

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

// ── Dashboard Types (Session 5) ─────────────────────────────────────────────

export interface RunMetricPoint {
  step: number
  value: number
  timestamp: number
}

export interface RunMetrics {
  runId: string
  loss: RunMetricPoint[]
  accuracy: RunMetricPoint[]
  progress: number
  eta: number | null
  currentBlock: string | null
  status: 'running' | 'complete' | 'failed' | 'pending'
  error?: string
}

export interface DashboardStats {
  total_papers: number
  active_papers: number
  running_now: number
  completed_today: number
  blocked: number
  compute_hours: number
  total_experiments: number
  completed_experiments: number
  running_runs: RunningRun[]
  recent_completed: RecentRun[]
  unassigned_runs: UnassignedRun[]
  ready_to_run: ReadyRun[]
}

export interface RunningRun {
  id: string
  name: string
  project_id: string | null
  paper_number: string | null
  progress: number
  current_block: string | null
  loss_history: number[]
  started_at: string
  eta: number | null
}

export interface RecentRun {
  id: string
  name: string
  project_id: string | null
  paper_number: string | null
  status: 'complete' | 'failed'
  loss: number | null
  accuracy: number | null
  compute_time: number
  completed_at: string
  error?: string
  traceback?: string
}

export interface UnassignedRun {
  id: string
  name: string
  status: string
  loss: number | null
  accuracy: number | null
  completed_at: string | null
}

export interface ReadyRun {
  id: string
  name: string
  project_id: string | null
  paper_number: string | null
  experiment_name: string
  estimated_time: number | null
}

// ── Monitor View Types (Session 6) ──────────────────────────────────────────

/** A single metric event from SSE or historical data */
export interface MetricEvent {
  timestamp: string  // ISO or HH:MM:SS
  blockId: string
  name: string       // e.g. "train/loss", "eval/acc", "benchmark/mmlu/acc"
  value: number
  step?: number
}

/** A pipeline block with its execution status */
export interface BlockStatus {
  id: string
  name: string
  category: string   // training, evaluation, inference, merge, data, etc.
  status: 'queued' | 'running' | 'complete' | 'failed' | 'cancelled'
  progress: number   // 0-1
  startedAt?: string
  finishedAt?: string
  error?: string
}

/** System resource metrics */
export interface SystemMetrics {
  cpu: number         // 0-100
  memory: number      // 0-100
  memoryGB: number
  gpuMemory?: number  // 0-100
  gpuMemoryGB?: number
}

/** Time-series data point for a single metric */
export interface MetricSeries {
  step: number
  value: number
  timestamp: string
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function isDemoMode() {
  return useSettingsStore.getState().demoMode
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

const INITIAL_SYSTEM: SystemMetrics = { cpu: 0, memory: 0, memoryGB: 0 }

/** Stable empty refs for Zustand selectors — avoids infinite re-render from `|| {}` creating new references */
export const EMPTY_BLOCK_METRICS: Record<string, MetricSeries[]> = {}
export const EMPTY_SERIES: MetricSeries[] = []

// ── Demo Data ───────────────────────────────────────────────────────────────

const DEMO_DASHBOARD: DashboardStats = {
  total_papers: 15,
  active_papers: 3,
  running_now: 2,
  completed_today: 5,
  blocked: 1,
  compute_hours: 127.4,
  total_experiments: 215,
  completed_experiments: 47,
  running_runs: [
    {
      id: 'run-3',
      name: 'LoRA r=16 epoch-3',
      project_id: 'demo-proj-1',
      paper_number: 'SL-2025-001',
      progress: 0.65,
      current_block: 'lora-fine-tuning',
      loss_history: [2.1, 1.8, 1.5, 1.3, 1.1, 0.95, 0.82, 0.71, 0.63, 0.58, 0.52, 0.47, 0.43, 0.40, 0.38, 0.36, 0.34, 0.32, 0.31, 0.30, 0.29, 0.28, 0.275, 0.27, 0.268, 0.265, 0.262, 0.260, 0.258, 0.256, 0.255, 0.254, 0.253, 0.252, 0.251, 0.250, 0.249, 0.248, 0.248, 0.247, 0.247, 0.246, 0.246, 0.245, 0.245, 0.244, 0.244, 0.244, 0.243, 0.243],
      started_at: '2025-12-10T08:00:00Z',
      eta: 2400,
    },
    {
      id: 'run-5',
      name: 'RAG eval chunk=512',
      project_id: 'demo-proj-3',
      paper_number: 'SL-2025-003',
      progress: 0.30,
      current_block: 'embedding-generation',
      loss_history: [1.8, 1.6, 1.4, 1.25, 1.15, 1.05, 0.98, 0.92, 0.88, 0.84, 0.81, 0.78, 0.76, 0.74, 0.72],
      started_at: '2025-12-10T09:30:00Z',
      eta: 5400,
    },
  ],
  recent_completed: [
    {
      id: 'run-2',
      name: 'LoRA r=16 epoch-2',
      project_id: 'demo-proj-1',
      paper_number: 'SL-2025-001',
      status: 'complete',
      loss: 0.289,
      accuracy: 0.871,
      compute_time: 2.75,
      completed_at: '2025-12-09T11:45:00Z',
    },
    {
      id: 'run-4',
      name: 'LoRA r=8 epoch-1',
      project_id: 'demo-proj-1',
      paper_number: 'SL-2025-001',
      status: 'failed',
      loss: null,
      accuracy: null,
      compute_time: 0.08,
      completed_at: '2025-12-07T14:05:00Z',
      error: 'CUDA OOM: Tried to allocate 2.4 GiB',
      traceback: 'File "train.py", line 142, in forward\n  output = model(input_ids)\nFile "torch/nn/modules/module.py", line 1532\n  return forward_call(*args)\ntorch.cuda.OutOfMemoryError: CUDA out of memory.',
    },
  ],
  unassigned_runs: [
    {
      id: 'run-orphan-1',
      name: 'quick-test-bert-base',
      status: 'complete',
      loss: 0.412,
      accuracy: 0.823,
      completed_at: '2025-12-09T16:00:00Z',
    },
    {
      id: 'run-orphan-2',
      name: 'ablation-no-dropout',
      status: 'complete',
      loss: 0.378,
      accuracy: 0.841,
      completed_at: '2025-12-08T12:00:00Z',
    },
  ],
  ready_to_run: [
    {
      id: 'ready-1',
      name: 'LoRA r=32 epoch-1',
      project_id: 'demo-proj-1',
      paper_number: 'SL-2025-001',
      experiment_name: 'Higher rank ablation',
      estimated_time: 3.5,
    },
  ],
}

// ── Selectors (Session 4) ───────────────────────────────────────────────────

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

// ── Store State ─────────────────────────────────────────────────────────────

interface MetricsStoreState {
  // Per-run monitoring (Session 4)
  runs: Record<string, RunMonitorState>
  handleNodeStarted: (runId: string, data: any) => void
  handleNodeProgress: (runId: string, data: any) => void
  handleNodeCompleted: (runId: string, data: any) => void
  handleNodeFailed: (runId: string, data: any) => void
  handleMetric: (runId: string, data: any) => void
  handleSystemMetric: (runId: string, data: any) => void
  handleRunCompleted: (runId: string, data: any) => void
  handleRunFailed: (runId: string, data: any) => void
  handleRunCancelled: (runId: string) => void
  loadMetricsLog: (runId: string, events: any[]) => void
  ensureRun: (runId: string) => void

  // Dashboard (Session 5)
  dashboard: DashboardStats | null
  liveMetrics: Record<string, RunMetrics>
  loading: boolean
  error: string | null
  fetchDashboard: () => Promise<void>
  updateRunMetrics: (runId: string, data: Partial<RunMetrics>) => void
  appendLossPoint: (runId: string, point: RunMetricPoint) => void
  assignRunToProject: (runId: string, projectId: string) => Promise<void>
  cancelRun: (runId: string) => Promise<void>
  cloneRun: (runId: string) => Promise<string | null>

  // Monitor View (Session 6)
  monitorRunId: string | null
  pipelineId: string | null
  runName: string | null
  paperId: string | null
  runStatus: 'live' | 'recorded' | 'cancelled' | 'idle'
  startedAt: string | null
  elapsed: number
  monitorEta: number | null
  monitorExecutionOrder: BlockStatus[]
  monitorActiveBlockId: string | null
  viewedBlockId: string | null
  metrics: Record<string, Record<string, MetricSeries[]>>
  metricEvents: MetricEvent[]
  system: SystemMetrics
  systemHistory: { timestamp: string; cpu: number; memory: number; gpuMemory?: number }[]
  configSnapshot: Record<string, any>
  logs: { timestamp: string; blockId: string; message: string; level: 'info' | 'warn' | 'error' }[]
  setRun: (runId: string, pipelineId: string, runName: string, paperId?: string) => void
  setRunStatus: (status: 'live' | 'recorded' | 'cancelled' | 'idle') => void
  setExecutionOrder: (blocks: BlockStatus[]) => void
  updateBlockStatus: (blockId: string, updates: Partial<BlockStatus>) => void
  setActiveBlock: (blockId: string) => void
  setViewedBlock: (blockId: string | null) => void
  pushMetric: (event: MetricEvent) => void
  pushLog: (log: { timestamp: string; blockId: string; message: string; level: 'info' | 'warn' | 'error' }) => void
  updateSystem: (metrics: SystemMetrics) => void
  setConfigSnapshot: (config: Record<string, any>) => void
  setElapsed: (seconds: number) => void
  setMonitorEta: (seconds: number | null) => void
  loadMonitorMetricsLog: (events: MetricEvent[], blocks: BlockStatus[], config?: Record<string, any>) => void
  getBlockMetrics: (blockId: string) => Record<string, MetricSeries[]>
  getBlockEvents: (blockId: string) => MetricEvent[]
  resetMonitor: () => void
}

// ── Store ───────────────────────────────────────────────────────────────────

export const useMetricsStore = create<MetricsStoreState>((set, get) => ({
  // ── Per-run monitoring state (Session 4) ────────────────────────────
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
      const runs = ensureRunState(state.runs, runId)
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

  // ── Dashboard state (Session 5) ────────────────────────────────────
  dashboard: null,
  liveMetrics: {},
  loading: false,
  error: null,

  fetchDashboard: async () => {
    set({ loading: true, error: null })
    if (isDemoMode()) {
      set({ dashboard: DEMO_DASHBOARD, loading: false })
      return
    }
    try {
      const raw = await api.get<any>('/projects/dashboard')
      const data: DashboardStats = {
        total_papers: raw.total_papers ?? 0,
        active_papers: raw.active_papers ?? 0,
        running_now: raw.running_now ?? 0,
        completed_today: raw.completed_today ?? 0,
        blocked: raw.blocked ?? 0,
        compute_hours: raw.compute_hours ?? 0,
        total_experiments: raw.total_experiments ?? 0,
        completed_experiments: raw.completed_experiments ?? 0,
        running_runs: Array.isArray(raw.running_runs) ? raw.running_runs : [],
        recent_completed: Array.isArray(raw.recent_completed) ? raw.recent_completed : [],
        unassigned_runs: Array.isArray(raw.unassigned_runs) ? raw.unassigned_runs : [],
        ready_to_run: Array.isArray(raw.ready_to_run) ? raw.ready_to_run : [],
      }
      set({ dashboard: data, loading: false })
    } catch (e: any) {
      set({ error: e.message, loading: false })
    }
  },

  updateRunMetrics: (runId, data) => {
    set((s) => ({
      liveMetrics: {
        ...s.liveMetrics,
        [runId]: { ...s.liveMetrics[runId], ...data } as RunMetrics,
      },
    }))
  },

  appendLossPoint: (runId, point) => {
    set((s) => {
      const existing = s.liveMetrics[runId]
      if (!existing) return s
      return {
        liveMetrics: {
          ...s.liveMetrics,
          [runId]: {
            ...existing,
            loss: [...existing.loss.slice(-99), point],
          },
        },
      }
    })
  },

  assignRunToProject: async (runId, projectId) => {
    if (isDemoMode()) {
      set((s) => {
        if (!s.dashboard) return s
        return {
          dashboard: {
            ...s.dashboard,
            unassigned_runs: s.dashboard.unassigned_runs.filter((r) => r.id !== runId),
          },
        }
      })
      return
    }
    await api.post(`/runs/${runId}/assign`, { project_id: projectId })
    get().fetchDashboard()
  },

  cancelRun: async (runId) => {
    if (isDemoMode()) {
      set((s) => {
        if (!s.dashboard) return s
        return {
          dashboard: {
            ...s.dashboard,
            running_runs: s.dashboard.running_runs.filter((r) => r.id !== runId),
            running_now: Math.max(0, s.dashboard.running_now - 1),
          },
        }
      })
      return
    }
    await api.post(`/runs/${runId}/cancel`)
    get().fetchDashboard()
  },

  cloneRun: async (runId) => {
    if (isDemoMode()) return `clone-${runId}-${Date.now()}`
    try {
      const result = await api.post<{ id: string }>(`/runs/${runId}/clone`)
      return result.id
    } catch {
      return null
    }
  },

  // ── Monitor View state (Session 6) ─────────────────────────────────
  monitorRunId: null,
  pipelineId: null,
  runName: null,
  paperId: null,
  runStatus: 'idle',
  startedAt: null,
  elapsed: 0,
  monitorEta: null,

  monitorExecutionOrder: [],
  monitorActiveBlockId: null,
  viewedBlockId: null,

  metrics: {},
  metricEvents: [],

  system: INITIAL_SYSTEM,
  systemHistory: [],

  configSnapshot: {},
  logs: [],

  setRun: (runId, pipelineId, runName, paperId) =>
    set({ monitorRunId: runId, pipelineId, runName, paperId: paperId || null, startedAt: new Date().toISOString(), runStatus: 'live' }),

  setRunStatus: (status) => set({ runStatus: status }),

  setExecutionOrder: (blocks) => set({ monitorExecutionOrder: blocks }),

  updateBlockStatus: (blockId, updates) =>
    set((s) => ({
      monitorExecutionOrder: s.monitorExecutionOrder.map((b) =>
        b.id === blockId ? { ...b, ...updates } : b
      ),
    })),

  setActiveBlock: (blockId) =>
    set((s) => ({
      monitorActiveBlockId: blockId,
      viewedBlockId: s.viewedBlockId === s.monitorActiveBlockId || s.viewedBlockId === null ? blockId : s.viewedBlockId,
    })),

  setViewedBlock: (blockId) => set({ viewedBlockId: blockId }),

  pushMetric: (event) =>
    set((s) => {
      const blockMetrics = s.metrics[event.blockId] || {}
      const series = blockMetrics[event.name] || []
      const step = event.step ?? series.length
      const newSeries = [...series, { step, value: event.value, timestamp: event.timestamp }]

      return {
        metrics: {
          ...s.metrics,
          [event.blockId]: {
            ...blockMetrics,
            [event.name]: newSeries,
          },
        },
        metricEvents: [...s.metricEvents, event],
      }
    }),

  pushLog: (log) =>
    set((s) => ({
      logs: [...s.logs.slice(-999), log],
    })),

  updateSystem: (metrics) =>
    set((s) => ({
      system: metrics,
      systemHistory: [
        ...s.systemHistory.slice(-119),
        { timestamp: new Date().toISOString(), cpu: metrics.cpu, memory: metrics.memory, gpuMemory: metrics.gpuMemory },
      ],
    })),

  setConfigSnapshot: (config) => set({ configSnapshot: config }),

  setElapsed: (seconds) => set({ elapsed: seconds }),

  setMonitorEta: (seconds) => set({ monitorEta: seconds }),

  loadMonitorMetricsLog: (events, blocks, config) => {
    const metrics: Record<string, Record<string, MetricSeries[]>> = {}
    for (const event of events) {
      if (!metrics[event.blockId]) metrics[event.blockId] = {}
      if (!metrics[event.blockId][event.name]) metrics[event.blockId][event.name] = []
      const series = metrics[event.blockId][event.name]
      series.push({ step: event.step ?? series.length, value: event.value, timestamp: event.timestamp })
    }
    set({
      metrics,
      metricEvents: events,
      monitorExecutionOrder: blocks,
      configSnapshot: config || {},
      runStatus: 'recorded',
      viewedBlockId: blocks[0]?.id || null,
    })
  },

  getBlockMetrics: (blockId) => get().metrics[blockId] || {},

  getBlockEvents: (blockId) => get().metricEvents.filter((e) => e.blockId === blockId),

  resetMonitor: () =>
    set({
      monitorRunId: null,
      pipelineId: null,
      runName: null,
      paperId: null,
      runStatus: 'idle',
      startedAt: null,
      elapsed: 0,
      monitorEta: null,
      monitorExecutionOrder: [],
      monitorActiveBlockId: null,
      viewedBlockId: null,
      metrics: {},
      metricEvents: [],
      system: INITIAL_SYSTEM,
      systemHistory: [],
      configSnapshot: {},
      logs: [],
    }),
}))
