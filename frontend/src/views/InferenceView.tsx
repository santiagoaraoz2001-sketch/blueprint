import { useEffect, useRef, useState } from 'react'
import { T, F, FS, FD } from '@/lib/design-tokens'
import { useInferenceStore, type ChatMessage } from '@/stores/inferenceStore'
import {
  Plus, X, Send, RefreshCw, Server, Circle, MessageSquare,
  ChevronRight, Loader2,
} from 'lucide-react'

export default function InferenceView() {
  const {
    tabs, activeTabId, servers, availableModels, modelsLoading,
    createTab, closeTab, setActiveTab, setTabModel,
    fetchModels, fetchServers, startServer,
  } = useInferenceStore()

  const activeTab = tabs.find((t) => t.id === activeTabId) || null

  useEffect(() => {
    fetchModels()
    fetchServers()
  }, [fetchModels, fetchServers])

  // Auto-create first tab
  useEffect(() => {
    if (tabs.length === 0) createTab()
  }, [tabs.length, createTab])

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12,
        borderBottom: `1px solid ${T.border}`, flexShrink: 0,
      }}>
        <MessageSquare size={18} color={T.cyan} />
        <h2 style={{
          fontFamily: FD, fontSize: FS.xl * 1.5, fontWeight: 600,
          color: T.text, margin: 0, letterSpacing: '0.04em',
        }}>
          INFERENCE
        </h2>
        <div style={{ flex: 1 }} />
        <button
          onClick={() => { fetchModels(); fetchServers() }}
          style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '5px 10px', background: T.surface3,
            border: `1px solid ${T.border}`, borderRadius: 4,
            color: T.dim, fontFamily: F, fontSize: FS.xs,
            cursor: 'pointer',
          }}
        >
          <RefreshCw size={10} className={modelsLoading ? 'spin' : ''} />
          REFRESH
        </button>
      </div>

      {/* Main content */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left panel — Models */}
        <div style={{
          width: 250, minWidth: 250, borderRight: `1px solid ${T.border}`,
          display: 'flex', flexDirection: 'column', overflow: 'auto',
          background: T.surface0,
        }}>
          <div style={{
            padding: '10px 12px', fontFamily: F, fontSize: FS.xxs,
            color: T.dim, letterSpacing: '0.12em', fontWeight: 900,
            borderBottom: `1px solid ${T.border}`,
          }}>
            AVAILABLE MODELS
          </div>
          <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
            {Object.keys(availableModels).length === 0 && (
              <div style={{ padding: '20px 16px', fontFamily: F, fontSize: FS.xs, color: T.dim, textAlign: 'center' }}>
                {modelsLoading ? 'Loading models...' : 'No models detected. Start a server or install models.'}
              </div>
            )}
            {Object.entries(availableModels).map(([backend, models]) => (
              <ModelGroup
                key={backend}
                backend={backend}
                models={models}
                activeModel={activeTab?.model || ''}
                activeBackend={activeTab?.backend || ''}
                onSelect={(model) => {
                  if (activeTab) {
                    setTabModel(activeTab.id, model, backend)
                  }
                }}
              />
            ))}
          </div>
        </div>

        {/* Center — Chat */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {/* Tab bar */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 0,
            borderBottom: `1px solid ${T.border}`, background: T.surface1,
            minHeight: 36, flexShrink: 0,
          }}>
            {tabs.map((tab) => (
              <div
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px',
                  background: tab.id === activeTabId ? T.surface2 : 'transparent',
                  borderRight: `1px solid ${T.border}`,
                  borderBottom: tab.id === activeTabId ? `2px solid ${T.cyan}` : '2px solid transparent',
                  color: tab.id === activeTabId ? T.text : T.dim,
                  fontFamily: F, fontSize: FS.xs,
                  cursor: 'pointer', whiteSpace: 'nowrap',
                }}
              >
                <span style={{ maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {tab.title}
                </span>
                {tab.model && (
                  <span style={{
                    fontFamily: F, fontSize: '7px', color: T.cyan,
                    background: `${T.cyan}15`, padding: '1px 4px', borderRadius: 3,
                  }}>
                    {tab.model.split('/').pop()?.split(':')[0]}
                  </span>
                )}
                <button
                  onClick={(e) => { e.stopPropagation(); closeTab(tab.id) }}
                  style={{
                    background: 'none', border: 'none', color: T.dim,
                    cursor: 'pointer', padding: 2, display: 'flex',
                  }}
                >
                  <X size={10} />
                </button>
              </div>
            ))}
            <button
              onClick={createTab}
              style={{
                background: 'none', border: 'none', color: T.dim,
                cursor: 'pointer', padding: '6px 10px', display: 'flex',
              }}
            >
              <Plus size={12} />
            </button>
          </div>

          {/* Chat area */}
          {activeTab ? (
            <ChatArea tab={activeTab} />
          ) : (
            <div style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontFamily: F, fontSize: FS.md, color: T.dim,
            }}>
              Create a tab to start chatting
            </div>
          )}
        </div>

        {/* Right panel — Servers */}
        <div style={{
          width: 200, minWidth: 200, borderLeft: `1px solid ${T.border}`,
          display: 'flex', flexDirection: 'column', overflow: 'auto',
          background: T.surface0,
        }}>
          <div style={{
            padding: '10px 12px', fontFamily: F, fontSize: FS.xxs,
            color: T.dim, letterSpacing: '0.12em', fontWeight: 900,
            borderBottom: `1px solid ${T.border}`,
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <Server size={10} /> SERVERS
          </div>
          <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {servers.map((s) => (
              <div key={s.name} style={{
                padding: '10px 12px', background: T.surface2,
                border: `1px solid ${T.border}`, borderRadius: 6,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                  <Circle
                    size={8}
                    fill={s.running ? T.green : s.installed ? T.amber : T.red}
                    color={s.running ? T.green : s.installed ? T.amber : T.red}
                  />
                  <span style={{
                    fontFamily: F, fontSize: FS.sm, color: T.text,
                    fontWeight: 700, textTransform: 'uppercase',
                  }}>
                    {s.name}
                  </span>
                </div>
                <div style={{
                  fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6,
                }}>
                  {s.running
                    ? (s.url || 'Running')
                    : s.installed
                      ? 'Installed · Stopped'
                      : 'Not Installed'}
                </div>
                {/* Installed models list */}
                {s.models && s.models.length > 0 && (
                  <div style={{ marginBottom: 8 }}>
                    <div style={{
                      fontFamily: F, fontSize: '7px', color: T.dim,
                      letterSpacing: '0.1em', fontWeight: 900, marginBottom: 4,
                    }}>
                      {s.running ? 'LOADED MODELS' : 'INSTALLED MODELS'}
                    </div>
                    {s.models.map((model) => (
                      <div
                        key={model}
                        onClick={() => {
                          if (activeTab && s.running) {
                            setTabModel(activeTab.id, model, s.name)
                          }
                        }}
                        style={{
                          fontFamily: F, fontSize: FS.xxs,
                          color: s.running ? T.sec : T.dim,
                          padding: '2px 6px', marginBottom: 1,
                          borderRadius: 3,
                          cursor: s.running ? 'pointer' : 'default',
                          opacity: s.running ? 1 : 0.6,
                          overflow: 'hidden', textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          background: s.running ? 'transparent' : `${T.surface3}`,
                        }}
                        onMouseEnter={(e) => {
                          if (s.running) e.currentTarget.style.background = `${T.cyan}15`
                        }}
                        onMouseLeave={(e) => {
                          if (s.running) e.currentTarget.style.background = 'transparent'
                        }}
                        title={s.running ? `Click to use ${model}` : `Start ${s.name} to use this model`}
                      >
                        {model}
                      </div>
                    ))}
                  </div>
                )}
                {!s.running && s.installed && (
                  <button
                    onClick={() => startServer(s.name)}
                    style={{
                      width: '100%', padding: '4px 8px',
                      background: `${T.green}15`, border: `1px solid ${T.green}30`,
                      borderRadius: 4, color: T.green, fontFamily: F,
                      fontSize: FS.xxs, cursor: 'pointer', fontWeight: 700,
                    }}
                  >
                    START SERVER
                  </button>
                )}
                {!s.installed && (
                  <div style={{
                    fontFamily: F, fontSize: FS.xxs, color: T.dim,
                    padding: '4px 0', fontStyle: 'italic',
                  }}>
                    {s.name === 'ollama' ? 'Install from ollama.com' : 'pip install mlx-lm'}
                  </div>
                )}
              </div>
            ))}
            {servers.length === 0 && (
              <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, textAlign: 'center', padding: 20 }}>
                Click Refresh to detect servers
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Model group in sidebar ──
function ModelGroup({ backend, models, activeModel, activeBackend, onSelect }: {
  backend: string
  models: any[]
  activeModel: string
  activeBackend: string
  onSelect: (model: string) => void
}) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          width: '100%', padding: '6px 12px',
          background: 'none', border: 'none', cursor: 'pointer',
          color: T.sec, fontFamily: F, fontSize: FS.xs,
          fontWeight: 700, letterSpacing: '0.08em',
          textTransform: 'uppercase',
        }}
      >
        <ChevronRight
          size={10}
          style={{
            transform: expanded ? 'rotate(90deg)' : 'none',
            transition: 'transform 0.15s',
          }}
        />
        {backend}
        <span style={{
          marginLeft: 'auto', fontSize: FS.xxs, color: T.dim,
          background: T.surface3, padding: '1px 5px', borderRadius: 3,
        }}>
          {models.length}
        </span>
      </button>
      {expanded && models.map((m: any) => {
        const modelName = typeof m === 'string' ? m : (m.name || m.model || String(m))
        const isActive = activeModel === modelName && activeBackend === backend
        return (
          <button
            key={modelName}
            onClick={() => onSelect(modelName)}
            style={{
              display: 'block', width: '100%', padding: '5px 12px 5px 28px',
              background: isActive ? `${T.cyan}12` : 'transparent',
              border: 'none', borderLeft: isActive ? `2px solid ${T.cyan}` : '2px solid transparent',
              color: isActive ? T.text : T.sec,
              fontFamily: F, fontSize: FS.xs,
              cursor: 'pointer', textAlign: 'left',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}
          >
            {modelName}
          </button>
        )
      })}
    </div>
  )
}

// ── Chat area with messages + input ──
function ChatArea({ tab }: { tab: ReturnType<typeof useInferenceStore.getState>['tabs'][0] }) {
  const { sendMessage } = useInferenceStore()
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [tab.messages.length, tab.messages[tab.messages.length - 1]?.content])

  const handleSend = () => {
    const text = input.trim()
    if (!text) return
    if (!tab.model) return
    setInput('')
    sendMessage(tab.id, text)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* No model warning */}
      {!tab.model && (
        <div style={{
          padding: '10px 16px', background: `${T.amber}10`,
          borderBottom: `1px solid ${T.amber}30`,
          fontFamily: F, fontSize: FS.xs, color: T.amber,
        }}>
          Select a model from the left panel to start chatting
        </div>
      )}

      {/* Messages */}
      <div style={{ flex: 1, overflow: 'auto', padding: '16px 20px' }}>
        {tab.messages.length === 0 && (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', height: '100%', gap: 8,
          }}>
            <MessageSquare size={32} color={T.dim} />
            <span style={{ fontFamily: F, fontSize: FS.sm, color: T.dim }}>
              {tab.model ? 'Type a message to start' : 'Select a model first'}
            </span>
          </div>
        )}
        {tab.messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {tab.isStreaming && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 0', fontFamily: F, fontSize: FS.xxs, color: T.dim,
          }}>
            <Loader2 size={10} className="spin" />
            Generating...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div style={{
        padding: '12px 16px', borderTop: `1px solid ${T.border}`,
        display: 'flex', gap: 8, alignItems: 'flex-end',
      }}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={tab.model ? 'Type a message... (Enter to send, Shift+Enter for newline)' : 'Select a model first'}
          disabled={!tab.model || tab.isStreaming}
          rows={2}
          style={{
            flex: 1, resize: 'none', background: T.surface2,
            border: `1px solid ${T.border}`, borderRadius: 8,
            padding: '10px 14px', color: T.text, fontFamily: F,
            fontSize: FS.sm, outline: 'none', lineHeight: 1.5,
          }}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || !tab.model || tab.isStreaming}
          style={{
            padding: '10px 14px', background: T.cyan,
            border: 'none', borderRadius: 8, color: '#000',
            cursor: !input.trim() || !tab.model || tab.isStreaming ? 'not-allowed' : 'pointer',
            opacity: !input.trim() || !tab.model || tab.isStreaming ? 0.4 : 1,
            display: 'flex', alignItems: 'center',
          }}
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  )
}

// ── Message bubble ──
function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'

  return (
    <div style={{
      display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start',
      marginBottom: 12,
    }}>
      <div style={{
        maxWidth: '75%', padding: '10px 14px',
        background: isUser ? `${T.cyan}15` : T.surface2,
        border: `1px solid ${isUser ? `${T.cyan}30` : T.border}`,
        borderRadius: isUser ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
      }}>
        <div style={{
          fontFamily: F, fontSize: FS.sm, color: T.text,
          lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
        }}>
          {message.content || (message.role === 'assistant' ? '...' : '')}
        </div>
        {message.tokenCount !== undefined && message.tokenCount > 0 && (
          <div style={{
            fontFamily: F, fontSize: '8px', color: T.dim,
            marginTop: 4, textAlign: 'right',
          }}>
            {message.tokenCount} tokens
          </div>
        )}
      </div>
    </div>
  )
}
