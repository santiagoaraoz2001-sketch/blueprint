/**
 * OpenAI LLM adapter.
 * Communicates with the OpenAI API using the standard chat completions format.
 */

import { LLM_DEFAULTS } from '@/lib/llm-prompts'
import type { LLMAdapter, ModelInfo, GenerateOptions } from './index'

interface OpenAIModelEntry {
  id: string
  object: string
  owned_by?: string
}

interface OpenAIModelsResponse {
  data?: OpenAIModelEntry[]
}

interface OpenAIChatResponse {
  choices?: { message?: { content?: string } }[]
}

/** Models that are relevant for chat/generation use cases. */
const GPT_MODEL_PREFIXES = ['gpt-4', 'gpt-3.5', 'o1', 'o3', 'o4']

function createTimeoutSignal(ms: number): AbortSignal {
  const controller = new AbortController()
  setTimeout(() => controller.abort(), ms)
  return controller.signal
}

function buildHeaders(apiKey?: string): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (apiKey) {
    headers['Authorization'] = `Bearer ${apiKey}`
  }
  return headers
}

export const openAIAdapter: LLMAdapter = {
  providerId: 'openai',
  displayName: 'OpenAI',
  requiresApiKey: true,
  defaultEndpoint: 'https://api.openai.com/v1',

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
      const data = (await res.json()) as OpenAIModelsResponse
      const allModels = data.data ?? []
      const chatModels = allModels.filter((m) =>
        GPT_MODEL_PREFIXES.some((prefix) => m.id.startsWith(prefix)),
      )
      return chatModels
        .sort((a, b) => a.id.localeCompare(b.id))
        .map((m) => ({
          id: m.id,
          name: m.id,
          provider: 'openai',
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
      throw new Error(`OpenAI generation failed (${res.status}): ${text}`)
    }

    const data = (await res.json()) as OpenAIChatResponse
    return data.choices?.[0]?.message?.content ?? ''
  },
}
