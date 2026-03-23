import { motion, AnimatePresence } from 'framer-motion'
import { T, F, FS } from '@/lib/design-tokens'
import { getPortColor, type PortType } from '@/lib/block-registry'

interface EdgePreviewPanelProps {
    visible: boolean
    x: number
    y: number
    dataType: string
}

export default function EdgePreviewPanel({ visible, x, y, dataType }: EdgePreviewPanelProps) {
    if (!visible) return null

    // Generate a mock display based on the connector type
    const renderContent = () => {
        switch (dataType) {
            case 'dataset':
                return (
                    <div style={{ padding: 12 }}>
                        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Dataset Stream</div>
                        <pre style={{ margin: 0, fontFamily: F, fontSize: 10, color: T.text, background: T.surface0, padding: 8, borderRadius: 4, border: `1px solid ${T.borderHi}`, overflowX: 'hidden' }}>
                            {`[
  { "id": 1, "text": "Sample interaction...", "label": 1 },
  { "id": 2, "text": "Another example...", "label": 0 },
  ... (10,482 rows)
]`}
                        </pre>
                    </div>
                )
            case 'text':
                return (
                    <div style={{ padding: 12 }}>
                        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Text Stream</div>
                        <pre style={{ margin: 0, fontFamily: F, fontSize: 10, color: T.text, background: T.surface0, padding: 8, borderRadius: 4, border: `1px solid ${T.borderHi}`, overflowX: 'hidden' }}>
                            {`"You are a helpful assistant.
Summarize the following document
in 3 bullet points..."`}
                        </pre>
                    </div>
                )
            case 'model':
                return (
                    <div style={{ padding: 12 }}>
                        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Model State</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: F, fontSize: FS.xs }}>
                                <span style={{ color: T.sec }}>Status:</span>
                                <span style={{ color: T.green }}>Ready/Loaded</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: F, fontSize: FS.xs }}>
                                <span style={{ color: T.sec }}>Architecture:</span>
                                <span style={{ color: T.text }}>Transformer (13B)</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: F, fontSize: FS.xs }}>
                                <span style={{ color: T.sec }}>Context:</span>
                                <span style={{ color: T.text }}>8192 tokens</span>
                            </div>
                        </div>
                    </div>
                )
            case 'config':
                return (
                    <div style={{ padding: 12 }}>
                        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Configuration</div>
                        <pre style={{ margin: 0, fontFamily: F, fontSize: 10, color: T.text, background: T.surface0, padding: 8, borderRadius: 4, border: `1px solid ${T.borderHi}`, overflowX: 'hidden' }}>
                            {`{
  "learning_rate": 1e-4,
  "batch_size": 32,
  "warmup_steps": 100,
  "optimizer": "adamw"
}`}
                        </pre>
                    </div>
                )
            case 'metrics':
                return (
                    <div style={{ padding: 12 }}>
                        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Evaluation Buffer</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: F, fontSize: FS.xs }}>
                                <span style={{ color: T.sec }}>Accuracy:</span>
                                <span style={{ color: T.text }}>--</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: F, fontSize: FS.xs }}>
                                <span style={{ color: T.sec }}>F1 Score:</span>
                                <span style={{ color: T.text }}>--</span>
                            </div>
                        </div>
                    </div>
                )
            case 'embedding':
                return (
                    <div style={{ padding: 12 }}>
                        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Embedding Vector</div>
                        <pre style={{ margin: 0, fontFamily: F, fontSize: 10, color: T.text, background: T.surface0, padding: 8, borderRadius: 4, border: `1px solid ${T.borderHi}`, overflowX: 'hidden' }}>
                            {`[0.0234, -0.1128, 0.0891, ...]
dim: 768, normalized: true`}
                        </pre>
                    </div>
                )
            case 'artifact':
                return (
                    <div style={{ padding: 12 }}>
                        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Artifact Package</div>
                        <pre style={{ margin: 0, fontFamily: F, fontSize: 10, color: T.text, background: T.surface0, padding: 8, borderRadius: 4, border: `1px solid ${T.borderHi}`, overflowX: 'hidden' }}>
                            {`{
  "type": "report",
  "format": "pdf",
  "size": "2.4 MB",
  "pages": 12
}`}
                        </pre>
                    </div>
                )
            case 'agent':
                return (
                    <div style={{ padding: 12 }}>
                        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Agent Instance</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: F, fontSize: FS.xs }}>
                                <span style={{ color: T.sec }}>Status:</span>
                                <span style={{ color: T.green }}>Active</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: F, fontSize: FS.xs }}>
                                <span style={{ color: T.sec }}>Tools:</span>
                                <span style={{ color: T.text }}>5 registered</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: F, fontSize: FS.xs }}>
                                <span style={{ color: T.sec }}>Memory:</span>
                                <span style={{ color: T.text }}>Enabled</span>
                            </div>
                        </div>
                    </div>
                )
            case 'llm':
                return (
                    <div style={{ padding: 12 }}>
                        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.1em' }}>LLM Provider Config</div>
                        <pre style={{ margin: 0, fontFamily: F, fontSize: 10, color: T.text, background: T.surface0, padding: 8, borderRadius: 4, border: `1px solid ${T.borderHi}`, overflowX: 'hidden' }}>
                            {`{
  "provider": "ollama",
  "model": "llama3.2",
  "temperature": 0.7,
  "max_tokens": 2048
}`}
                        </pre>
                    </div>
                )
            case 'any':
                return (
                    <div style={{ padding: 12 }}>
                        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Generic Pass-Through</div>
                        <div style={{ fontFamily: F, fontSize: FS.xs, color: T.sec }}>
                            Accepts any data type — used for flow control, routing, and type-agnostic operations.
                        </div>
                    </div>
                )
            default:
                return (
                    <div style={{ padding: 12 }}>
                        <div style={{ fontFamily: F, fontSize: FS.xs, color: T.sec }}>
                            A stream of <strong style={{ color: getPortColor(dataType as PortType) }}>{dataType}</strong> data passing between blocks.
                        </div>
                    </div>
                )
        }
    }

    return (
        <AnimatePresence>
            <motion.div
                initial={{ opacity: 0, scale: 0.95, y: -4 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: -4 }}
                transition={{ duration: 0.15 }}
                style={{
                    position: 'fixed',
                    left: x + 15,
                    top: y + 15,
                    width: 280,
                    background: `linear-gradient(145deg, ${T.surface2} 0%, ${T.surface1} 100%)`,
                    border: `1px solid ${T.borderHi}`,
                    borderRadius: 8,
                    boxShadow: `0 8px 32px ${T.shadow}`,
                    zIndex: 9999,
                    pointerEvents: 'none', // Don't block mouse
                    overflow: 'hidden',
                }}
            >
                <div style={{ height: 3, background: getPortColor(dataType as PortType) }} />
                {renderContent()}
            </motion.div>
        </AnimatePresence>
    )
}
