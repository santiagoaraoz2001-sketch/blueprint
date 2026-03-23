import { useState } from 'react'
import { T, F, FS, FD } from '@/lib/design-tokens'
import { Send, X, Bot, User } from 'lucide-react'
import { api } from '@/api/client'
import toast from 'react-hot-toast'

interface Props {
    modelId: string
    onClose: () => void
}

interface Message {
    role: 'user' | 'assistant'
    content: string
}

export default function ChatInterface({ modelId, onClose }: Props) {
    const [messages, setMessages] = useState<Message[]>([])
    const [input, setInput] = useState('')
    const [loading, setLoading] = useState(false)

    const handleSend = async () => {
        if (!input.trim() || loading) return

        const userMsg = input.trim()
        setMessages(prev => [...prev, { role: 'user', content: userMsg }])
        setInput('')
        setLoading(true)

        try {
            const res = await api.post<{ text: string }>(`/models/${encodeURIComponent(modelId)}/inference`, {
                prompt: userMsg,
                max_tokens: 150,
                temperature: 0.7
            })
            setMessages(prev => [...prev, { role: 'assistant', content: res.text }])
        } catch (e: any) {
            toast.error('Inference failed')
            setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${e.message || 'Failed'}` }])
        } finally {
            setLoading(false)
        }
    }

    return (
        <div style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            background: T.shadowHeavy,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
        }}>
            <div style={{
                width: 600,
                height: 500,
                background: T.surface0,
                border: `1px solid ${T.border}`,
                display: 'flex',
                flexDirection: 'column',
                boxShadow: `0 20px 40px ${T.shadow}`,
            }}>
                {/* Header */}
                <div style={{
                    padding: '12px 16px',
                    borderBottom: `1px solid ${T.border}`,
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    background: T.surface1,
                }}>
                    <div>
                        <h3 style={{ fontFamily: FD, fontSize: FS.md, color: T.text, margin: 0 }}>Vibe Check</h3>
                        <span style={{ fontFamily: F, fontSize: FS.xs, color: T.dim }}>{modelId}</span>
                    </div>
                    <button onClick={onClose} style={{
                        background: 'none', border: 'none', color: T.dim, cursor: 'pointer'
                    }}>
                        <X size={14} />
                    </button>
                </div>

                {/* Messages */}
                <div style={{
                    flex: 1,
                    overflowY: 'auto',
                    padding: 16,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 12,
                }}>
                    {messages.length === 0 ? (
                        <div style={{ margin: 'auto', textAlign: 'center', color: T.dim, fontFamily: F, fontSize: FS.sm }}>
                            Start chatting to vibe check this model.
                        </div>
                    ) : (
                        messages.map((m, i) => (
                            <div key={i} style={{
                                display: 'flex', gap: 12,
                                flexDirection: m.role === 'user' ? 'row-reverse' : 'row'
                            }}>
                                <div style={{
                                    width: 28, height: 28, borderRadius: 14,
                                    background: m.role === 'user' ? T.surface3 : `${T.cyan}20`,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    color: m.role === 'user' ? T.sec : T.cyan,
                                    flexShrink: 0
                                }}>
                                    {m.role === 'user' ? <User size={14} /> : <Bot size={14} />}
                                </div>
                                <div style={{
                                    background: m.role === 'user' ? T.surface2 : 'transparent',
                                    border: m.role === 'user' ? `1px solid ${T.border}` : 'none',
                                    padding: m.role === 'user' ? '8px 12px' : '6px 0',
                                    borderRadius: 4,
                                    color: T.text,
                                    fontFamily: F,
                                    fontSize: FS.sm,
                                    lineHeight: 1.5,
                                    maxWidth: '80%',
                                    whiteSpace: 'pre-wrap'
                                }}>
                                    {m.content}
                                </div>
                            </div>
                        ))
                    )}
                    {loading && (
                        <div style={{ display: 'flex', gap: 12 }}>
                            <div style={{
                                width: 28, height: 28, borderRadius: 14, background: `${T.cyan}20`,
                                display: 'flex', alignItems: 'center', justifyContent: 'center', color: T.cyan
                            }}>
                                <Bot size={14} />
                            </div>
                            <div style={{ padding: '6px 0', color: T.dim, fontFamily: F, fontSize: FS.sm }}>Generating...</div>
                        </div>
                    )}
                </div>

                {/* Input */}
                <div style={{
                    padding: 12,
                    borderTop: `1px solid ${T.border}`,
                    background: T.surface1,
                }}>
                    <div style={{ display: 'flex', gap: 8 }}>
                        <input
                            value={input}
                            onChange={e => setInput(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && handleSend()}
                            placeholder="Ask the model something..."
                            style={{
                                flex: 1,
                                background: T.surface2,
                                border: `1px solid ${T.border}`,
                                padding: '8px 12px',
                                color: T.text,
                                fontFamily: F,
                                fontSize: FS.sm,
                                outline: 'none',
                            }}
                        />
                        <button
                            onClick={handleSend}
                            disabled={loading || !input.trim()}
                            style={{
                                background: T.cyan,
                                border: 'none',
                                color: '#000',
                                padding: '0 16px',
                                cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
                                opacity: loading || !input.trim() ? 0.5 : 1,
                                display: 'flex', alignItems: 'center', justifyContent: 'center'
                            }}
                        >
                            <Send size={14} />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    )
}
