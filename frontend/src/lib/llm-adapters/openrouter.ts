/**
 * OpenRouter LLM adapter.
 * Communicates with the OpenRouter API using OpenAI-compatible format.
 */

import { LLM_DEFAULTS } from '@/lib/llm-prompts'
import type { LLMAdapter, ModelInfo, GenerateOptions } from './index'

interface OpenRouterModelEntry {
  id: string
  name?: string
  description?: string
  context_length?: number
}

interface OpenRouterModelsResponse {
  data?: OpenRouterModelEntry[]
}

interface OpenRouterChatResponse {
  choices?: { message?: { content?: string } }[]
}

function createTimeoutSignal(ms: number): AbortSignal {
  const controller = new AbortController()
  setTimeout(() => controller.abort(), ms)
  return controller.signal
}

function buildHeaders(apiKey?: string): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'HTTP-Referer': 'https://specificlabs.com',
    'X-Title': 'Blueprint',
  }
  if (apiKey) {
    headers['Authorization'] = `Bearer ${apiKey}`
  }
  return headers
}

export const openRouterAdapter: LLMAdapter = {
  providerId: 'openrouter',
  displayName: 'OpenRouter',
  requiresApiKey: true,
  defaultEndpoint: 'https://openrouter.ai/api/v1',

  async testConnection(endpoint: string, apiKey?: string): Promise<boolean> {
    try {
      const signal = createTimeoutSignal(LLM_DEFAULTS.timeoutMs)
      const res = await fetch(`${endpoint}/models`, {
        headers: buildHeaders(apiKey),
        signal,
      })
      return res.ok
    } catch {
      return false
    }
  },

  async fetchModels(endpoint: string, apiKey?: string): Promise<ModelInfo[]> {
    try {
      const signal = createTimeoutSignal(LLM_DEFAULTS.timeoutMs)
      const res = await fetch(`${endpoint}/models`, {
        headers: buildHeaders(apiKey),
        signal,
      })
      if (!res.ok) return []
      const data = (await res.json()) as OpenRouterModelsResponse
      return (data.data ?? []).map((m) => ({
        id: m.id,
        name: m.name ?? m.id,
        provider: 'openrouter',
        description: m.description,
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
    apiKey?: string,
  ): Promise<string> {
    const timeout = options?.timeoutMs ?? LLM_DEFAULTS.timeoutMs
    const signal = createTimeoutSignal(timeout)

    const res = await fetch(`${endpoint}/chat/completions`, {
      method: 'POST',
      headers: buildHeaders(apiKey),
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
      throw new Error(`OpenRouter generation failed (${res.status}): ${text}`)
    }

    const data = (await res.json()) as OpenRouterChatResponse
    return data.choices?.[0]?.message?.content ?? ''
  },
}
