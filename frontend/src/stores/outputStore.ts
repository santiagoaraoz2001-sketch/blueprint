import { create } from 'zustand'

export interface OutputEntry {
  id: string
  timestamp: number
  nodeId: string
  blockType: string
  category: string
  entryType: 'text' | 'metric' | 'log' | 'iteration' | 'checkpoint'
  content: string
  metadata?: Record<string, any>
}

const MAX_ENTRIES = 10_000

interface OutputState {
  entries: OutputEntry[]
  activeRunId: string | null
  isStreaming: boolean

  activeCategory: string | null
  hardwareMetrics: {
    cpuPercent: number
    memPercent: number
    memGb: number
    gpuPercent: number | null
  }
  inferenceMetrics: {
    tokensPerSecond: number
    totalTokens: number
    contextWindow: number
    latencyMs: number
  }
  trainingMetrics: {
    loss: number
    learningRate: number
    epoch: number
    step: number
    totalSteps: number
  }
  eta: number | null
  elapsed: number

  addEntry: (entry: OutputEntry) => void
  setActiveRun: (runId: string | null) => void
  setStreaming: (streaming: boolean) => void
  updateHardwareMetrics: (metrics: Partial<OutputState['hardwareMetrics']>) => void
  updateInferenceMetrics: (metrics: Partial<OutputState['inferenceMetrics']>) => void
  updateTrainingMetrics: (metrics: Partial<OutputState['trainingMetrics']>) => void
  setActiveCategory: (category: string | null) => void
  setEta: (eta: number | null) => void
  setElapsed: (elapsed: number) => void
  clear: () => void
}

const initialHardware = { cpuPercent: 0, memPercent: 0, memGb: 0, gpuPercent: null as number | null }
const initialInference = { tokensPerSecond: 0, totalTokens: 0, contextWindow: 0, latencyMs: 0 }
const initialTraining = { loss: 0, learningRate: 0, epoch: 0, step: 0, totalSteps: 0 }

export const useOutputStore = create<OutputState>((set) => ({
  entries: [],
  activeRunId: null,
  isStreaming: false,
  activeCategory: null,
  hardwareMetrics: { ...initialHardware },
  inferenceMetrics: { ...initialInference },
  trainingMetrics: { ...initialTraining },
  eta: null,
  elapsed: 0,

  addEntry: (entry) =>
    set((s) => {
      const next = [...s.entries, entry]
      // Ring buffer: drop oldest when exceeding cap
      if (next.length > MAX_ENTRIES) {
        return { entries: next.slice(next.length - MAX_ENTRIES) }
      }
      return { entries: next }
    }),

  setActiveRun: (runId) => set({ activeRunId: runId }),
  setStreaming: (streaming) => set({ isStreaming: streaming }),

  updateHardwareMetrics: (metrics) =>
    set((s) => ({ hardwareMetrics: { ...s.hardwareMetrics, ...metrics } })),

  updateInferenceMetrics: (metrics) =>
    set((s) => ({ inferenceMetrics: { ...s.inferenceMetrics, ...metrics } })),

  updateTrainingMetrics: (metrics) =>
    set((s) => ({ trainingMetrics: { ...s.trainingMetrics, ...metrics } })),

  setActiveCategory: (category) => set({ activeCategory: category }),
  setEta: (eta) => set({ eta }),
  setElapsed: (elapsed) => set({ elapsed }),

  clear: () =>
    set({
      entries: [],
      activeRunId: null,
      isStreaming: false,
      activeCategory: null,
      hardwareMetrics: { ...initialHardware },
      inferenceMetrics: { ...initialInference },
      trainingMetrics: { ...initialTraining },
      eta: null,
      elapsed: 0,
    }),
}))
