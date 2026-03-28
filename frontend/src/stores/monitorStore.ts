/**
 * Monitor Store — tracks execution timeline and log data from SSE events.
 *
 * Provides data for ExecutionTimeline (Gantt chart), LogViewer, and
 * the bottom monitor tab bar during pipeline runs.
 */
import { create } from 'zustand'
import { sseManager } from '@/services/sseManager'

// ── Timeline Types ────────────────────────────────────────────────────

export interface TimelineBlock {
  nodeId: string
  blockType: string
  category: string
  label: string
  index: number
  total: number
  status: 'pending' | 'running' | 'complete' | 'failed' | 'cached'
  startTime: number      // wall-clock ms since epoch
  endTime: number | null  // null while running
  durationMs: number | null
  primaryOutputType?: string | null
  artifactCount?: number
}

// ── Log Types ─────────────────────────────────────────────────────────

export type LogSeverity = 'debug' | 'info' | 'warn' | 'error'

export interface LogLine {
  timestamp: number    // wall-clock ms since epoch
  nodeId: string
  nodeName: string     // human-readable label from the block
  severity: LogSeverity
  message: string
}

// ── Store Shape ───────────────────────────────────────────────────────

interface MonitorState {
  // Per-run data keyed by runId
  runId: string | null
  runStartTime: number | null
  runStatus: 'idle' | 'running' | 'complete' | 'failed' | 'cancelled'
  blocks: Record<string, TimelineBlock>
  executionOrder: string[]
  logs: LogLine[]
  activeTab: 'timeline' | 'logs' | 'outputs'

  // SSE subscription
  _unsubscribe: (() => void) | null

  // Actions
  startMonitoring: (runId: string, nodeLabels?: Record<string, string>) => void
  stopMonitoring: () => void
  setActiveTab: (tab: 'timeline' | 'logs' | 'outputs') => void
  reset: () => void
}

const MAX_LOG_LINES = 5000

export const useMonitorStore = create<MonitorState>((set, get) => ({
  runId: null,
  runStartTime: null,
  runStatus: 'idle',
  blocks: {},
  executionOrder: [],
  logs: [],
  activeTab: 'timeline',
  _unsubscribe: null,

  startMonitoring: (runId: string, nodeLabels?: Record<string, string>) => {
    // Clean up previous subscription
    const { _unsubscribe } = get()
    if (_unsubscribe) _unsubscribe()

    set({
      runId,
      runStartTime: Date.now(),
      runStatus: 'running',
      blocks: {},
      executionOrder: [],
      logs: [],
    })

    const unsubscribe = sseManager.subscribe(runId, (event, data) => {
      const state = get()
      const now = Date.now()

      switch (event) {
        case 'node_started': {
          const nodeId = data.node_id || ''
          const label = nodeLabels?.[nodeId] || data.block_type || nodeId
          const block: TimelineBlock = {
            nodeId,
            blockType: data.block_type || '',
            category: data.category || '',
            label,
            index: data.index ?? Object.keys(state.blocks).length,
            total: data.total ?? 0,
            status: 'running',
            startTime: now,
            endTime: null,
            durationMs: null,
          }
          set({
            blocks: { ...state.blocks, [nodeId]: block },
            executionOrder: state.executionOrder.includes(nodeId)
              ? state.executionOrder
              : [...state.executionOrder, nodeId],
          })
          break
        }

        case 'node_completed': {
          const nodeId = data.node_id || ''
          const existing = state.blocks[nodeId]
          if (existing) {
            set({
              blocks: {
                ...state.blocks,
                [nodeId]: {
                  ...existing,
                  status: 'complete',
                  endTime: now,
                  durationMs: data.duration_ms ?? (now - existing.startTime),
                  primaryOutputType: data.primary_output_type,
                  artifactCount: data.artifact_count,
                },
              },
            })
          }
          break
        }

        case 'node_failed': {
          const nodeId = data.node_id || ''
          const existing = state.blocks[nodeId]
          if (existing) {
            set({
              blocks: {
                ...state.blocks,
                [nodeId]: {
                  ...existing,
                  status: 'failed',
                  endTime: now,
                  durationMs: now - existing.startTime,
                },
              },
            })
          }
          break
        }

        case 'node_cached': {
          const nodeId = data.node_id || ''
          const label = nodeLabels?.[nodeId] || data.block_type || nodeId
          set({
            blocks: {
              ...state.blocks,
              [nodeId]: {
                nodeId,
                blockType: data.block_type || '',
                category: data.category || '',
                label,
                index: data.index ?? Object.keys(state.blocks).length,
                total: 0,
                status: 'cached',
                startTime: now,
                endTime: now,
                durationMs: 0,
              },
            },
            executionOrder: state.executionOrder.includes(nodeId)
              ? state.executionOrder
              : [...state.executionOrder, nodeId],
          })
          break
        }

        case 'node_log': {
          const nodeId = data.node_id || ''
          const blockLabel = state.blocks[nodeId]?.label || nodeLabels?.[nodeId] || nodeId
          const line: LogLine = {
            timestamp: now,
            nodeId,
            nodeName: blockLabel,
            severity: (data.severity as LogSeverity) || 'info',
            message: data.message || '',
          }
          const newLogs = state.logs.length >= MAX_LOG_LINES
            ? [...state.logs.slice(state.logs.length - MAX_LOG_LINES + 1), line]
            : [...state.logs, line]
          set({ logs: newLogs })
          break
        }

        case 'run_completed':
          set({ runStatus: 'complete' })
          break

        case 'run_failed':
          set({ runStatus: 'failed' })
          break

        case 'run_cancelled':
          set({ runStatus: 'cancelled' })
          break
      }
    })

    set({ _unsubscribe: unsubscribe })
  },

  stopMonitoring: () => {
    const { _unsubscribe } = get()
    if (_unsubscribe) _unsubscribe()
    set({ _unsubscribe: null })
  },

  setActiveTab: (tab) => set({ activeTab: tab }),

  reset: () => {
    const { _unsubscribe } = get()
    if (_unsubscribe) _unsubscribe()
    set({
      runId: null,
      runStartTime: null,
      runStatus: 'idle',
      blocks: {},
      executionOrder: [],
      logs: [],
      activeTab: 'timeline',
      _unsubscribe: null,
    })
  },
}))
