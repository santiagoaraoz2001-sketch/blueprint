import { create } from 'zustand'
import { api } from '@/api/client'
import { useSettingsStore } from './settingsStore'

export interface HFModel {
  id: string
  author: string
  downloads: number
  likes: number
  pipeline_tag: string
  tags: string[]
  formats: string[]
  last_modified: string
}

export interface LocalModel {
  name: string
  path: string
  format: string
  size_bytes: number
  detected_quant: string | null
}

interface ModelHubState {
  searchResults: HFModel[]
  localModels: LocalModel[]
  searchQuery: string
  loading: boolean
  error: string | null

  searchModels: (query: string) => Promise<void>
  fetchLocalModels: () => Promise<void>
  triggerScan: () => Promise<void>
  setSearchQuery: (query: string) => void
}

// Demo data for demo mode
const DEMO_HF_MODELS: HFModel[] = [
  {
    id: 'meta-llama/Llama-3-8B',
    author: 'meta-llama',
    downloads: 5200000,
    likes: 12000,
    pipeline_tag: 'text-generation',
    tags: ['llama', 'transformer', 'pytorch'],
    formats: ['safetensors'],
    last_modified: '2025-01-15',
  },
  {
    id: 'mistralai/Mistral-7B-v0.3',
    author: 'mistralai',
    downloads: 3100000,
    likes: 8500,
    pipeline_tag: 'text-generation',
    tags: ['mistral', 'transformer'],
    formats: ['safetensors', 'gguf'],
    last_modified: '2025-02-01',
  },
  {
    id: 'google/gemma-2-9b',
    author: 'google',
    downloads: 2400000,
    likes: 6200,
    pipeline_tag: 'text-generation',
    tags: ['gemma', 'transformer'],
    formats: ['safetensors'],
    last_modified: '2025-01-20',
  },
  {
    id: 'microsoft/Phi-3-mini-4k-instruct',
    author: 'microsoft',
    downloads: 1800000,
    likes: 4300,
    pipeline_tag: 'text-generation',
    tags: ['phi', 'transformer', 'instruct'],
    formats: ['safetensors', 'gguf'],
    last_modified: '2025-02-10',
  },
  {
    id: 'sentence-transformers/all-MiniLM-L6-v2',
    author: 'sentence-transformers',
    downloads: 9800000,
    likes: 5600,
    pipeline_tag: 'feature-extraction',
    tags: ['sentence-transformers', 'embedding'],
    formats: ['safetensors', 'pytorch'],
    last_modified: '2024-12-05',
  },
]

const DEMO_LOCAL_MODELS: LocalModel[] = [
  {
    name: 'Llama-3-8B-Q4_K_M',
    path: '~/.ollama/models/llama3',
    format: 'gguf',
    size_bytes: 4_800_000_000,
    detected_quant: 'Q4_K_M',
  },
  {
    name: 'Mistral-7B',
    path: '~/.cache/huggingface/hub/mistral-7b',
    format: 'safetensors',
    size_bytes: 14_500_000_000,
    detected_quant: null,
  },
  {
    name: 'Phi-3-mini-Q5_K_S',
    path: '~/.specific-labs/models/phi3-mini',
    format: 'gguf',
    size_bytes: 2_800_000_000,
    detected_quant: 'Q5_K_S',
  },
]

export const useModelHubStore = create<ModelHubState>((set) => ({
  searchResults: [],
  localModels: [],
  searchQuery: '',
  loading: false,
  error: null,

  searchModels: async (query: string) => {
    set({ loading: true, error: null })
    const demoMode = useSettingsStore.getState().demoMode

    if (demoMode) {
      const lq = query.toLowerCase()
      const filtered = lq
        ? DEMO_HF_MODELS.filter(
            (m) =>
              m.id.toLowerCase().includes(lq) ||
              m.author.toLowerCase().includes(lq) ||
              m.tags.some((t) => t.toLowerCase().includes(lq)) ||
              m.pipeline_tag.toLowerCase().includes(lq)
          )
        : DEMO_HF_MODELS
      set({ searchResults: filtered, loading: false })
      return
    }

    try {
      const params = new URLSearchParams()
      if (query) params.set('q', query)
      params.set('limit', '20')
      const data = await api.get<HFModel[]>(`/models/search?${params}`)
      set({ searchResults: data, loading: false })
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Search failed'
      set({ error: msg, loading: false })
    }
  },

  fetchLocalModels: async () => {
    set({ loading: true, error: null })
    const demoMode = useSettingsStore.getState().demoMode

    if (demoMode) {
      set({ localModels: DEMO_LOCAL_MODELS, loading: false })
      return
    }

    try {
      const data = await api.get<LocalModel[]>('/models/local')
      set({ localModels: data, loading: false })
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to fetch local models'
      set({ error: msg, loading: false })
    }
  },

  triggerScan: async () => {
    set({ loading: true, error: null })
    const demoMode = useSettingsStore.getState().demoMode

    if (demoMode) {
      set({ localModels: DEMO_LOCAL_MODELS, loading: false })
      return
    }

    try {
      const data = await api.post<{ count: number; models: LocalModel[] }>('/models/local/scan')
      set({ localModels: data.models, loading: false })
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Scan failed'
      set({ error: msg, loading: false })
    }
  },

  setSearchQuery: (query: string) => set({ searchQuery: query }),
}))
