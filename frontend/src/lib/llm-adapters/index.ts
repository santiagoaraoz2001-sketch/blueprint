/**
 * LLM Adapter system — unified interface for multiple LLM providers.
 *
 * Each adapter implements the `LLMAdapter` interface, allowing the rest of the
 * app to interact with any provider through a single API surface.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ModelInfo {
  id: string
  name: string
  provider: string
  size?: string
  description?: string
}

export interface GenerateOptions {
  temperature?: number
  maxTokens?: number
  timeoutMs?: number
}

export interface LLMAdapter {
  /** Unique machine-readable identifier for this provider (e.g. "ollama") */
  readonly providerId: string
  /** Human-readable display name (e.g. "Ollama") */
  readonly displayName: string
  /** Whether the provider needs an API key to authenticate */
  readonly requiresApiKey: boolean
  /** Default API endpoint URL */
  readonly defaultEndpoint: string

  /** Test whether the endpoint (and optional key) are reachable & valid. */
  testConnection(endpoint: string, apiKey?: string): Promise<boolean>

  /** Fetch the list of available models from the provider. */
  fetchModels(endpoint: string, apiKey?: string): Promise<ModelInfo[]>

  /** Run a single prompt through the model and return the generated text. */
  generate(
    endpoint: string,
    model: string,
    prompt: string,
    systemPrompt: string,
    options?: GenerateOptions,
    apiKey?: string,
  ): Promise<string>
}

// ---------------------------------------------------------------------------
// Adapter imports
// ---------------------------------------------------------------------------

import { ollamaAdapter } from './ollama'
import { mlxAdapter } from './mlx'
import { openRouterAdapter } from './openrouter'
import { openAIAdapter } from './openai'
import { anthropicAdapter } from './anthropic'

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

const adapterMap: Record<string, LLMAdapter> = {
  ollama: ollamaAdapter,
  mlx: mlxAdapter,
  openrouter: openRouterAdapter,
  openai: openAIAdapter,
  anthropic: anthropicAdapter,
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Provider metadata for UI dropdowns and configuration screens.
 */
export const PROVIDERS: { id: string; label: string; requiresKey: boolean }[] = [
  { id: 'ollama', label: 'Ollama', requiresKey: false },
  { id: 'mlx', label: 'MLX', requiresKey: false },
  { id: 'openrouter', label: 'OpenRouter', requiresKey: true },
  { id: 'openai', label: 'OpenAI', requiresKey: true },
  { id: 'anthropic', label: 'Anthropic', requiresKey: true },
]

/**
 * Factory function — returns the adapter for the given provider id.
 *
 * @throws {Error} if the provider id is not recognised.
 */
export function getAdapter(provider: string): LLMAdapter {
  const adapter = adapterMap[provider]
  if (!adapter) {
    throw new Error(
      `Unknown LLM provider "${provider}". Available providers: ${Object.keys(adapterMap).join(', ')}`,
    )
  }
  return adapter
}

// Re-export individual adapters for direct use
export { ollamaAdapter } from './ollama'
export { mlxAdapter } from './mlx'
export { openRouterAdapter } from './openrouter'
export { openAIAdapter } from './openai'
export { anthropicAdapter } from './anthropic'
