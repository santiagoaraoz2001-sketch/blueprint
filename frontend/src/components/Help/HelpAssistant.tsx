import { useState, useRef, useEffect, useCallback } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { useAgentStore } from '@/stores/agentStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { getAdapter, PROVIDERS } from '@/lib/llm-adapters'
import { Sparkles, Send, Trash2, X, Loader, AlertCircle, Settings } from 'lucide-react'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

interface HelpAssistantProps {
  contextText: string
  contextTitle: string
  onClose: () => void
}

/**
 * LLM-powered help chat panel.
 * Uses the app's unified LLM adapter system to answer questions
 * about Blueprint using the current help section as context.
 */
export default function HelpAssistant({ contextText, contextTitle, onClose }: HelpAssistantProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [models, setModels] = useState<string[]>([])
  const [selectedModel, setSelectedModel] = useState('')
  const [connected, setConnected] = useState<boolean | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const provider = useAgentStore((s) => s.provider)
  const endpoint = useAgentStore((s) => s.endpoint)

  // Test connection & fetch models on mount or provider/endpoint change
  useEffect(() => {
    let cancelled = false

    ;(async () => {
      try {
        const adapterId = provider === 'manual' ? 'ollama' : provider
        const adapter = getAdapter(adapterId)
        const apiKey = useSettingsStore.getState().getApiKey(provider)

        const ok = await adapter.testConnection(endpoint, apiKey)
        if (cancelled) return

        if (!ok) {
          setConnected(false)
          return
        }

        const modelList = await adapter.fetchModels(endpoint, apiKey)
        if (cancelled) return

        const modelNames = modelList.map((m) => m.id)
        setModels(modelNames)
        setSelectedModel(modelNames[0] ?? '')
        setConnected(true)
      } catch {
        if (!cancelled) setConnected(false)
      }
    })()

    return () => { cancelled = true }
  }, [endpoint, provider])

  // Auto-scroll on new messages
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, loading])

  // Cleanup abort controller on unmount
  useEffect(() => {
    return () => { abortRef.current?.abort() }
  }, [])

  const sendMessage = useCallback(async () => {
    const text = input.trim()
    if (!text || loading || !selectedModel) return

    setInput('')
    setError(null)
    const userMsg: ChatMessage = { role: 'user', content: text }
    const newMessages = [...messages, userMsg]
    setMessages(newMessages)
    setLoading(true)

    // Abort any previous in-flight request
    abortRef.current?.abort()
    abortRef.current = new AbortController()

    const systemPrompt = `You are Blueprint's help assistant. You answer questions about Blueprint, an ML experiment workbench by Specific Labs. Use the following documentation section as context:\n\n--- ${contextTitle} ---\n${contextText.slice(0, 4000)}\n---\n\nBe specific. Reference exact UI locations, config field names, and CLI commands. If you don't know the answer, say so and suggest checking the relevant section.`

    try {
      const adapterId = provider === 'manual' ? 'ollama' : provider
      const adapter = getAdapter(adapterId)
      const apiKey = useSettingsStore.getState().getApiKey(provider)

      const assistantText = await adapter.generate(
        endpoint,
        selectedModel,
        newMessages.map((m) => `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`).join('\n'),
        systemPrompt,
        { temperature: 0.3, maxTokens: 1024 },
        apiKey,
      )

      if (assistantText) {
        setMessages([...newMessages, { role: 'assistant', content: assistantText }])
      } else {
        setError('No response received from the model.')
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      setError(err instanceof Error ? err.message : 'Failed to get response')
    } finally {
      setLoading(false)
    }
  }, [input, loading, messages, endpoint, selectedModel, provider, contextText, contextTitle])

  const panelStyle: React.CSSProperties = {
    width: 380,
    minWidth: 380,
    height: '100%',
    borderLeft: `1px solid ${T.border}`,
    background: T.surface1,
    display: 'flex',
    flexDirection: 'column',
  }

  const headerStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 16px',
    borderBottom: `1px solid ${T.border}`,
  }

  // Disconnected state
  if (connected === false) {
    const providerLabel = PROVIDERS.find((p) => p.id === provider)?.label ?? provider
    return (
      <div style={panelStyle}>
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Sparkles size={16} color={T.cyan} />
            <span style={{ fontFamily: F, fontSize: FS.sm, fontWeight: 700, color: T.text }}>
              AI Assistant
            </span>
          </div>
          <X size={16} color={T.dim} style={{ cursor: 'pointer' }} onClick={onClose} />
        </div>

        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 32,
            gap: 16,
          }}
        >
          <AlertCircle size={40} color={T.dim} />
          <div
            style={{
              fontFamily: F,
              fontSize: FS.sm,
              color: T.sec,
              textAlign: 'center',
              lineHeight: 1.6,
            }}
          >
            Could not connect to {providerLabel} at {endpoint}. Start the LLM server or configure a
            different provider in Settings.
          </div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontFamily: F,
              fontSize: FS.xs,
              color: T.cyan,
              cursor: 'pointer',
            }}
          >
            <Settings size={13} />
            Configure in Settings
          </div>
        </div>
      </div>
    )
  }

  // Loading connection state
  if (connected === null) {
    return (
      <div
        style={{
          ...panelStyle,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Loader size={20} color={T.dim} className="animate-spin" />
      </div>
    )
  }

  return (
    <div style={panelStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Sparkles size={16} color={T.cyan} />
          <span style={{ fontFamily: F, fontSize: FS.sm, fontWeight: 700, color: T.text }}>
            AI Assistant
          </span>
          <div
            style={{
              width: 7,
              height: 7,
              borderRadius: '50%',
              background: T.cyan,
              marginLeft: 2,
            }}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Trash2
            size={14}
            color={T.dim}
            style={{ cursor: 'pointer' }}
            onClick={() => setMessages([])}
          />
          <X size={16} color={T.dim} style={{ cursor: 'pointer' }} onClick={onClose} />
        </div>
      </div>

      {/* Model selector */}
      {models.length > 1 && (
        <div style={{ padding: '8px 16px', borderBottom: `1px solid ${T.border}` }}>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            style={{
              width: '100%',
              background: T.surface2,
              border: `1px solid ${T.border}`,
              color: T.text,
              fontFamily: F,
              fontSize: FS.xs,
              padding: '5px 8px',
              outline: 'none',
            }}
          >
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Messages */}
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        {messages.length === 0 && (
          <div
            style={{
              fontFamily: F,
              fontSize: FS.sm,
              color: T.dim,
              textAlign: 'center',
              marginTop: 40,
              lineHeight: 1.6,
            }}
          >
            Ask me anything about Blueprint. I&apos;ll use the current help section as context.
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: '85%',
              padding: '10px 14px',
              background: msg.role === 'user' ? T.cyan : T.surface2,
              color: msg.role === 'user' ? '#fff' : T.text,
              fontFamily: F,
              fontSize: FS.sm,
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {msg.content}
          </div>
        ))}

        {loading && (
          <div
            style={{
              alignSelf: 'flex-start',
              padding: '10px 14px',
              background: T.surface2,
              fontFamily: F,
              fontSize: FS.sm,
              color: T.dim,
            }}
          >
            Thinking...
          </div>
        )}

        {error && (
          <div
            style={{
              padding: '8px 12px',
              background: 'rgba(239,68,68,0.1)',
              border: '1px solid rgba(239,68,68,0.3)',
              fontFamily: F,
              fontSize: FS.xs,
              color: '#ef4444',
              lineHeight: 1.4,
            }}
          >
            {error}
          </div>
        )}
      </div>

      {/* Input */}
      <div
        style={{
          padding: '12px 16px',
          borderTop: `1px solid ${T.border}`,
          display: 'flex',
          gap: 8,
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              sendMessage()
            }
          }}
          placeholder="Ask about Blueprint..."
          rows={1}
          style={{
            flex: 1,
            background: T.surface2,
            border: `1px solid ${T.border}`,
            color: T.text,
            fontFamily: F,
            fontSize: FS.sm,
            padding: '8px 12px',
            outline: 'none',
            resize: 'none',
            lineHeight: 1.4,
          }}
        />
        <button
          onClick={sendMessage}
          disabled={loading || !input.trim()}
          style={{
            background: T.cyan,
            border: 'none',
            padding: '8px 12px',
            cursor: loading || !input.trim() ? 'default' : 'pointer',
            opacity: loading || !input.trim() ? 0.4 : 1,
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <Send size={15} color="#fff" />
        </button>
      </div>
    </div>
  )
}
