import { useState } from 'react'
import { T, F, FS } from '@/lib/design-tokens'
import { FileText, BarChart3, Table, Code, ChevronRight } from 'lucide-react'

export interface PaperPaletteBlock {
    type: 'markdown' | 'chart' | 'table' | 'module'
    label: string
    description: string
    icon: React.ElementType
    color: string
}

export const PAPER_BLOCK_TYPES: PaperPaletteBlock[] = [
    {
        type: 'markdown',
        label: 'Text (Markdown)',
        description: 'Rich editable text blocks',
        icon: FileText,
        color: T.cyan,
    },
    {
        type: 'chart',
        label: 'Chart Visualization',
        description: 'Insert a chart from a pipeline run',
        icon: BarChart3,
        color: T.purple,
    },
    {
        type: 'table',
        label: 'Database Table',
        description: 'Embed results from a pipeline execution',
        icon: Table,
        color: T.green,
    },
    {
        type: 'module',
        label: 'Logic Core',
        description: 'Reference a block definition directly',
        icon: Code,
        color: T.blue,
    },
]

export default function PaperBlockLibrary() {
    const [collapsed, setCollapsed] = useState(false)

    const onDragStart = (e: React.DragEvent, blockType: string) => {
        e.dataTransfer.setData('application/blueprint-paper-block', blockType)
        e.dataTransfer.effectAllowed = 'copy'
    }

    return (
        <div
            style={{
                width: 260,
                minWidth: 260,
                height: '100%',
                background: `linear-gradient(180deg, ${T.surface1} 0%, ${T.surface0} 100%)`,
                backdropFilter: 'blur(10px)',
                borderRight: `1px solid ${T.border}`,
                display: 'flex',
                flexDirection: 'column',
                overflow: 'hidden',
                boxShadow: 'inset -1px 0 0 rgba(255,255,255,0.02)',
            }}
        >
            {/* Header */}
            <div
                style={{
                    padding: '12px 14px',
                    borderBottom: `1px solid ${T.border}`,
                    background: 'rgba(255,255,255,0.01)'
                }}
            >
                <span
                    style={{
                        fontFamily: F,
                        fontSize: FS.xs,
                        fontWeight: 800,
                        letterSpacing: '0.15em',
                        color: T.dim,
                    }}
                >
                    BLOCK PALETTE
                </span>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', padding: '12px 0' }}>
                {/* Category Header */}
                <div
                    onClick={() => setCollapsed(!collapsed)}
                    style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        padding: '6px 14px', cursor: 'pointer',
                        transition: 'color 0.15s'
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.color = T.text}
                    onMouseLeave={(e) => e.currentTarget.style.color = T.dim}
                >
                    <ChevronRight
                        size={12}
                        color={T.dim}
                        style={{
                            transform: collapsed ? 'none' : 'rotate(90deg)',
                            transition: 'transform 0.2s ease'
                        }}
                    />
                    <span
                        style={{
                            fontFamily: F, fontSize: FS.xxs, fontWeight: 700,
                            color: T.text, letterSpacing: '0.12em',
                        }}
                    >
                        ELEMENTS
                    </span>
                </div>

                {/* Blocks list */}
                {!collapsed && (
                    <div style={{ padding: '4px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {PAPER_BLOCK_TYPES.map((block) => {
                            const IconComponent = block.icon
                            return (
                                <div
                                    key={block.type}
                                    draggable
                                    onDragStart={(e) => onDragStart(e, block.type)}
                                    style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 10,
                                        padding: '8px 10px',
                                        background: T.surface2,
                                        border: `1px solid ${T.borderHi}`,
                                        borderRadius: 6,
                                        cursor: 'grab',
                                        transition: 'all 0.15s ease',
                                        position: 'relative',
                                        overflow: 'hidden',
                                    }}
                                    onMouseEnter={(e) => {
                                        e.currentTarget.style.borderColor = block.color
                                        e.currentTarget.style.background = T.surface3
                                        e.currentTarget.style.boxShadow = `0 4px 12px ${block.color}15`
                                        e.currentTarget.style.transform = 'translateY(-1px)'
                                    }}
                                    onMouseLeave={(e) => {
                                        e.currentTarget.style.borderColor = T.borderHi
                                        e.currentTarget.style.background = T.surface2
                                        e.currentTarget.style.boxShadow = 'none'
                                        e.currentTarget.style.transform = 'none'
                                    }}
                                >
                                    {/* Decorative side border */}
                                    <div style={{
                                        position: 'absolute', left: 0, top: 0, bottom: 0,
                                        width: 3, background: block.color, opacity: 0.8
                                    }} />

                                    <div
                                        style={{
                                            width: 24, height: 24, borderRadius: 4,
                                            background: `${block.color}1a`, border: `1px solid ${block.color}33`,
                                            display: 'flex', alignItems: 'center', justifyContent: 'center'
                                        }}
                                    >
                                        <IconComponent size={12} color={block.color} />
                                    </div>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ fontFamily: F, fontSize: FS.sm, fontWeight: 600, color: T.text }}>
                                            {block.label}
                                        </div>
                                        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                                            {block.description}
                                        </div>
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                )}
            </div>
        </div>
    )
}
