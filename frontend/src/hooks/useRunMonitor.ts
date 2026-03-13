import { useEffect, useRef, useCallback } from 'react'
import { useSSE } from './useSSE'
import { useMetricsStore, type MetricEvent, type BlockStatus } from '@/stores/metricsStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { api } from '@/api/client'

// ── Per-Run Monitor (Session 4) ─────────────────────────────────────────────

interface UseRunMonitorResult {
  isConnected: boolean
  activeBlock: string | null
  overallProgress: number
  eta: number | null
  status: 'idle' | 'running' | 'complete' | 'failed' | 'cancelled'
}

/**
 * Subscribes to SSE for a run and routes events to the metricsStore.
 * Does NOT clear the store on unmount (data persists for replay).
 */
export function useRunMonitor(runId: string | null): UseRunMonitorResult {
  const isConnectedRef = useRef(false)
  const notificationPermissionRequested = useRef(false)

  const store = useMetricsStore

  // Ensure run state exists
  useEffect(() => {
    if (runId) {
      store.getState().ensureRun(runId)
    }
  }, [runId])

  // Request notification permission on first pipeline start
  useEffect(() => {
    if (
      runId &&
      !notificationPermissionRequested.current &&
      typeof Notification !== 'undefined' &&
      Notification.permission === 'default'
    ) {
      notificationPermissionRequested.current = true
      Notification.requestPermission()
    }
  }, [runId])

  const handleEvent = useCallback(
    (event: string, data: any) => {
      if (!runId) return
      isConnectedRef.current = true

      const s = store.getState()

      switch (event) {
        case 'node_started':
          s.handleNodeStarted(runId, data)
          break
        case 'node_progress':
          s.handleNodeProgress(runId, data)
          break
        case 'node_completed':
          s.handleNodeCompleted(runId, data)
          break
        case 'node_failed':
          s.handleNodeFailed(runId, data)
          break
        case 'metric':
          s.handleMetric(runId, data)
          break
        case 'system_metric':
          s.handleSystemMetric(runId, data)
          break
        case 'run_completed':
          s.handleRunCompleted(runId, data)
          // Desktop notification
          if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            new Notification('Experiment Complete', {
              body: `Run ${runId.slice(0, 8)} finished in ${data.duration ? Math.round(data.duration) + 's' : 'unknown time'}`,
              tag: runId,
            })
          }
          break
        case 'run_failed':
          s.handleRunFailed(runId, data)
          // Desktop notification
          if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
            new Notification('Experiment Failed', {
              body: `Run ${runId.slice(0, 8)} failed: ${data.error ?? 'unknown error'}`,
              tag: runId,
            })
          }
          break
        case 'run_cancelled':
          s.handleRunCancelled(runId)
          break
      }
    },
    [runId],
  )

  const handleError = useCallback(() => {
    isConnectedRef.current = false
  }, [])

  const url = runId ? `/api/events/runs/${runId}` : null

  useSSE(url, {
    onEvent: handleEvent,
    onError: handleError,
    enabled: !!runId,
  })

  // Read from store reactively
  const runState = useMetricsStore((s) => (runId ? s.runs[runId] : null))

  return {
    isConnected: isConnectedRef.current,
    activeBlock: runState?.activeBlockId ?? null,
    overallProgress: runState?.overallProgress ?? 0,
    eta: runState?.eta ?? null,
    status: runState?.status ?? 'idle',
  }
}

// ── Dashboard Monitor (Session 5) ───────────────────────────────────────────

interface UseDashboardMonitorOptions {
  enabled?: boolean
}

/**
 * Subscribes to the global SSE stream for run events.
 * Updates metricsStore with live progress, metrics, and status changes.
 * Triggers dashboard re-fetch on run_completed / run_failed.
 */
export function useDashboardMonitor(options: UseDashboardMonitorOptions = {}) {
  const { enabled = true } = options
  const updateRunMetrics = useMetricsStore((s) => s.updateRunMetrics)
  const fetchDashboard = useMetricsStore((s) => s.fetchDashboard)

  const handleEvent = useCallback(
    (event: string, data: any) => {
      const runId = data.run_id
      if (!runId) return

      switch (event) {
        case 'run_started':
          updateRunMetrics(runId, {
            runId,
            status: 'running',
            progress: 0,
            eta: data.eta ?? null,
            currentBlock: data.block_name ?? null,
            loss: [],
            accuracy: [],
          })
          break

        case 'node_started':
          updateRunMetrics(runId, {
            runId,
            currentBlock: data.block_name ?? data.node_id ?? null,
          })
          break

        case 'node_progress':
        case 'run_progress':
          updateRunMetrics(runId, {
            runId,
            progress: data.progress ?? data.overall ?? 0,
            eta: data.eta ?? null,
            currentBlock: data.block_name ?? data.node_id ?? null,
            status: 'running',
          })
          break

        case 'metric': {
          const store = useMetricsStore.getState()
          const existing = store.liveMetrics[runId]
          if (data.name === 'loss' && existing) {
            store.appendLossPoint(runId, {
              step: data.step ?? (existing.loss?.length ?? 0),
              value: data.value,
              timestamp: Date.now(),
            })
          }
          break
        }

        case 'run_completed':
          updateRunMetrics(runId, {
            runId,
            status: 'complete',
            progress: 1,
            eta: 0,
          })
          fetchDashboard()
          break

        case 'run_failed':
          updateRunMetrics(runId, {
            runId,
            status: 'failed',
            error: data.error,
          })
          fetchDashboard()
          break
      }
    },
    [updateRunMetrics, fetchDashboard]
  )

  const sseUrl = enabled ? '/api/runs/stream' : null

  return useSSE(sseUrl, {
    onEvent: handleEvent,
    enabled,
  })
}

// ── Monitor View Hook (Session 6) ───────────────────────────────────────────

/**
 * Connects to a run's SSE stream and populates metricsStore monitor state.
 * Handles live monitoring + elapsed timer + demo mode simulation.
 */
export function useMonitorView(runId: string | null) {
  const store = useMetricsStore
  const elapsedRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const demoTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const isDemoMode = useSettingsStore.getState().demoMode

  const handleSSEEvent = useCallback((event: string, data: any) => {
    const s = store.getState()
    const ts = new Date().toISOString().slice(11, 19) // HH:MM:SS

    switch (event) {
      case 'run_started':
        store.getState().setRun(data.run_id, data.pipeline_id, data.run_name || 'Run', data.paper_id)
        if (data.config_snapshot) {
          store.getState().setConfigSnapshot(data.config_snapshot)
        }
        if (data.blocks) {
          store.getState().setExecutionOrder(
            data.blocks.map((b: any) => ({
              id: b.id,
              name: b.name || b.id,
              category: b.category || 'default',
              status: 'queued' as const,
              progress: 0,
            }))
          )
        }
        break

      case 'node_started':
        store.getState().updateBlockStatus(data.node_id, {
          status: 'running',
          startedAt: new Date().toISOString(),
        })
        store.getState().setActiveBlock(data.node_id)
        store.getState().pushLog({ timestamp: ts, blockId: data.node_id, message: `Block started: ${data.node_id}`, level: 'info' })
        break

      case 'node_progress':
        store.getState().updateBlockStatus(data.node_id, { progress: data.progress || 0 })
        if (data.eta != null) store.getState().setMonitorEta(data.eta)
        break

      case 'node_completed':
        store.getState().updateBlockStatus(data.node_id, {
          status: 'complete',
          progress: 1,
          finishedAt: new Date().toISOString(),
        })
        store.getState().pushLog({ timestamp: ts, blockId: data.node_id, message: `Block completed: ${data.node_id}`, level: 'info' })
        break

      case 'node_failed':
        store.getState().updateBlockStatus(data.node_id, {
          status: 'failed',
          progress: 0,
          error: data.error,
          finishedAt: new Date().toISOString(),
        })
        store.getState().pushLog({ timestamp: ts, blockId: data.node_id, message: `Block failed: ${data.error || data.node_id}`, level: 'error' })
        break

      case 'metric': {
        const metricEvent: MetricEvent = {
          timestamp: ts,
          blockId: data.node_id || s.monitorActiveBlockId || '',
          name: data.name,
          value: data.value,
          step: data.step,
        }
        store.getState().pushMetric(metricEvent)
        break
      }

      case 'node_log':
        store.getState().pushLog({
          timestamp: ts,
          blockId: data.node_id || s.monitorActiveBlockId || '',
          message: data.message,
          level: data.level || 'info',
        })
        break

      case 'system_metrics':
        store.getState().updateSystem({
          cpu: data.cpu ?? 0,
          memory: data.memory ?? 0,
          memoryGB: data.memory_gb ?? 0,
          gpuMemory: data.gpu_memory,
          gpuMemoryGB: data.gpu_memory_gb,
        })
        break

      case 'run_completed':
        store.getState().setRunStatus('recorded')
        store.getState().pushLog({ timestamp: ts, blockId: '', message: 'Run completed', level: 'info' })
        break

      case 'run_failed':
        store.getState().setRunStatus('cancelled')
        store.getState().pushLog({ timestamp: ts, blockId: '', message: `Run failed: ${data.error || 'unknown'}`, level: 'error' })
        break
    }
  }, [])

  // SSE connection for live runs
  const sseUrl = runId && !isDemoMode ? `/api/events/runs/${runId}` : null
  useSSE(sseUrl, {
    onEvent: handleSSEEvent,
    enabled: !!runId && !isDemoMode,
  })

  // Elapsed timer
  useEffect(() => {
    if (!runId) return
    const start = Date.now()
    elapsedRef.current = setInterval(() => {
      const state = store.getState()
      if (state.runStatus === 'live') {
        store.getState().setElapsed(Math.floor((Date.now() - start) / 1000))
      }
    }, 1000)
    return () => {
      if (elapsedRef.current) clearInterval(elapsedRef.current)
    }
  }, [runId])

  // Demo mode simulation
  useEffect(() => {
    if (!runId || !isDemoMode) return

    const demoBlocks: BlockStatus[] = [
      { id: 'data-loader', name: 'Data Loader', category: 'data', status: 'queued', progress: 0 },
      { id: 'tokenizer', name: 'Tokenizer', category: 'data', status: 'queued', progress: 0 },
      { id: 'training', name: 'Fine-Tuning', category: 'training', status: 'queued', progress: 0 },
      { id: 'eval-mmlu', name: 'MMLU Eval', category: 'evaluation', status: 'queued', progress: 0 },
      { id: 'eval-hellaswag', name: 'HellaSwag', category: 'evaluation', status: 'queued', progress: 0 },
      { id: 'merge', name: 'Model Merge', category: 'merge', status: 'queued', progress: 0 },
      { id: 'deploy', name: 'Deploy', category: 'inference', status: 'queued', progress: 0 },
    ]

    // Batch all initialization into a single set() to avoid cascading re-renders
    const initBlocks = demoBlocks.map((b, i) =>
      i === 0 ? { ...b, status: 'running' as const, startedAt: new Date().toISOString() } : b
    )
    store.setState({
      monitorRunId: runId,
      pipelineId: 'demo-pipeline',
      runName: 'Demo Training Run',
      paperId: 'paper-1',
      startedAt: new Date().toISOString(),
      runStatus: 'live',
      monitorExecutionOrder: initBlocks,
      monitorActiveBlockId: demoBlocks[0].id,
      viewedBlockId: demoBlocks[0].id,
      configSnapshot: {
        model: { name: 'llama-3.1-8b', quantization: 'none' },
        training: { learning_rate: 2e-4, batch_size: 8, epochs: 3, warmup_steps: 100 },
        optimizer: { type: 'adamw', weight_decay: 0.01, beta1: 0.9, beta2: 0.999 },
        data: { dataset: 'custom-instruct-50k', max_length: 2048 },
      },
    })

    let step = 0
    let currentBlock = 0
    const ts = () => new Date().toISOString().slice(11, 19)

    demoTimerRef.current = setInterval(() => {
      const block = demoBlocks[currentBlock]
      if (!block) {
        store.setState({ runStatus: 'recorded' })
        if (demoTimerRef.current) clearInterval(demoTimerRef.current)
        return
      }

      step++
      const now = ts()

      // Collect new metric events to batch
      const newEvents: MetricEvent[] = []

      if (block.category === 'training') {
        const loss = 2.5 * Math.exp(-step * 0.015) + 0.1 + (Math.random() - 0.5) * 0.05
        const lr = step < 100 ? (2e-4 * step) / 100 : 2e-4 * Math.max(0.1, 1 - (step - 100) / 300)
        newEvents.push({ timestamp: now, blockId: block.id, name: 'train/loss', value: parseFloat(loss.toFixed(4)), step })
        newEvents.push({ timestamp: now, blockId: block.id, name: 'train/lr', value: parseFloat(lr.toExponential(2)), step })
        if (step % 20 === 0) {
          const evalLoss = loss * 1.1 + (Math.random() - 0.5) * 0.08
          newEvents.push({ timestamp: now, blockId: block.id, name: 'eval/loss', value: parseFloat(evalLoss.toFixed(4)), step })
        }
      } else if (block.category === 'evaluation') {
        if (step % 8 === 0) {
          const benchmarks = ['mmlu', 'hellaswag', 'arc', 'truthfulqa', 'winogrande', 'gsm8k', 'humaneval', 'mbpp']
          const idx = Math.floor(step / 8) % benchmarks.length
          const score = 0.5 + Math.random() * 0.4
          newEvents.push({ timestamp: now, blockId: block.id, name: `benchmark/${benchmarks[idx]}/acc`, value: parseFloat(score.toFixed(3)), step: idx })
        }
      } else if (block.category === 'inference') {
        newEvents.push({ timestamp: now, blockId: block.id, name: 'tokens/sec', value: parseFloat((45 + Math.random() * 20).toFixed(1)), step })
      } else if (block.category === 'data') {
        newEvents.push({ timestamp: now, blockId: block.id, name: 'rows_processed', value: step * 1000, step })
      } else if (block.category === 'merge') {
        newEvents.push({ timestamp: now, blockId: block.id, name: 'layer', value: Math.min(step, 32), step })
      }

      // Block progress and transition
      const blockDuration = block.category === 'training' ? 60 : block.category === 'evaluation' ? 30 : 15
      const blockProgress = Math.min(1, step / blockDuration)
      const blockCompleted = blockProgress >= 1

      // System metrics
      const newSystem = {
        cpu: 40 + Math.random() * 40,
        memory: 55 + Math.random() * 25,
        memoryGB: 12.4 + Math.random() * 4,
        gpuMemory: block.category === 'training' ? 70 + Math.random() * 25 : 30 + Math.random() * 20,
        gpuMemoryGB: block.category === 'training' ? 18 + Math.random() * 4 : 8 + Math.random() * 5,
      }

      // SINGLE batched store update per tick
      store.setState((s) => {
        // Build updated metrics
        const metrics = { ...s.metrics }
        const metricEvents = [...s.metricEvents]
        for (const evt of newEvents) {
          if (!metrics[evt.blockId]) metrics[evt.blockId] = {}
          const series = metrics[evt.blockId][evt.name] || []
          const evtStep = evt.step ?? series.length
          metrics[evt.blockId] = {
            ...metrics[evt.blockId],
            [evt.name]: [...series, { step: evtStep, value: evt.value, timestamp: evt.timestamp }],
          }
          metricEvents.push(evt)
        }

        // Build updated execution order
        let monitorExecutionOrder = s.monitorExecutionOrder.map((b) =>
          b.id === block.id ? { ...b, progress: blockProgress } : b
        )

        // Build updated logs
        const logs = step % 3 === 0
          ? [...s.logs.slice(-999), { timestamp: now, blockId: block.id, message: `Processing step ${step}...`, level: 'info' as const }]
          : s.logs

        // System history
        const systemHistory = [
          ...s.systemHistory.slice(-119),
          { timestamp: now, cpu: newSystem.cpu, memory: newSystem.memory, gpuMemory: newSystem.gpuMemory },
        ]

        let monitorActiveBlockId = s.monitorActiveBlockId
        let viewedBlockId = s.viewedBlockId
        let runStatus = s.runStatus

        if (blockCompleted) {
          monitorExecutionOrder = monitorExecutionOrder.map((b) =>
            b.id === block.id ? { ...b, status: 'complete' as const, progress: 1, finishedAt: new Date().toISOString() } : b
          )
          currentBlock++
          step = 0
          if (currentBlock < demoBlocks.length) {
            const nextBlock = demoBlocks[currentBlock]
            monitorExecutionOrder = monitorExecutionOrder.map((b) =>
              b.id === nextBlock.id ? { ...b, status: 'running' as const, startedAt: new Date().toISOString() } : b
            )
            monitorActiveBlockId = nextBlock.id
            if (viewedBlockId === block.id || viewedBlockId === s.monitorActiveBlockId) {
              viewedBlockId = nextBlock.id
            }
          } else {
            runStatus = 'recorded'
            if (demoTimerRef.current) clearInterval(demoTimerRef.current)
          }
        }

        return {
          metrics,
          metricEvents,
          monitorExecutionOrder,
          logs,
          system: newSystem,
          systemHistory,
          monitorActiveBlockId,
          viewedBlockId,
          runStatus,
        }
      })
    }, 300)

    return () => {
      if (demoTimerRef.current) clearInterval(demoTimerRef.current)
    }
  }, [runId, isDemoMode])

  // Load historical data
  const loadHistoricalRun = useCallback(async (historicalRunId: string) => {
    try {
      const run = await api.get<any>(`/runs/${historicalRunId}`)
      const metricsLog = await api.get<any>(`/runs/${historicalRunId}/metrics-log`)

      const events: MetricEvent[] = (metricsLog.events || []).map((e: any) => ({
        timestamp: e.timestamp,
        blockId: e.block_id || e.node_id || '',
        name: e.name,
        value: e.value,
        step: e.step,
      }))

      const blocks: BlockStatus[] = (metricsLog.blocks || run.blocks || []).map((b: any) => ({
        id: b.id,
        name: b.name || b.id,
        category: b.category || 'default',
        status: b.status || 'complete',
        progress: 1,
      }))

      store.getState().setRun(historicalRunId, run.pipeline_id, run.name || 'Run', run.paper_id)
      store.getState().loadMonitorMetricsLog(events, blocks, run.config_snapshot)
    } catch {
      // If metrics-log endpoint doesn't exist, load basic run data
      try {
        const run = await api.get<any>(`/runs/${historicalRunId}`)
        store.getState().setRun(historicalRunId, run.pipeline_id, 'Run', undefined)
        store.getState().setRunStatus('recorded')
        if (run.config_snapshot) store.getState().setConfigSnapshot(run.config_snapshot)
      } catch {
        // Silently fail for historical loads
      }
    }
  }, [])

  return { loadHistoricalRun }
}
