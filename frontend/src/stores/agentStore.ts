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

/**
 * Robustly extract pipeline JSON from an LLM response.
 *
 * Handles:
 *  - Clean JSON
 *  - Markdown code blocks (```json ... ```)
 *  - Preamble/trailing text around JSON
 *  - Nested braces
 */
function extractPipelineJSON(raw: string): GeneratedWorkflow {
  let text = raw.trim()

  // Strip markdown code fences first
  const fenceMatch = text.match(/```(?:json)?\s*([\s\S]*?)```/)
  if (fenceMatch) {
    text = fenceMatch[1].trim()
  }

  // Try direct parse first
  try {
    const parsed = JSON.parse(text)
    if (parsed && (parsed.nodes || parsed.edges)) return parsed as GeneratedWorkflow
  } catch {
    // Fall through to bracket extraction
  }

  // Find the first '{' and last matching '}' — handles preamble/trailing text
  const firstBrace = text.indexOf('{')
  if (firstBrace === -1) {
    throw new Error('No JSON object found in LLM response')
  }

  // Walk from the first '{' to find the matching '}'
  let depth = 0
  let lastBrace = -1
  for (let i = firstBrace; i < text.length; i++) {
    if (text[i] === '{') depth++
    else if (text[i] === '}') {
      depth--
      if (depth === 0) {
        lastBrace = i
        break
      }
    }
  }

  if (lastBrace === -1) {
    throw new Error('Unmatched braces in LLM response — JSON is incomplete')
  }

  const jsonStr = text.slice(firstBrace, lastBrace + 1)
  const parsed = JSON.parse(jsonStr)

  if (!parsed.nodes && !parsed.edges) {
    throw new Error('Parsed JSON does not contain nodes or edges')
  }

  return parsed as GeneratedWorkflow
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

      // Parse JSON from response — robust extraction handles markdown,
      // preamble text, and trailing commentary from LLMs.
      const pipeline = extractPipelineJSON(responseText)
      set({ isGenerating: false })
      return pipeline
    } catch (err: unknown) {
      set({ isGenerating: false, error: errorMessage(err) || 'Generation failed' })
      return null
    }
  },
}))
