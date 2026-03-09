import { create } from 'zustand'
import { api } from '@/api/client'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: number
  tokenCount?: number
}

export interface ChatTab {
  id: string
  title: string
  model: string
  backend: string
  messages: ChatMessage[]
  isStreaming: boolean
}

export interface ServerStatus {
  name: string
  running: boolean
  installed: boolean
  url?: string
  models: string[]
}

interface InferenceState {
  tabs: ChatTab[]
  activeTabId: string | null
  servers: ServerStatus[]
  availableModels: Record<string, any[]>
  modelsLoading: boolean

  createTab: () => void
  closeTab: (id: string) => void
  setActiveTab: (id: string) => void
  setTabModel: (tabId: string, model: string, backend: string) => void
  setTabTitle: (tabId: string, title: string) => void
  addMessage: (tabId: string, msg: ChatMessage) => void
  updateLastAssistantMessage: (tabId: string, content: string, tokenCount?: number) => void
  setStreaming: (tabId: string, streaming: boolean) => void
  fetchModels: () => Promise<void>
  fetchServers: () => Promise<void>
  sendMessage: (tabId: string, content: string) => Promise<void>
  startServer: (name: string) => Promise<void>
}

let tabCounter = 0

export const useInferenceStore = create<InferenceState>((set, get) => ({
  tabs: [],
  activeTabId: null,
  servers: [],
  availableModels: {},
  modelsLoading: false,

  createTab: () => {
    const id = `chat-${++tabCounter}-${Date.now()}`
    const tab: ChatTab = {
      id,
      title: `Chat ${tabCounter}`,
      model: '',
      backend: 'ollama',
      messages: [],
      isStreaming: false,
    }
    set((s) => ({
      tabs: [...s.tabs, tab],
      activeTabId: id,
    }))
  },

  closeTab: (id) => {
    set((s) => {
      const tabs = s.tabs.filter((t) => t.id !== id)
      let activeTabId = s.activeTabId
      if (activeTabId === id) {
        activeTabId = tabs.length > 0 ? tabs[tabs.length - 1].id : null
      }
      return { tabs, activeTabId }
    })
  },

  setActiveTab: (id) => set({ activeTabId: id }),

  setTabModel: (tabId, model, backend) => {
    set((s) => ({
      tabs: s.tabs.map((t) =>
        t.id === tabId ? { ...t, model, backend } : t
      ),
    }))
  },

  setTabTitle: (tabId, title) => {
    set((s) => ({
      tabs: s.tabs.map((t) => (t.id === tabId ? { ...t, title } : t)),
    }))
  },

  addMessage: (tabId, msg) => {
    set((s) => ({
      tabs: s.tabs.map((t) =>
        t.id === tabId ? { ...t, messages: [...t.messages, msg] } : t
      ),
    }))
  },

  updateLastAssistantMessage: (tabId, content, tokenCount) => {
    set((s) => ({
      tabs: s.tabs.map((t) => {
        if (t.id !== tabId) return t
        const msgs = [...t.messages]
        const last = msgs[msgs.length - 1]
        if (last && last.role === 'assistant') {
          msgs[msgs.length - 1] = { ...last, content, tokenCount }
        }
        return { ...t, messages: msgs }
      }),
    }))
  },

  setStreaming: (tabId, streaming) => {
    set((s) => ({
      tabs: s.tabs.map((t) =>
        t.id === tabId ? { ...t, isStreaming: streaming } : t
      ),
    }))
  },

  fetchModels: async () => {
    set({ modelsLoading: true })
    try {
      const data = await api.get<Record<string, any[]>>('/models/available')
      if (data && typeof data === 'object') {
        set({ availableModels: data })
      }
    } catch {
      // Silently fail
    } finally {
      set({ modelsLoading: false })
    }
  },

  fetchServers: async () => {
    try {
      const data = await api.get<ServerStatus[]>('/inference/servers')
      if (Array.isArray(data)) {
        set({ servers: data })
      }
    } catch {
      // Probe failed, set defaults
      set({
        servers: [
          { name: 'ollama', running: false, installed: false, models: [] },
          { name: 'mlx', running: false, installed: false, models: [] },
        ],
      })
    }
  },

  sendMessage: async (tabId, content) => {
    const { tabs, addMessage, updateLastAssistantMessage, setStreaming } = get()
    const tab = tabs.find((t) => t.id === tabId)
    if (!tab || !tab.model) return

    // Add user message
    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}-u`,
      role: 'user',
      content,
      timestamp: Date.now(),
    }
    addMessage(tabId, userMsg)

    // Add placeholder assistant message
    const assistantMsg: ChatMessage = {
      id: `msg-${Date.now()}-a`,
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
    }
    addMessage(tabId, assistantMsg)
    setStreaming(tabId, true)

    // Build message history
    const updatedTab = get().tabs.find((t) => t.id === tabId)!
    const messages = updatedTab.messages
      .filter((m) => m.role !== 'system' || m.content)
      .map((m) => ({ role: m.role, content: m.content }))
      .slice(0, -1) // Exclude the empty assistant placeholder

    try {
      const response = await fetch('/api/inference/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: tab.model,
          backend: tab.backend,
          messages,
          temperature: 0.7,
          max_tokens: 2048,
          stream: true,
        }),
      })

      if (!response.ok) {
        const errText = await response.text()
        updateLastAssistantMessage(tabId, `Error: ${errText}`)
        setStreaming(tabId, false)
        return
      }

      const reader = response.body?.getReader()
      if (!reader) {
        updateLastAssistantMessage(tabId, 'Error: No response stream')
        setStreaming(tabId, false)
        return
      }

      const decoder = new TextDecoder()
      let fullContent = ''
      let tokenCount = 0

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6).trim()
            if (data === '[DONE]') continue
            try {
              const parsed = JSON.parse(data)
              if (parsed.token) {
                fullContent += parsed.token
                tokenCount++
                updateLastAssistantMessage(tabId, fullContent, tokenCount)
              }
              if (parsed.error) {
                fullContent += `\n\n[Error: ${parsed.error}]`
                updateLastAssistantMessage(tabId, fullContent)
              }
            } catch {
              // Skip unparseable lines
            }
          }
        }
      }

      if (!fullContent) {
        updateLastAssistantMessage(tabId, '(No response received)')
      }
    } catch (err: any) {
      updateLastAssistantMessage(tabId, `Error: ${err.message || 'Connection failed'}`)
    } finally {
      setStreaming(tabId, false)
    }
  },

  startServer: async (name) => {
    try {
      await api.post(`/inference/servers/${name}/start`, {})
      // Poll for server readiness: check at 2s, 5s, 10s
      const poll = [2000, 5000, 10000]
      for (const delay of poll) {
        setTimeout(async () => {
          await get().fetchServers()
          await get().fetchModels()
        }, delay)
      }
    } catch {
      // Ignore
    }
  },
}))
