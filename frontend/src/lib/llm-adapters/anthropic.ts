/**
 * Anthropic LLM adapter.
 * Communicates with the Anthropic Messages API.
 */

import { LLM_DEFAULTS } from '@/lib/llm-prompts'
import type { LLMAdapter, ModelInfo, GenerateOptions } from './index'

interface AnthropicContentBlock {
  type: string
  text?: string
}

interface AnthropicMessagesResponse {
  content?: AnthropicContentBlock[]
}

/** Hardcoded model list since Anthropic does not expose a public models endpoint. */
const ANTHROPIC_MODELS: ModelInfo[] = [
  {
    id: 'claude-sonnet-4-20250514',
    name: 'Claude Sonnet 4',
    provider: 'anthropic',
    description: 'Best combination of intelligence and speed',
  },
  {
    id: 'claude-3-5-haiku-20241022',
    name: 'Claude 3.5 Haiku',
    provider: 'anthropic',
    description: 'Fastest and most compact model for near-instant responses',
  },
  {
    id: 'claude-opus-4-20250514',
    name: 'Claude Opus 4',
    provider: 'anthropic',
    description: 'Most powerful model for highly complex tasks',
  },
  {
    id: 'claude-3-5-sonnet-20241022',
    name: 'Claude 3.5 Sonnet',
    provider: 'anthropic',
    description: 'Previous generation high-intelligence model',
  },
]

const ANTHROPIC_API_VERSION = '2023-06-01'

const createTimeoutSignal = (ms: number): AbortSignal => AbortSignal.timeout(ms)

function buildHeaders(apiKey?: string): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'anthropic-version': ANTHROPIC_API_VERSION,
  }
  if (apiKey) {
    headers['x-api-key'] = apiKey
  }
  return headers
}

export const anthropicAdapter: LLMAdapter = {
  providerId: 'anthropic',
  displayName: 'Anthropic',
  requiresApiKey: true,
  defaultEndpoint: 'https://api.anthropic.com/v1',

  async testConnection(endpoint: string, apiKey?: string): Promise<boolean> {
    try {
      const signal = createTimeoutSignal(LLM_DEFAULTS.timeoutMs)
      // Send a minimal messages request to verify the key works.
      // Using max_tokens: 1 to minimize cost.
      const res = await fetch(`${endpoint}/messages`, {
        method: 'POST',
        headers: buildHeaders(apiKey),
        signal,
        body: JSON.stringify({
          model: 'claude-3-5-haiku-20241022',
          messages: [{ role: 'user', content: 'Hi' }],
          max_tokens: 1,
        }),
      })
      return res.ok
    } catch {
      return false
    }
  },

  async fetchModels(): Promise<ModelInfo[]> {
    // Anthropic does not expose a public models listing endpoint.
    // Return the hardcoded list of available models.
    return ANTHROPIC_MODELS
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

    const res = await fetch(`${endpoint}/messages`, {
      method: 'POST',
      headers: buildHeaders(apiKey),
      signal,
      body: JSON.stringify({
        model,
        system: systemPrompt,
        messages: [{ role: 'user', content: prompt }],
        max_tokens: options?.maxTokens ?? 4096,
        temperature: options?.temperature ?? LLM_DEFAULTS.temperature,
      }),
    })

    if (!res.ok) {
      const text = await res.text().catch(() => 'Unknown error')
      throw new Error(`Anthropic generation failed (${res.status}): ${text}`)
    }

    const data = (await res.json()) as AnthropicMessagesResponse
    // Concatenate all text blocks from the response
    const textBlocks = (data.content ?? []).filter((b) => b.type === 'text')
    return textBlocks.map((b) => b.text ?? '').join('')
  },
}
