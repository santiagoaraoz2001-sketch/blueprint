import { create } from 'zustand'
import type { Node, Edge } from '@xyflow/react'
import {
  WORKFLOW_GENERATION_PROMPT,
  LLM_DEFAULTS,
  DEMO_WORKFLOW,
} from '@/lib/llm-prompts'
import { getAdapter } from '@/lib/llm-adapters'
import { useSettingsStore } from '@/stores/settingsStore'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type LLMProvider = 'ollama' | 'mlx' | 'openrouter' | 'openai' | 'anthropic' | 'manual'

/** The workflow object returned by generateWorkflow */
export interface GeneratedWorkflow {
  nodes: Node[]
  edges: Edge[]
}

interface AgentState {
  provider: LLMProvider
  model: string
  endpoint: string
  isConnected: boolean
  isGenerating: boolean
  availableModels: string[]
  error: string | null

  setProvider: (provider: LLMProvider) => void
  setModel: (model: string) => void
  setEndpoint: (endpoint: string) => void

  testConnection: () => Promise<boolean>
  fetchModels: () => Promise<void>
  generateWorkflow: (researchPlan: string) => Promise<GeneratedWorkflow | null>
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const DEMO_MODELS: string[] = [
  'llama3:8b',
  'mistral:7b',
  'codellama:13b',
]

/** Extract a human-readable message from an unknown catch value. */
function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message
  return String(err)
}

/**
 * Resolve the adapter for a provider.
 * The "manual" provider delegates to the ollama adapter as a sensible default
 * for custom / OpenAI-compatible local endpoints.
 */
function resolveAdapterProvider(provider: LLMProvider): string {
  return provider === 'manual' ? 'ollama' : provider
}

/**
 * Get the default endpoint for a provider via its adapter.
 * For "manual" we keep the classic localhost:11434 default.
 */
function defaultEndpointFor(provider: LLMProvider): string {
  if (provider === 'manual') return LLM_DEFAULTS.endpoints.ollama
  return getAdapter(provider).defaultEndpoint
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useAgentStore = create<AgentState>((set, get) => ({
  provider: 'ollama',
  model: '',
  endpoint: defaultEndpointFor('ollama'),
  isConnected: false,
  isGenerating: false,
  availableModels: [],
  error: null,

  setProvider: (provider) => {
    set({
      provider,
      endpoint: defaultEndpointFor(provider),
      isConnected: false,
      availableModels: [],
      model: '',
    })
  },

  setModel: (model) => set({ model }),
  setEndpoint: (endpoint) => set({ endpoint }),

  // -----------------------------------------------------------------------
  // testConnection
  // -----------------------------------------------------------------------
  testConnection: async () => {
    const { demoMode } = useSettingsStore.getState()
    if (demoMode) {
      set({ isConnected: true, error: null })
      return true
    }

    const { endpoint, provider } = get()
    try {
      const adapterId = resolveAdapterProvider(provider)
      const adapter = getAdapter(adapterId)
      const apiKey = useSettingsStore.getState().getApiKey(provider)

      const ok = await adapter.testConnection(endpoint, apiKey || undefined)

      if (ok) {
        set({ isConnected: true, error: null })
        return true
      }

      set({ isConnected: false, error: 'Connection failed' })
      return false
    } catch (err: unknown) {
      set({ isConnected: false, error: errorMessage(err) || 'Connection failed' })
      return false
    }
  },

  // -----------------------------------------------------------------------
  // fetchModels
  // -----------------------------------------------------------------------
  fetchModels: async () => {
    const { demoMode } = useSettingsStore.getState()
    if (demoMode) {
      set({ availableModels: DEMO_MODELS })
      if (!get().model) {
        set({ model: DEMO_MODELS[0] })
      }
      return
    }

    const { endpoint, provider } = get()
    try {
      const adapterId = resolveAdapterProvider(provider)
      const adapter = getAdapter(adapterId)
      const apiKey = useSettingsStore.getState().getApiKey(provider)

      const modelInfos = await adapter.fetchModels(endpoint, apiKey || undefined)
      const models = modelInfos.map((m) => m.id)

      set({ availableModels: models })
      if (models.length > 0 && !get().model) {
        set({ model: models[0] })
      }
    } catch {
      set({ availableModels: [] })
    }
  },

  // -----------------------------------------------------------------------
  // generateWorkflow
  // -----------------------------------------------------------------------
  generateWorkflow: async (researchPlan) => {
    const { demoMode } = useSettingsStore.getState()
    if (demoMode) {
      set({ isGenerating: true, error: null })
      // Simulate a short delay so the UI can show the generating state
      await new Promise((resolve) => setTimeout(resolve, 800))
      set({ isGenerating: false })
      return DEMO_WORKFLOW as GeneratedWorkflow
    }

    const { endpoint, model, provider } = get()
    set({ isGenerating: true, error: null })

    try {
      const adapterId = resolveAdapterProvider(provider)
      const adapter = getAdapter(adapterId)
      const apiKey = useSettingsStore.getState().getApiKey(provider)

      const prompt = `Research Plan:\n${researchPlan}\n\nGenerate the pipeline JSON:`

      const responseText = await adapter.generate(
        endpoint,
        model || 'default',
        prompt,
        WORKFLOW_GENERATION_PROMPT,
        { temperature: LLM_DEFAULTS.temperature },
        apiKey || undefined,
      )

      // Parse JSON from response (handle potential markdown wrapping)
      let jsonStr = responseText.trim()
      if (jsonStr.startsWith('```json')) jsonStr = jsonStr.slice(7)
      if (jsonStr.startsWith('```')) jsonStr = jsonStr.slice(3)
      if (jsonStr.endsWith('```')) jsonStr = jsonStr.slice(0, -3)
      jsonStr = jsonStr.trim()

      const pipeline = JSON.parse(jsonStr) as GeneratedWorkflow
      set({ isGenerating: false })
      return pipeline
    } catch (err: unknown) {
      set({ isGenerating: false, error: errorMessage(err) || 'Generation failed' })
      return null
    }
  },
}))
