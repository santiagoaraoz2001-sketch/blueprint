/**
 * Ollama LLM adapter.
 * Communicates with a local Ollama instance via its REST API.
 */

import { LLM_DEFAULTS } from '@/lib/llm-prompts'
import type { LLMAdapter, ModelInfo, GenerateOptions } from './index'

/** Shape returned by Ollama's /api/tags endpoint */
interface OllamaTagModel {
  name: string
  modified_at: string
  size: number
}

interface OllamaTagsResponse {
  models?: OllamaTagModel[]
}

interface OllamaGenerateResponse {
  response?: string
}

function createTimeoutSignal(ms: number): AbortSignal {
  const controller = new AbortController()
  setTimeout(() => controller.abort(), ms)
  return controller.signal
}

export const ollamaAdapter: LLMAdapter = {
  providerId: 'ollama',
  displayName: 'Ollama',
  requiresApiKey: false,
  defaultEndpoint: LLM_DEFAULTS.endpoints.ollama ?? 'http://localhost:11434',

  async testConnection(endpoint: string): Promise<boolean> {
    try {
      const signal = createTimeoutSignal(LLM_DEFAULTS.timeoutMs)
      const res = await fetch(`${endpoint}/api/tags`, { signal })
      return res.ok
    } catch {
      return false
    }
  },

  async fetchModels(endpoint: string): Promise<ModelInfo[]> {
    try {
      const signal = createTimeoutSignal(LLM_DEFAULTS.timeoutMs)
      const res = await fetch(`${endpoint}/api/tags`, { signal })
      if (!res.ok) return []
      const data = (await res.json()) as OllamaTagsResponse
      return (data.models ?? []).map((m) => ({
        id: m.name,
        name: m.name,
        provider: 'ollama',
        size: `${(m.size / 1e9).toFixed(1)}GB`,
      }))
    } catch {
      return []
    }
  },

  async generate(
    endpoint: string,
    model: string,
    prompt: string,
    systemPrompt: string,
    options?: GenerateOptions,
  ): Promise<string> {
    const timeout = options?.timeoutMs ?? LLM_DEFAULTS.timeoutMs
    const signal = createTimeoutSignal(timeout)

    const res = await fetch(`${endpoint}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal,
      body: JSON.stringify({
        model,
        prompt: `${systemPrompt}\n\n${prompt}`,
        stream: false,
        options: {
          temperature: options?.temperature ?? LLM_DEFAULTS.temperature,
          ...(options?.maxTokens ? { num_predict: options.maxTokens } : {}),
        },
      }),
    })

    if (!res.ok) {
      const text = await res.text().catch(() => 'Unknown error')
      throw new Error(`Ollama generation failed (${res.status}): ${text}`)
    }

    const data = (await res.json()) as OllamaGenerateResponse
    return data.response ?? ''
  },
}
