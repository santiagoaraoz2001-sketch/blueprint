/**
 * LLM Adapter Registry — provides a unified interface for interacting with
 * different LLM providers (Ollama, MLX, OpenRouter, OpenAI, Anthropic).
 *
 * Each adapter exposes the same API surface so the agent store and help
 * assistant can swap providers transparently.
 */

// ── Types ─────────────────────────────────────────────────────────

export interface ModelInfo {
  id: string
  name?: string
  size?: number
}

export interface LLMAdapter {
  id: string
  label: string
  defaultEndpoint: string
  requiresKey: boolean
  testConnection: (endpoint: string, apiKey?: string) => Promise<boolean>
  fetchModels: (endpoint: string, apiKey?: string) => Promise<ModelInfo[]>
  generate: (
    endpoint: string,
    model: string,
    prompt: string,
    systemPrompt: string,
    options?: { temperature?: number; maxTokens?: number },
    apiKey?: string,
  ) => Promise<string>
}

export interface ProviderMeta {
  id: string
  label: string
  requiresKey: boolean
}

// ── Ollama Adapter ────────────────────────────────────────────────

const ollamaAdapter: LLMAdapter = {
  id: 'ollama',
  label: 'Ollama (Local)',
  defaultEndpoint: 'http://localhost:11434',
  requiresKey: false,

  testConnection: async (endpoint) => {
    try {
      const resp = await fetch(`${endpoint}/api/tags`)
      return resp.ok
    } catch {
      return false
    }
  },

  fetchModels: async (endpoint) => {
    try {
      const resp = await fetch(`${endpoint}/api/tags`)
      if (!resp.ok) return []
      const data = await resp.json()
      return (data.models || []).map((m: any) => ({
        id: m.name || m.model,
        name: m.name || m.model,
        size: m.size,
      }))
    } catch {
      return []
    }
  },

  generate: async (endpoint, model, prompt, systemPrompt, options, _apiKey) => {
    const resp = await fetch(`${endpoint}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model,
        prompt,
        system: systemPrompt,
        stream: false,
        options: { temperature: options?.temperature ?? 0.7 },
      }),
    })
    if (!resp.ok) throw new Error(`Ollama error: ${resp.status}`)
    const data = await resp.json()
    return data.response || ''
  },
}

// ── MLX Adapter ───────────────────────────────────────────────────

const mlxAdapter: LLMAdapter = {
  id: 'mlx',
  label: 'MLX (Apple Silicon)',
  defaultEndpoint: 'http://localhost:8080',
  requiresKey: false,

  testConnection: async (endpoint) => {
    try {
      const resp = await fetch(`${endpoint}/v1/models`)
      return resp.ok
    } catch {
      return false
    }
  },

  fetchModels: async (endpoint) => {
    try {
      const resp = await fetch(`${endpoint}/v1/models`)
      if (!resp.ok) return []
      const data = await resp.json()
      return (data.data || []).map((m: any) => ({ id: m.id, name: m.id }))
    } catch {
      return []
    }
  },

  generate: async (endpoint, model, prompt, systemPrompt, options, _apiKey) => {
    const resp = await fetch(`${endpoint}/v1/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: prompt },
        ],
        temperature: options?.temperature ?? 0.7,
        stream: false,
      }),
    })
    if (!resp.ok) throw new Error(`MLX error: ${resp.status}`)
    const data = await resp.json()
    return data.choices?.[0]?.message?.content || ''
  },
}

// ── OpenAI-compatible Adapter (OpenRouter, OpenAI, etc.) ──────────

function createOpenAIAdapter(
  id: string, label: string, defaultEndpoint: string, requiresKey: boolean,
): LLMAdapter {
  return {
    id, label, defaultEndpoint, requiresKey,

    testConnection: async (endpoint, apiKey) => {
      try {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`
        const resp = await fetch(`${endpoint}/v1/models`, { headers })
        return resp.ok
      } catch {
        return false
      }
    },

    fetchModels: async (endpoint, apiKey) => {
      try {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' }
        if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`
        const resp = await fetch(`${endpoint}/v1/models`, { headers })
        if (!resp.ok) return []
        const data = await resp.json()
        return (data.data || []).map((m: any) => ({ id: m.id, name: m.id }))
      } catch {
        return []
      }
    },

    generate: async (endpoint, model, prompt, systemPrompt, options, apiKey) => {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`
      const resp = await fetch(`${endpoint}/v1/chat/completions`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          model,
          messages: [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: prompt },
          ],
          temperature: options?.temperature ?? 0.7,
          stream: false,
        }),
      })
      if (!resp.ok) throw new Error(`${label} error: ${resp.status}`)
      const data = await resp.json()
      return data.choices?.[0]?.message?.content || ''
    },
  }
}

// ── Registry ──────────────────────────────────────────────────────

const adapters: Record<string, LLMAdapter> = {
  ollama: ollamaAdapter,
  mlx: mlxAdapter,
  openrouter: createOpenAIAdapter('openrouter', 'OpenRouter', 'https://openrouter.ai/api', true),
  openai: createOpenAIAdapter('openai', 'OpenAI', 'https://api.openai.com', true),
  anthropic: createOpenAIAdapter('anthropic', 'Anthropic', 'https://api.anthropic.com', true),
}

export function getAdapter(providerId: string): LLMAdapter {
  const adapter = adapters[providerId]
  if (!adapter) {
    console.warn(`[llm-adapters] Unknown provider "${providerId}", falling back to ollama`)
    return ollamaAdapter
  }
  return adapter
}

export const PROVIDERS: ProviderMeta[] = Object.values(adapters).map((a) => ({
  id: a.id,
  label: a.label,
  requiresKey: a.requiresKey,
}))
