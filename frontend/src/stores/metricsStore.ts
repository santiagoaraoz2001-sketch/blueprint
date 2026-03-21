import { create } from 'zustand'
import { immer } from 'zustand/middleware/immer'
import { api } from '@/api/client'
import { useSettingsStore } from './settingsStore'

// ── Core Metric Types ───────────────────────────────────────────────────────

export interface MetricPoint {
  step: number
  value: number
  timestamp: number
}

export interface SystemMetricPoint {
  timestamp: number
  cpu: number
  memory: number
  memoryTotal: number
  gpu?: number
  gpuMemory?: number
  gpuMemoryTotal?: number
}

export interface LogEntry {
  timestamp: number
  nodeId: string
  message: string
  level: 'info' | 'warn' | 'error'
}

export interface BlockState {
  nodeId: string
  blockType: string
  category: string
  label: string
  status: 'queued' | 'running' | 'complete' | 'failed'
  progress: number
  error?: string
  index: number
  metrics: Record<string, MetricPoint[]>
  _stepCounters: Record<string, number>
}

export interface RunMonitorData {
  status: 'running' | 'complete' | 'failed'
  blocks: Record<string, BlockState>
  executionOrder: string[]
  activeBlockId: string | null
  systemMetrics: SystemMetricPoint[]
  logs: LogEntry[]
  overallProgress: number
  eta: number | null
  duration: number | null
  totalBlocks: number
  pipelineName: string
  configSnapshot: Record<string, any> | null
  finalMetrics: Record<string, number> | null
}

// ── Per-Run Monitoring Types (Session 4 — kept for backward compat) ─────────

export interface BlockMetrics {
  category: string
  status: 'pending' | 'running' | 'complete' | 'failed'
  progress: number
  metrics: Record<string, MetricPoint[]>
}

export interface SystemMetricSnapshot {
  timestamp: number
  cpu_pct: number
  mem_pct: number
  mem_gb: number
  gpu_mem_pct?: number
}

export interface RunMonitorState {
  blocks: Record<string, BlockMetrics>
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

function createEmptyRun(): RunMonitorData {
  return {
    status: 'running',
    blocks: {},
    executionOrder: [],
    activeBlockId: null,
    systemMetrics: [],
    logs: [],
    overallProgress: 0,
    eta: null,
    duration: null,
    totalBlocks: 0,
    pipelineName: '',
    configSnapshot: null,
    finalMetrics: null,
  }
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

// ── Exported Selectors (Session 4 — work with RunMonitorData.blocks) ────────

export function getActiveBlock(runId: string): (state: MetricsStoreState) => BlockState | null {
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
): (state: MetricsStoreState) => SystemMetricPoint | null {
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
  // Per-run monitoring — unified RunMonitorData (supports both Session 4 handlers and Monitor components)
  runs: Record<string, RunMonitorData>

  // Session 4 handlers (legacy — operate on runs via RunMonitorData)
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

  // Monitor component methods (unified event handler API)
  initRun: (runId: string, opts?: { pipelineName?: string; configSnapshot?: Record<string, any>; blockMeta?: Record<string, { category: string; label: string }> }) => void
  handleEvent: (runId: string, event: string, data: any) => void
  handleEventBatch: (runId: string, events: Array<{event: string, data: any}>) => void
  addSystemMetric: (runId: string, metric: SystemMetricPoint) => void
  loadHistoricalRun: (runId: string, run: any) => void
  removeRun: (runId: string) => void

  // Instance selectors (for Monitor components)
  getMetricSeries: (runId: string, blockId: string, metricName: string) => MetricPoint[]
  getAllMetricNames: (runId: string, blockId: string) => string[]
  getLatestSystemMetrics: (runId: string) => SystemMetricPoint | null
  getActiveBlock: (runId: string) => BlockState | null

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

// ── Helper: apply a single event to a run draft (shared by handleEvent and handleEventBatch) ──

function applyEventToRun(run: RunMonitorData, event: string, data: any): boolean {
  const now = Date.now()

  switch (event) {
    case 'node_started': {
      const nodeId = data.node_id || ''
      const existing = run.blocks[nodeId]
      run.blocks[nodeId] = {
        nodeId,
        blockType: data.block_type || existing?.blockType || '',
        category: existing?.category || 'data',
        label: existing?.label || data.block_type || nodeId,
        status: 'running',
        progress: 0,
        index: data.index ?? existing?.index ?? run.executionOrder.length,
        metrics: existing?.metrics || {},
        _stepCounters: existing?._stepCounters || {},
      }
      if (!run.executionOrder.includes(nodeId)) {
        run.executionOrder.push(nodeId)
      }
      run.activeBlockId = nodeId
      run.totalBlocks = data.total ?? run.totalBlocks
      return true
    }

    case 'node_progress': {
      const nodeId = data.node_id || ''
      const block = run.blocks[nodeId]
      if (!block) return false
      block.progress = data.progress ?? block.progress
      run.overallProgress = data.overall ?? run.overallProgress
      run.eta = data.eta ?? run.eta
      return true
    }

    case 'node_log': {
      const entry: LogEntry = {
        timestamp: now,
        nodeId: data.node_id || '',
        message: data.message || '',
        level: 'info',
      }
      const msg = entry.message.toLowerCase()
      if (msg.includes('error') || msg.includes('exception')) entry.level = 'error'
      else if (msg.includes('warn')) entry.level = 'warn'
      if (run.logs.length > 999) run.logs.splice(0, run.logs.length - 999)
      run.logs.push(entry)
      return true
    }

    case 'metric': {
      const nodeId = data.node_id || ''
      const name: string = data.name || ''
      const value: number = data.value ?? 0
      const block = run.blocks[nodeId]
      if (!block) return false
      if (!block.metrics[name]) block.metrics[name] = []
      if (!block._stepCounters[name]) block._stepCounters[name] = 0
      block._stepCounters[name] += 1
      const stepCounter = block._stepCounters[name]
      const point: MetricPoint = {
        step: data.step ?? stepCounter,
        value,
        timestamp: now,
      }
      // Cap metric series to 10k points to prevent unbounded memory growth
      const maxPoints = 10000
      const series = block.metrics[name]
      if (series.length >= maxPoints) {
        series.splice(0, series.length - maxPoints + 1)
      }
      series.push(point)
      return true
    }

    case 'node_completed': {
      const nodeId = data.node_id || ''
      const block = run.blocks[nodeId]
      if (!block) return false
      block.status = 'complete'
      block.progress = 1
      return true
    }

    case 'node_failed': {
      const nodeId = data.node_id || ''
      const block = run.blocks[nodeId]
      if (!block) return false
      block.status = 'failed'
      block.error = data.error
      return true
    }

    case 'run_completed':
      run.status = 'complete'
      run.overallProgress = 1
      run.duration = data.duration ?? run.duration
      run.finalMetrics = data.metrics ?? run.finalMetrics
      return true

    case 'run_failed':
      run.status = 'failed'
      run.eta = null
      return true

    case 'run_cancelled':
      run.status = 'failed' // RunMonitorData doesn't have 'cancelled', map to 'failed'
      run.eta = null
      run.duration = data.duration ?? run.duration
      return true

    case 'node_cached': {
      const cachedId = data.node_id || ''
      const cachedExisting = run.blocks[cachedId]
      run.blocks[cachedId] = {
        nodeId: cachedId,
        blockType: cachedExisting?.blockType || data.block_type || '',
        category: cachedExisting?.category || data.category || 'data',
        label: cachedExisting?.label || cachedId,
        status: 'complete',
        progress: 1,
        index: cachedExisting?.index ?? data.index ?? run.executionOrder.length,
        metrics: cachedExisting?.metrics || {},
        _stepCounters: cachedExisting?._stepCounters || {},
      }
      if (!run.executionOrder.includes(cachedId)) run.executionOrder.push(cachedId)
      if (data.index != null && data.total) {
        run.overallProgress = (data.index + 1) / data.total
      }
      return true
    }

    case 'node_output': {
      const outputNodeId = data.node_id || ''
      const outputKeys = Object.keys(data.outputs || {}).join(', ')
      const entry: LogEntry = {
        timestamp: now,
        nodeId: outputNodeId,
        message: `[output] ${outputKeys}`,
        level: 'info',
      }
      if (run.logs.length > 999) run.logs.splice(0, run.logs.length - 999)
      run.logs.push(entry)
      return true
    }

    default:
      return false
  }
}

// ── Store ───────────────────────────────────────────────────────────────────

export const useMetricsStore = create<MetricsStoreState>()(immer((set, get) => ({
  // ── Per-run monitoring state ────────────────────────────────────────
  runs: {},

  ensureRun: (runId: string) => {
    const { runs } = get()
    if (!runs[runId]) {
      set((state) => {
        state.runs[runId] = createEmptyRun()
      })
    }
  },

  // ── Session 4 handlers (adapted to work with RunMonitorData/BlockState) ──

  handleNodeStarted: (runId, data) => {
    set((state) => {
      if (!state.runs[runId]) state.runs[runId] = createEmptyRun()
      const run = state.runs[runId]
      const nodeId = data.node_id as string

      run.status = 'running'
      run.activeBlockId = nodeId

      if (!run.executionOrder.includes(nodeId)) {
        run.executionOrder.push(nodeId)
      }

      const existingBlock = run.blocks[nodeId]
      run.blocks[nodeId] = {
        nodeId,
        blockType: existingBlock?.blockType ?? '',
        category: data.category ?? existingBlock?.category ?? 'flow',
        label: existingBlock?.label ?? nodeId,
        status: 'running',
        progress: 0,
        index: existingBlock?.index ?? run.executionOrder.length - 1,
        metrics: existingBlock?.metrics ?? {},
        _stepCounters: existingBlock?._stepCounters ?? {},
      }
    })
  },

  handleNodeProgress: (runId, data) => {
    set((state) => {
      if (!state.runs[runId]) state.runs[runId] = createEmptyRun()
      const run = state.runs[runId]
      const nodeId = data.node_id as string
      const existing = run.blocks[nodeId]

      if (existing) {
        existing.progress = data.progress ?? existing.progress
      }
      run.overallProgress = data.overall ?? run.overallProgress
      run.eta = data.eta ?? run.eta
    })
  },

  handleNodeCompleted: (runId, data) => {
    set((state) => {
      if (!state.runs[runId]) state.runs[runId] = createEmptyRun()
      const run = state.runs[runId]
      const nodeId = data.node_id as string
      const existing = run.blocks[nodeId]

      if (existing) {
        existing.status = 'complete'
        existing.progress = 1
      }
    })
  },

  handleNodeFailed: (runId, data) => {
    set((state) => {
      if (!state.runs[runId]) state.runs[runId] = createEmptyRun()
      const run = state.runs[runId]
      const nodeId = data.node_id as string
      const existing = run.blocks[nodeId]

      if (existing) {
        existing.status = 'failed'
        existing.progress = 0
        existing.error = data.error
      }
    })
  },

  handleMetric: (runId, data) => {
    set((state) => {
      if (!state.runs[runId]) state.runs[runId] = createEmptyRun()
      const run = state.runs[runId]
      const nodeId = data.node_id as string
      const name = data.name as string
      const value = data.value as number
      const timestamp = (data.timestamp as number) ?? Date.now() / 1000

      if (!run.blocks[nodeId]) {
        run.blocks[nodeId] = {
          nodeId,
          blockType: '',
          category: data.category ?? 'flow',
          label: nodeId,
          status: 'running',
          progress: 0,
          index: run.executionOrder.length,
          metrics: {},
          _stepCounters: {},
        }
      }

      const existing = run.blocks[nodeId]
      if (!existing.metrics[name]) existing.metrics[name] = []
      if (!existing._stepCounters[name]) existing._stepCounters[name] = 0
      existing._stepCounters[name] += 1
      const stepCounter = existing._stepCounters[name]
      const point: MetricPoint = { step: data.step ?? stepCounter, value, timestamp }
      existing.metrics[name].push(point)
    })
  },

  handleSystemMetric: (runId, data) => {
    set((state) => {
      if (!state.runs[runId]) state.runs[runId] = createEmptyRun()
      const run = state.runs[runId]
      const metric: SystemMetricPoint = {
        timestamp: data.timestamp ?? Date.now() / 1000,
        cpu: data.cpu_pct ?? 0,
        memory: data.mem_pct ?? 0,
        memoryTotal: data.mem_gb ?? 0,
        gpu: data.gpu_mem_pct,
      }

      // Cap at 300 entries to prevent unbounded growth
      run.systemMetrics.push(metric)
      if (run.systemMetrics.length > 300) run.systemMetrics.splice(0, run.systemMetrics.length - 300)
    })
  },

  handleRunCompleted: (runId, _data) => {
    set((state) => {
      if (!state.runs[runId]) state.runs[runId] = createEmptyRun()
      const run = state.runs[runId]
      run.status = 'complete'
      run.overallProgress = 1
      run.activeBlockId = null
    })
  },

  handleRunFailed: (runId, _data) => {
    set((state) => {
      if (!state.runs[runId]) state.runs[runId] = createEmptyRun()
      const run = state.runs[runId]
      run.status = 'failed'
      run.activeBlockId = null
    })
  },

  handleRunCancelled: (runId) => {
    set((state) => {
      if (!state.runs[runId]) state.runs[runId] = createEmptyRun()
      const run = state.runs[runId]
      run.status = 'failed' // RunMonitorData doesn't have 'cancelled', map to 'failed'
      run.activeBlockId = null
    })
  },

  loadMetricsLog: (runId, events) => {
    set((state) => {
      if (!state.runs[runId]) state.runs[runId] = createEmptyRun()
      const run = createEmptyRun()

      for (const evt of events) {
        const type = evt.type ?? evt.event
        switch (type) {
          case 'node_started': {
            const nodeId = evt.node_id
            if (!run.executionOrder.includes(nodeId)) {
              run.executionOrder.push(nodeId)
            }
            const existingBlock = run.blocks[nodeId]
            run.blocks[nodeId] = {
              nodeId,
              blockType: existingBlock?.blockType ?? '',
              category: evt.category ?? existingBlock?.category ?? 'flow',
              label: existingBlock?.label ?? nodeId,
              status: 'running',
              progress: 0,
              index: existingBlock?.index ?? run.executionOrder.length - 1,
              metrics: existingBlock?.metrics ?? {},
              _stepCounters: existingBlock?._stepCounters ?? {},
            }
            run.activeBlockId = nodeId
            break
          }
          case 'node_completed': {
            const nodeId = evt.node_id
            const existing = run.blocks[nodeId]
            if (existing) {
              existing.status = 'complete'
              existing.progress = 1
            }
            break
          }
          case 'metric': {
            const nodeId = evt.node_id
            const name = evt.name as string
            const value = evt.value as number
            const timestamp = evt.timestamp ?? Date.now() / 1000
            if (!run.blocks[nodeId]) {
              run.blocks[nodeId] = {
                nodeId,
                blockType: '',
                category: evt.category ?? 'flow',
                label: nodeId,
                status: 'running',
                progress: 0,
                index: run.executionOrder.length,
                metrics: {},
                _stepCounters: {},
              }
            }
            const existing = run.blocks[nodeId]
            if (!existing.metrics[name]) existing.metrics[name] = []
            if (!existing._stepCounters[name]) existing._stepCounters[name] = 0
            existing._stepCounters[name] += 1
            const stepCounter = existing._stepCounters[name]
            existing.metrics[name].push({ step: evt.step ?? stepCounter, value, timestamp })
            break
          }
          case 'system_metric': {
            // Cap at 300 entries — parity with addSystemMetric/handleSystemMetric
            run.systemMetrics.push({
              timestamp: evt.timestamp ?? Date.now() / 1000,
              cpu: evt.cpu_pct ?? 0,
              memory: evt.mem_pct ?? 0,
              memoryTotal: evt.mem_gb ?? 0,
              gpu: evt.gpu_mem_pct,
            })
            if (run.systemMetrics.length > 300) run.systemMetrics.splice(0, run.systemMetrics.length - 300)
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

      state.runs[runId] = run
    })
  },

  // ── Monitor component methods (unified event handler API) ──────────

  initRun: (runId, opts) => {
    set((state) => {
      state.runs[runId] = {
        ...createEmptyRun(),
        pipelineName: opts?.pipelineName || '',
        configSnapshot: opts?.configSnapshot || null,
        blocks: opts?.blockMeta
          ? Object.fromEntries(
              Object.entries(opts.blockMeta).map(([nodeId, meta]) => [
                nodeId,
                {
                  nodeId,
                  blockType: '',
                  category: meta.category,
                  label: meta.label,
                  status: 'queued' as const,
                  progress: 0,
                  index: 0,
                  metrics: {},
                  _stepCounters: {},
                },
              ])
            )
          : {},
      }
    })
  },

  handleEvent: (runId, event, data) => {
    set((state) => {
      if (!state.runs[runId]) state.runs[runId] = createEmptyRun()
      applyEventToRun(state.runs[runId], event, data)
    })
  },

  handleEventBatch: (runId, events) => {
    set((state) => {
      if (!state.runs[runId]) state.runs[runId] = createEmptyRun()
      const run = state.runs[runId]
      for (const { event, data } of events) {
        applyEventToRun(run, event, data)
          }
        }
      }
    })
  },

  addSystemMetric: (runId, metric) => {
    set((state) => {
      const run = state.runs[runId]
      if (!run) return
      if (run.systemMetrics.length > 299) {
        run.systemMetrics.splice(0, run.systemMetrics.length - 299)
      }
      run.systemMetrics.push(metric)
    })
  },

  loadHistoricalRun: (runId, runData) => {
    set((state) => {
      const existing = state.runs[runId]
      // Don't overwrite a run that has active live metric data
      if (existing && existing.status === 'running' && Object.keys(existing.blocks).some(
        (id) => Object.keys(existing.blocks[id].metrics).length > 0
      )) return

      const configSnapshot = runData.config_snapshot || {}
      const nodes: any[] = configSnapshot.nodes || []
      const blocks: Record<string, BlockState> = {}
      const executionOrder: string[] = []

      nodes.forEach((node: any, i: number) => {
        const nodeId = node.id || node.node_id || `node-${i}`
        const data = node.data || {}
        executionOrder.push(nodeId)
        blocks[nodeId] = {
          nodeId,
          blockType: data.type || '',
          category: data.category || 'data',
          label: data.label || data.type || nodeId,
          status: runData.status === 'complete' ? 'complete' : runData.status === 'failed' ? 'failed' : 'queued',
          progress: runData.status === 'complete' ? 1 : 0,
          index: i,
          metrics: {},
          _stepCounters: {},
        }
      })

      // Load final metrics into the first training/relevant block or all blocks
      const finalMetrics = runData.metrics || {}
      if (Object.keys(finalMetrics).length > 0) {
        for (const [metricName, value] of Object.entries(finalMetrics)) {
          if (typeof value !== 'number') continue
          const targetId = executionOrder[0]
          if (targetId && blocks[targetId]) {
            blocks[targetId].metrics[metricName] = [
              { step: 1, value, timestamp: Date.now() },
            ]
          }
        }
      }

      state.runs[runId] = {
        status: runData.status === 'complete' ? 'complete' : runData.status === 'failed' ? 'failed' : 'running',
        blocks,
        executionOrder,
        activeBlockId: null,
        systemMetrics: [],
        logs: [],
        overallProgress: runData.status === 'complete' ? 1 : 0,
        eta: null,
        duration: runData.duration_seconds ?? null,
        totalBlocks: nodes.length,
        pipelineName: configSnapshot.name || '',
        configSnapshot,
        finalMetrics: Object.keys(finalMetrics).length > 0 ? finalMetrics as Record<string, number> : null,
      }
    })
  },

  removeRun: (runId) => {
    set((state) => {
      delete state.runs[runId]
    })
  },

  // ── Instance selectors (for Monitor components) ────────────────────

  getMetricSeries: (runId, blockId, metricName) => {
    const run = get().runs[runId]
    return run?.blocks[blockId]?.metrics[metricName] || []
  },

  getAllMetricNames: (runId, blockId) => {
    const run = get().runs[runId]
    const block = run?.blocks[blockId]
    return block ? Object.keys(block.metrics) : []
  },

  getLatestSystemMetrics: (runId) => {
    const run = get().runs[runId]
    if (!run || run.systemMetrics.length === 0) return null
    return run.systemMetrics[run.systemMetrics.length - 1]
  },

  getActiveBlock: (runId) => {
    const run = get().runs[runId]
    if (!run || !run.activeBlockId) return null
    return run.blocks[run.activeBlockId] || null
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
    set((state) => {
      state.liveMetrics[runId] = { ...state.liveMetrics[runId], ...data } as RunMetrics
    })
  },

  appendLossPoint: (runId, point) => {
    set((state) => {
      const existing = state.liveMetrics[runId]
      if (!existing) return
      if (existing.loss.length > 99) {
        existing.loss.splice(0, existing.loss.length - 99)
      }
      existing.loss.push(point)
    })
  },

  assignRunToProject: async (runId, projectId) => {
    if (isDemoMode()) {
      set((state) => {
        if (!state.dashboard) return
        state.dashboard.unassigned_runs = state.dashboard.unassigned_runs.filter((r) => r.id !== runId)
      })
      return
    }
    await api.post(`/runs/${runId}/assign`, { project_id: projectId })
    get().fetchDashboard()
  },

  cancelRun: async (runId) => {
    if (isDemoMode()) {
      set((state) => {
        if (!state.dashboard) return
        state.dashboard.running_runs = state.dashboard.running_runs.filter((r) => r.id !== runId)
        state.dashboard.running_now = Math.max(0, state.dashboard.running_now - 1)
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
    set((state) => {
      const block = state.monitorExecutionOrder.find((b) => b.id === blockId)
      if (block) Object.assign(block, updates)
    }),

  setActiveBlock: (blockId) =>
    set((state) => {
      state.monitorActiveBlockId = blockId
      if (state.viewedBlockId === state.monitorActiveBlockId || state.viewedBlockId === null) {
        state.viewedBlockId = blockId
      }
    }),

  setViewedBlock: (blockId) => set({ viewedBlockId: blockId }),

  pushMetric: (event) =>
    set((state) => {
      if (!state.metrics[event.blockId]) state.metrics[event.blockId] = {}
      const blockMetrics = state.metrics[event.blockId]
      if (!blockMetrics[event.name]) blockMetrics[event.name] = []
      const series = blockMetrics[event.name]
      const step = event.step ?? series.length
      series.push({ step, value: event.value, timestamp: event.timestamp })
      state.metricEvents.push(event)
    }),

  pushLog: (log) =>
    set((state) => {
      if (state.logs.length > 999) state.logs.splice(0, state.logs.length - 999)
      state.logs.push(log)
    }),

  updateSystem: (metrics) =>
    set((state) => {
      state.system = metrics
      if (state.systemHistory.length > 119) {
        state.systemHistory.splice(0, state.systemHistory.length - 119)
      }
      state.systemHistory.push({
        timestamp: new Date().toISOString(),
        cpu: metrics.cpu,
        memory: metrics.memory,
        gpuMemory: metrics.gpuMemory,
      })
    }),

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
})))
