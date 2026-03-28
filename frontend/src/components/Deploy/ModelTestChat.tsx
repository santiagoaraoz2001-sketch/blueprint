import { useState, useRef, useEffect, useCallback } from 'react'
import { T, F } from '@/lib/design-tokens'
import {
  X, Send, Bot, User, Clock, Zap, MemoryStick, AlertCircle, Loader2,
} from 'lucide-react'
import toast from 'react-hot-toast'

interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  latencyMs?: number
  tokensPerSec?: number
}

interface ModelTestChatProps {
  modelName: string
  onClose: () => void
}

const OLLAMA_BASE = '/api/inference/ollama'

export default function ModelTestChat({ modelName, onClose }: ModelTestChatProps) {
  const t = T()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [generating, setGenerating] = useState(false)
  const [ollamaAvailable, setOllamaAvailable] = useState<boolean | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Check if Ollama is available and model exists
  useEffect(() => {
    checkOllama()
  }, [modelName])

  const checkOllama = async () => {
    try {
      const resp = await fetch('/api/models/deploy/targets')
      if (!resp.ok) { setOllamaAvailable(false); return }
      const data = await resp.json()
      if (!data.ollama?.server_running) {
        setOllamaAvailable(false)
        setMessages([{
          role: 'system',
          content: 'Ollama server is not running. Start it with "ollama serve" to test models.',
        }])
        return
      }
      setOllamaAvailable(true)
      setMessages([{
        role: 'system',
        content: `Connected to Ollama. Testing model: ${modelName}. Type a message to begin.`,
      }])
    } catch {
      setOllamaAvailable(false)
      setMessages([{
        role: 'system',
        content: 'Cannot reach Ollama. Make sure it is running.',
      }])
    }
  }

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => { scrollToBottom() }, [messages, scrollToBottom])

  const handleSend = async () => {
    const prompt = input.trim()
    if (!prompt || generating || !ollamaAvailable) return

    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: prompt }])
    setGenerating(true)

    const startTime = performance.now()
    // Accumulate streamed text so we can build the final message
    let accumulated = ''

    // Add a placeholder assistant message that we'll update incrementally
    const placeholderIdx = messages.length + 1 // +1 because we just pushed the user message
    setMessages((prev) => [
      ...prev,
      { role: 'assistant', content: '', latencyMs: undefined, tokensPerSec: undefined },
    ])

    try {
      const resp = await fetch(`${OLLAMA_BASE}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: modelName,
          prompt,
          stream: true,
          timeout_s: 600,
        }),
      })

      if (!resp.ok) {
        const errText = await resp.text()
        throw new Error(errText || `HTTP ${resp.status}`)
      }

      const reader = resp.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''
      let finalStats: { eval_count?: number; eval_duration?: number } | null = null

      while (true) {
        const { done: streamDone, value } = await reader.read()
        if (streamDone) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // Keep incomplete last line in buffer

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const dataStr = line.slice(6).trim()
          if (!dataStr) continue

          try {
            const evt = JSON.parse(dataStr)

            if (evt.error) {
              throw new Error(evt.error)
            }

            if (evt.token) {
              accumulated += evt.token
              // Update the assistant message in-place for live streaming
              setMessages((prev) => {
                const updated = [...prev]
                const last = updated[updated.length - 1]
                if (last?.role === 'assistant') {
                  updated[updated.length - 1] = { ...last, content: accumulated }
                }
                return updated
              })
            }

            if (evt.done && evt.stats) {
              finalStats = evt.stats
            }
          } catch (parseErr) {
            if (parseErr instanceof Error && parseErr.message !== dataStr) {
              throw parseErr
            }
          }
        }
      }

      // Finalize with stats
      const latencyMs = performance.now() - startTime
      const tokensPerSec = finalStats?.eval_count && finalStats?.eval_duration
        ? (finalStats.eval_count / (finalStats.eval_duration / 1e9))
        : undefined

      setMessages((prev) => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last?.role === 'assistant') {
          updated[updated.length - 1] = {
            ...last,
            content: accumulated || '(empty response)',
            latencyMs: Math.round(latencyMs),
            tokensPerSec: tokensPerSec ? Math.round(tokensPerSec * 10) / 10 : undefined,
          }
        }
        return updated
      })
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Generation failed'
      if (msg.includes('not found') || msg.includes('does not exist')) {
        // Replace the placeholder assistant message with a system message
        setMessages((prev) => {
          const updated = [...prev]
          if (updated[updated.length - 1]?.role === 'assistant') {
            updated[updated.length - 1] = {
              role: 'system',
              content: `Model "${modelName}" not found in Ollama. Deploy it first using the Deploy button.`,
            }
          }
          return updated
        })
      } else {
        toast.error(`Chat error: ${msg}`)
        setMessages((prev) => {
          const updated = [...prev]
          if (updated[updated.length - 1]?.role === 'assistant' && !updated[updated.length - 1].content) {
            updated[updated.length - 1] = { role: 'system', content: `Error: ${msg}` }
          } else {
            updated.push({ role: 'system', content: `Error: ${msg}` })
          }
          return updated
        })
      }
    } finally {
      setGenerating(false)
      inputRef.current?.focus()
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
    }} onClick={onClose}>
      <div
        style={{
          background: t.bg, border: `1px solid ${t.border}`, borderRadius: 12,
          width: 560, height: '70vh', display: 'flex', flexDirection: 'column',
          boxShadow: t.shadowHeavy,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{
          padding: '12px 16px', borderBottom: `1px solid ${t.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Bot size={16} style={{ color: t.cyan }} />
            <span style={{ ...F.sm, fontWeight: 700, color: t.text }}>Test Model</span>
            <span style={{
              ...F.xs, color: t.dim, background: t.surface3, borderRadius: 4,
              padding: '1px 6px',
            }}>
              {modelName}
            </span>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: t.dim, padding: 4 }}>
            <X size={16} />
          </button>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
          {messages.map((msg, i) => (
            <MessageBubble key={i} message={msg} />
          ))}
          {generating && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 12px' }}>
              <Loader2 size={14} style={{ color: t.cyan, animation: 'spin 1s linear infinite' }} />
              <span style={{ ...F.xs, color: t.dim }}>Generating...</span>
              <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div style={{
          padding: '10px 12px', borderTop: `1px solid ${t.border}`,
          display: 'flex', gap: 8, flexShrink: 0,
        }}>
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
            placeholder={ollamaAvailable ? 'Type a message...' : 'Ollama not available'}
            disabled={!ollamaAvailable || generating}
            style={{
              ...F.xs, flex: 1, padding: '8px 12px', borderRadius: 8,
              border: `1px solid ${t.border}`, background: t.surface2,
              color: t.text, outline: 'none',
            }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || generating || !ollamaAvailable}
            style={{
              padding: '8px 12px', borderRadius: 8,
              background: t.cyan, color: t.bg, border: 'none',
              cursor: input.trim() && !generating ? 'pointer' : 'not-allowed',
              opacity: input.trim() && !generating ? 1 : 0.4,
              display: 'flex', alignItems: 'center',
            }}
          >
            <Send size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}


function MessageBubble({ message }: { message: ChatMessage }) {
  const t = T()

  if (message.role === 'system') {
    return (
      <div style={{
        display: 'flex', alignItems: 'flex-start', gap: 6, padding: '6px 10px',
        marginBottom: 8, borderRadius: 8, background: `${t.amber}11`,
        border: `1px solid ${t.amber}22`,
      }}>
        <AlertCircle size={13} style={{ color: t.amber, marginTop: 1, flexShrink: 0 }} />
        <span style={{ ...F.xs, color: t.amber }}>{message.content}</span>
      </div>
    )
  }

  const isUser = message.role === 'user'

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      alignItems: isUser ? 'flex-end' : 'flex-start',
      marginBottom: 10,
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 4, marginBottom: 3,
      }}>
        {isUser ? <User size={11} style={{ color: t.dim }} /> : <Bot size={11} style={{ color: t.cyan }} />}
        <span style={{ ...F.xs, color: t.dim, fontSize: 10 }}>
          {isUser ? 'You' : 'Model'}
        </span>
      </div>
      <div style={{
        ...F.xs, padding: '8px 12px', borderRadius: 10,
        maxWidth: '85%', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
        background: isUser ? t.cyan : t.surface3,
        color: isUser ? t.bg : t.text,
        lineHeight: 1.5,
      }}>
        {message.content}
      </div>
      {/* Stats row for assistant messages */}
      {!isUser && (message.latencyMs || message.tokensPerSec) && (
        <div style={{ display: 'flex', gap: 10, marginTop: 3 }}>
          {message.latencyMs != null && (
            <span style={{ ...F.xs, color: t.dim, fontSize: 10, display: 'flex', alignItems: 'center', gap: 2 }}>
              <Clock size={9} /> {message.latencyMs}ms
            </span>
          )}
          {message.tokensPerSec != null && (
            <span style={{ ...F.xs, color: t.dim, fontSize: 10, display: 'flex', alignItems: 'center', gap: 2 }}>
              <Zap size={9} /> {message.tokensPerSec} tok/s
            </span>
          )}
        </div>
      )}
    </div>
  )
}
