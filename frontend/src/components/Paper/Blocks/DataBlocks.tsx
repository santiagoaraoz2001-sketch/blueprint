import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { usePaperStore } from '@/stores/paperStore'
import { Table as TableIcon, Code, Database } from 'lucide-react'

// ============================================
// TableBlock Component
// ============================================

export function TableBlock({ sectionId, blockId, tableId }: { sectionId: string; blockId: string; tableId: string }) {
    const { updateBlock } = usePaperStore()
    // In a real app we'd fetch table data from the DB runId.
    // For this aesthetic milestone, we'll allow entering a mock table reference
    const [val, setVal] = useState(tableId)

    const handleBlur = () => {
        if (val !== tableId) {
            updateBlock(sectionId, blockId, val)
        }
    }

    return (
        <div style={{ padding: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <TableIcon size={14} color={T.green} />
                <span style={{ fontFamily: F, fontSize: FS.sm, fontWeight: 700, color: T.text }}>Database Table Reference</span>
            </div>
            <div style={{
                display: 'flex', flexDirection: 'column', gap: 4,
                background: T.surface2, padding: 12, borderRadius: 6, border: `1px solid ${T.border}`
            }}>
                <label style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 700, letterSpacing: '0.08em' }}>TABLE / RUN ID</label>
                <input
                    value={val}
                    onChange={(e) => setVal(e.target.value)}
                    onBlur={handleBlur}
                    placeholder="e.g. run_78a19_users"
                    style={{
                        background: T.surface4, border: `1px solid ${T.borderHi}`, color: T.text,
                        fontFamily: F, fontSize: FS.sm, padding: '6px 10px', borderRadius: 4, outline: 'none'
                    }}
                />
                {!tableId && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, color: T.dim, fontFamily: F, fontSize: FS.xs }}>
                        <Database size={12} />
                        <span>Connect to a run to visualize tabular data inline.</span>
                    </div>
                )}
                {tableId && (
                    <div style={{ marginTop: 8, padding: 10, background: T.surface0, border: `1px dashed ${T.borderHi}`, borderRadius: 4 }}>
                        <div style={{ fontFamily: F, fontSize: FS.sm, color: T.sec, textAlign: 'center' }}>
                            [Table preview of {tableId} would render here]
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}

// ============================================
// ModuleBlock Component
// ============================================

export function ModuleBlock({ sectionId, blockId, moduleId }: { sectionId: string; blockId: string; moduleId: string }) {
    const { updateBlock } = usePaperStore()
    const [val, setVal] = useState(moduleId)

    const handleBlur = () => {
        if (val !== moduleId) {
            updateBlock(sectionId, blockId, val)
        }
    }

    return (
        <div style={{ padding: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <Code size={14} color={T.blue} />
                <span style={{ fontFamily: F, fontSize: FS.sm, fontWeight: 700, color: T.text }}>Logic Module Reference</span>
            </div>
            <div style={{
                display: 'flex', flexDirection: 'column', gap: 4,
                background: T.surface2, padding: 12, borderRadius: 6, border: `1px solid ${T.border}`
            }}>
                <label style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 700, letterSpacing: '0.08em' }}>MODULE NAME OR CODE</label>
                <textarea
                    value={val}
                    onChange={(e) => setVal(e.target.value)}
                    onBlur={handleBlur}
                    placeholder="e.g. LLM Reasoning Agent"
                    style={{
                        background: T.surface4, border: `1px solid ${T.borderHi}`, color: T.text,
                        fontFamily: 'monospace', fontSize: FS.sm, padding: '8px 10px', borderRadius: 4, outline: 'none',
                        minHeight: 60, resize: 'vertical'
                    }}
                />
            </div>
        </div>
    )
}
