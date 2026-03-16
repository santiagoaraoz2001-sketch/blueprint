import { create } from 'zustand'
import { sseManager } from '@/services/sseManager'
import { api } from '@/api/client'

// ── Types ────────────────────────────────────────────────────────────────────

export type OutputCategory =
  | 'inference' | 'agents' | 'training' | 'merge'
  | 'flow' | 'data' | 'error' | 'system' | 'unknown'

export type EntryType = 'text' | 'log' | 'metric' | 'iteration'

export interface OutputEntry {
  id: string
  timestamp: number
  nodeId: string
  blockType: string
  category: OutputCategory
  entryType: EntryType
  content: string
  metadata?: Record<string, any>
}

export interface InferenceMetrics {
  latencyMs: number
  totalTokens: number
  tokensPerSecond: number
}

export interface TrainingMetrics {
  loss: number | null
  learningRate: number | null
  step: number
  totalSteps: number
  epoch: number
}

export interface HardwareMetrics {
  cpuPercent: number
  memPercent: number
  memGb: number
  gpuPercent: number | null
}

// ── Constants ────────────────────────────────────────────────────────────────

const MAX_ENTRIES = 10_000
const HW_POLL_INTERVAL_MS = 5_000

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatNodeOutput(data: any): string {
  if (!data.outputs) return JSON.stringify(data, null, 2)

  const textKeys = ['response', 'text', 'output', 'consensus']
  for (const key of textKeys) {
    if (data.outputs[key]) {
      const val = data.outputs[key]
      if (typeof val === 'string') return val
      if (typeof val === 'object') return JSON.stringify(val, null, 2)
    }
  }

  return JSON.stringify(data.outputs, null, 2)
}

function inferCategory(blockType: string): OutputCategory {
  const categoryMap: Record<string, OutputCategory> = {
    llm_inference: 'inference', chat_completion: 'inference',
    batch_inference: 'inference', prompt_chain: 'inference',
    chain_of_thought: 'agents', multi_agent_debate: 'agents',
    agent_orchestrator: 'agents', code_agent: 'agents',
    lora_finetuning: 'training', ballast_training: 'training',
    full_finetuning: 'training', continued_pretraining: 'training',
    slerp_merge: 'merge', ties_merge: 'merge', dare_merge: 'merge',
    loop_controller: 'flow',
  }
  return categoryMap[blockType] || 'data'
}

export function formatDuration(seconds: number): string {
  if (seconds < 0) return '--'
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}

function computeEta(elapsed: number, progress: number): string {
  if (progress <= 0 || progress >= 1) return '--'
  const totalEstimate = elapsed / progress
  const remaining = totalEstimate - elapsed
  return formatDuration(remaining)
}

/** Generate a unique ID for output entries. Uses crypto.randomUUID where available. */
function uniqueId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

// ── Store ────────────────────────────────────────────────────────────────────

interface OutputState {
  activeRunId: string | null
  isStreaming: boolean
  entries: OutputEntry[]
  elapsed: number
  eta: number | null
  etaDisplay: string
  activeCategory: OutputCategory | null

  inferenceMetrics: InferenceMetrics
  trainingMetrics: TrainingMetrics
  hardwareMetrics: HardwareMetrics

  // Internal (prefixed to signal not for external use)
  _sseUnsubscribe: (() => void) | null
  _elapsedInterval: number | null
  _hwPollInterval: number | null

  // Actions
  addEntry: (entry: OutputEntry) => void
  subscribeToRun: (runId: string) => void
  unsubscribeFromRun: () => void
  updateHardwareMetrics: (metrics: HardwareMetrics) => void
  clearEntries: () => void
  getAllText: () => string
}

const INITIAL_INFERENCE: InferenceMetrics = { latencyMs: 0, totalTokens: 0, tokensPerSecond: 0 }
const INITIAL_TRAINING: TrainingMetrics = { loss: null, learningRate: null, step: 0, totalSteps: 0, epoch: 0 }
const INITIAL_HARDWARE: HardwareMetrics = { cpuPercent: 0, memPercent: 0, memGb: 0, gpuPercent: null }

/** Clean up all active timers and SSE subscription */
function cleanupSubscription(state: OutputState): void {
  if (state._sseUnsubscribe) state._sseUnsubscribe()
  if (state._elapsedInterval) clearInterval(state._elapsedInterval)
  if (state._hwPollInterval) clearInterval(state._hwPollInterval)
}

export const useOutputStore = create<OutputState>((set, get) => ({
  activeRunId: null,
  isStreaming: false,
  entries: [],
  elapsed: 0,
  eta: null,
  etaDisplay: '--',
  activeCategory: null,

  inferenceMetrics: { ...INITIAL_INFERENCE },
  trainingMetrics: { ...INITIAL_TRAINING },
  hardwareMetrics: { ...INITIAL_HARDWARE },

  _sseUnsubscribe: null,
  _elapsedInterval: null,
  _hwPollInterval: null,

  addEntry: (entry) => {
    set((s) => {
      // Ring buffer: drop oldest entries when at capacity
      const next = s.entries.length >= MAX_ENTRIES
        ? [...s.entries.slice(-(MAX_ENTRIES - 1)), entry]
        : [...s.entries, entry]
      return { entries: next }
    })
  },

  subscribeToRun: (runId: string) => {
    // Clean up any previous subscription
    cleanupSubscription(get())

    set({
      activeRunId: runId,
      isStreaming: true,
      entries: [],
      elapsed: 0,
      eta: null,
      etaDisplay: '--',
      activeCategory: null,
      inferenceMetrics: { ...INITIAL_INFERENCE },
      trainingMetrics: { ...INITIAL_TRAINING },
      hardwareMetrics: { ...INITIAL_HARDWARE },
      _sseUnsubscribe: null,
      _elapsedInterval: null,
      _hwPollInterval: null,
    })

    const startTime = Date.now()

    // Elapsed timer — updates once per second
    const elapsedInterval = window.setInterval(() => {
      const elapsed = (Date.now() - startTime) / 1000
      set({ elapsed })
    }, 1000)

    // Hardware metrics polling via the shared API client (handles base URL, retries)
    const pollHardware = async () => {
      try {
        const data = await api.get<any>('/system/metrics')
        if (!data) return
        set({
          hardwareMetrics: {
            cpuPercent: data.cpu_percent ?? 0,
            memPercent: data.memory_percent ?? 0,
            memGb: data.memory_gb ?? 0,
            gpuPercent: data.gpu_percent ?? null,
          },
        })
      } catch {
        // Silently fail — hardware metrics are best-effort
      }
    }
    pollHardware()
    const hwPollInterval = window.setInterval(pollHardware, HW_POLL_INTERVAL_MS)

    /** Stop timers and mark stream as finished */
    const finalizeRun = () => {
      clearInterval(elapsedInterval)
      clearInterval(hwPollInterval)
      set({
        isStreaming: false,
        _elapsedInterval: null,
        _hwPollInterval: null,
      })
    }

    // SSE subscription — routes events to entries + derived metrics
    const unsubscribe = sseManager.subscribe(runId, (event: string, data: any) => {
      // Skip internal meta-events (connection status)
      if (event.startsWith('__sse_')) return

      const state = get()

      switch (event) {
        case 'node_started': {
          const category = data.category || inferCategory(data.block_type || '')
          set({ activeCategory: category })
          state.addEntry({
            id: uniqueId(),
            timestamp: Date.now(),
            nodeId: data.node_id || '',
            blockType: data.block_type || '',
            category,
            entryType: 'log',
            content: `▶ Starting ${data.label || data.block_type || data.node_id || 'block'}`,
          })
          break
        }

        case 'node_output': {
          const content = formatNodeOutput(data)
          state.addEntry({
            id: uniqueId(),
            timestamp: Date.now(),
            nodeId: data.node_id || '',
            blockType: data.block_type || '',
            category: state.activeCategory || 'unknown',
            entryType: 'text',
            content,
            metadata: data.metadata,
          })
          break
        }

        case 'node_log': {
          state.addEntry({
            id: uniqueId(),
            timestamp: Date.now(),
            nodeId: data.node_id || '',
            blockType: data.block_type || '',
            category: state.activeCategory || 'unknown',
            entryType: 'log',
            content: data.message || '',
          })
          break
        }

        case 'metric': {
          const name: string = data.name || data.metric_name || ''
          const value = data.value

          // Route to inference metrics panel
          if (name.startsWith('inference/') || name.includes('latency') || name.includes('tokens')) {
            const current = state.inferenceMetrics
            const newLatency = name.includes('latency') ? value : current.latencyMs
            const newTokens = name.includes('tokens') ? value : current.totalTokens
            set({
              inferenceMetrics: {
                latencyMs: newLatency,
                totalTokens: newTokens,
                tokensPerSecond: newLatency > 0
                  ? Math.round(newTokens / (newLatency / 1000))
                  : current.tokensPerSecond,
              },
            })
          }
          // Route to training metrics panel
          else if (name.startsWith('train/') || name.includes('loss') || name.includes('learning_rate')) {
            const current = state.trainingMetrics
            set({
              trainingMetrics: {
                ...current,
                loss: name.includes('loss') ? value : current.loss,
                learningRate: name.includes('lr') || name.includes('learning_rate') ? value : current.learningRate,
                step: data.step ?? current.step,
                totalSteps: data.total_steps ?? current.totalSteps,
                epoch: data.epoch ?? current.epoch,
              },
            })
          }

          // Also surface in the output stream
          state.addEntry({
            id: uniqueId(),
            timestamp: Date.now(),
            nodeId: data.node_id || '',
            blockType: '',
            category: state.activeCategory || 'unknown',
            entryType: 'metric',
            content: `${name}: ${typeof value === 'number' ? value.toFixed(4) : value}`,
          })
          break
        }

        case 'system_metric': {
          // Route SSE-pushed system metrics (in addition to polling)
          set({
            hardwareMetrics: {
              cpuPercent: data.cpu_pct ?? data.cpu_percent ?? get().hardwareMetrics.cpuPercent,
              memPercent: data.mem_pct ?? data.memory_percent ?? get().hardwareMetrics.memPercent,
              memGb: data.mem_gb ?? data.memory_gb ?? get().hardwareMetrics.memGb,
              gpuPercent: data.gpu_mem_pct ?? data.gpu_percent ?? get().hardwareMetrics.gpuPercent,
            },
          })
          break
        }

        case 'node_iteration': {
          state.addEntry({
            id: uniqueId(),
            timestamp: Date.now(),
            nodeId: data.node_id || '',
            blockType: 'loop_controller',
            category: 'flow',
            entryType: 'iteration',
            content: `Iteration ${(data.iteration ?? 0) + 1} / ${data.total || '?'}`,
            metadata: { iteration: data.iteration, total: data.total },
          })
          break
        }

        case 'node_completed': {
          state.addEntry({
            id: uniqueId(),
            timestamp: Date.now(),
            nodeId: data.node_id || '',
            blockType: data.block_type || '',
            category: state.activeCategory || 'unknown',
            entryType: 'log',
            content: `✓ ${data.label || data.block_type || data.node_id || 'block'} complete`,
          })
          break
        }

        case 'node_cached': {
          state.addEntry({
            id: uniqueId(),
            timestamp: Date.now(),
            nodeId: data.node_id || '',
            blockType: data.block_type || '',
            category: state.activeCategory || 'flow',
            entryType: 'log',
            content: `⊘ ${data.label || data.block_type || data.node_id || 'block'} (cached)`,
          })
          break
        }

        case 'node_retry': {
          state.addEntry({
            id: uniqueId(),
            timestamp: Date.now(),
            nodeId: data.node_id || '',
            blockType: data.block_type || '',
            category: state.activeCategory || 'unknown',
            entryType: 'log',
            content: `↻ Retrying ${data.label || data.block_type || data.node_id || 'block'}${data.attempt ? ` (attempt ${data.attempt})` : ''}`,
          })
          break
        }

        case 'node_failed': {
          state.addEntry({
            id: uniqueId(),
            timestamp: Date.now(),
            nodeId: data.node_id || '',
            blockType: data.block_type || '',
            category: 'error',
            entryType: 'log',
            content: `✗ ${data.label || data.block_type || data.node_id || 'block'} failed: ${data.error || 'Unknown error'}`,
          })
          break
        }

        case 'node_progress': {
          // Compute ETA from overall pipeline progress
          const overall = data.overall
          if (typeof overall === 'number' && overall > 0 && overall < 1) {
            const elapsed = (Date.now() - startTime) / 1000
            const etaSeconds = (elapsed / overall) * (1 - overall)
            set({ eta: etaSeconds, etaDisplay: computeEta(elapsed, overall) })
          }
          break
        }

        case 'run_completed': {
          const finalElapsed = (Date.now() - startTime) / 1000
          finalizeRun()
          set({ elapsed: finalElapsed, eta: 0, etaDisplay: '--' })
          state.addEntry({
            id: uniqueId(),
            timestamp: Date.now(),
            nodeId: '',
            blockType: '',
            category: 'system',
            entryType: 'log',
            content: `Pipeline complete — ${get().entries.length + 1} events, ${finalElapsed.toFixed(1)}s`,
          })
          break
        }

        case 'run_failed': {
          finalizeRun()
          set({ eta: null, etaDisplay: '--' })
          state.addEntry({
            id: uniqueId(),
            timestamp: Date.now(),
            nodeId: data.node_id || '',
            blockType: '',
            category: 'error',
            entryType: 'log',
            content: `✗ Error: ${data.error || data.message || 'Unknown error'}`,
          })
          break
        }

        case 'run_cancelled': {
          finalizeRun()
          set({ eta: null, etaDisplay: '--' })
          state.addEntry({
            id: uniqueId(),
            timestamp: Date.now(),
            nodeId: '',
            blockType: '',
            category: 'system',
            entryType: 'log',
            content: 'Pipeline cancelled',
          })
          break
        }
      }
    })

    set({
      _sseUnsubscribe: unsubscribe,
      _elapsedInterval: elapsedInterval,
      _hwPollInterval: hwPollInterval,
    })
  },

  unsubscribeFromRun: () => {
    cleanupSubscription(get())
    set({
      activeRunId: null,
      isStreaming: false,
      _sseUnsubscribe: null,
      _elapsedInterval: null,
      _hwPollInterval: null,
    })
  },

  updateHardwareMetrics: (metrics) => set({ hardwareMetrics: metrics }),

  clearEntries: () => set({ entries: [] }),

  getAllText: () => {
    return get().entries.map((e) => e.content).join('\n')
  },
}))
