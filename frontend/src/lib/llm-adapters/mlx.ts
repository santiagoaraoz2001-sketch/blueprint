/**
 * MLX LLM adapter.
 * Communicates with a local MLX server via OpenAI-compatible REST API.
 */

import { LLM_DEFAULTS } from '@/lib/llm-prompts'
import type { LLMAdapter, ModelInfo, GenerateOptions } from './index'

/** Shape returned by MLX's /v1/models endpoint */
interface MLXModelEntry {
  id: string
  object: string
}

interface MLXModelsResponse {
  data?: MLXModelEntry[]
}

interface MLXChatResponse {
  choices?: { message?: { content?: string } }[]
}

const createTimeoutSignal = (ms: number): AbortSignal => AbortSignal.timeout(ms)

export const mlxAdapter: LLMAdapter = {
  providerId: 'mlx',
  displayName: 'MLX',
  requiresApiKey: false,
  defaultEndpoint: LLM_DEFAULTS.endpoints.mlx ?? 'http://localhost:8080',

  async testConnection(endpoint: string): Promise<boolean> {
    try {
      const signal = createTimeoutSignal(LLM_DEFAULTS.timeoutMs)
      const res = await fetch(`${endpoint}/v1/models`, { signal })
      return res.ok
    } catch {
      return false
    }
  },

  async fetchModels(endpoint: string): Promise<ModelInfo[]> {
    try {
      const signal = createTimeoutSignal(LLM_DEFAULTS.timeoutMs)
      const res = await fetch(`${endpoint}/v1/models`, { signal })
      if (!res.ok) return []
      const data = (await res.json()) as MLXModelsResponse
      return (data.data ?? []).map((m) => ({
        id: m.id,
        name: m.id,
        provider: 'mlx',
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

    const res = await fetch(`${endpoint}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal,
      body: JSON.stringify({
        model,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: prompt },
        ],
        temperature: options?.temperature ?? LLM_DEFAULTS.temperature,
        ...(options?.maxTokens ? { max_tokens: options.maxTokens } : {}),
      }),
    })

    if (!res.ok) {
      const text = await res.text().catch(() => 'Unknown error')
      throw new Error(`MLX generation failed (${res.status}): ${text}`)
    }

    const data = (await res.json()) as MLXChatResponse
    return data.choices?.[0]?.message?.content ?? ''
  },
}
