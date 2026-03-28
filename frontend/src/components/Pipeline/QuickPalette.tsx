import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { T, F, FS } from '@/lib/design-tokens'
import { getAllBlocks, isPortCompatible } from '@/lib/block-registry'
import { getIcon } from '@/lib/icon-utils'

interface QuickPaletteProps {
    visible: boolean
    x: number
    y: number
    sourceType: string
    sourceNodeId: string
    sourceHandleId: string
    onSelect: (blockType: string) => void
    onClose: () => void
}

export default function QuickPalette({ visible, x, y, sourceType, onClose, onSelect }: QuickPaletteProps) {
    const [searchTerm, setSearchTerm] = useState('')

    useEffect(() => {
        if (visible) setSearchTerm('')
    }, [visible])

    // Filter blocks that have an input port compatible with the source output port type
    const compatibleBlocks = getAllBlocks().filter((block) => {
        return block.inputs.some((input) => isPortCompatible(sourceType, input.dataType))
    })

    const q = searchTerm.toLowerCase()
    const filteredBlocks = compatibleBlocks.filter((block) =>
        block.name.toLowerCase().includes(q) ||
        block.description.toLowerCase().includes(q) ||
        block.aliases?.some((a: string) => a.toLowerCase().includes(q)) ||
        block.tags?.some((t: string) => t.toLowerCase().includes(q))
    )

    if (!visible) return null

    return (
        <AnimatePresence>
            <motion.div
                initial={{ opacity: 0, scale: 0.9, y: 10 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.9, y: 10 }}
                transition={{ type: 'spring', damping: 25, stiffness: 300 }}
                style={{
                    position: 'fixed',
                    left: x,
                    top: y,
                    width: 320,
                    background: `linear-gradient(145deg, ${T.surface2} 0%, ${T.surface1} 100%)`,
                    border: `1px solid ${T.borderHi}`,
                    borderRadius: 8,
                    boxShadow: `0 16px 48px ${T.shadow}`,
                    zIndex: 1000,
                    display: 'flex',
                    flexDirection: 'column',
                    maxHeight: 400,
                    overflow: 'hidden',
                }}
            >
                {/* Header/Search */}
                <div style={{ padding: 8, borderBottom: `1px solid ${T.borderHi}` }}>
                    <input
                        autoFocus
                        type="text"
                        placeholder={`Connect ${sourceType} to...`}
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Escape') onClose()
                            if (e.key === 'Enter' && filteredBlocks.length > 0) {
                                onSelect(filteredBlocks[0].type)
                            }
                        }}
                        style={{
                            width: '100%',
                            background: T.surface3,
                            border: `1px solid ${T.border}`,
                            borderRadius: 4,
                            padding: '6px 10px',
                            fontFamily: F,
                            fontSize: FS.sm,
                            color: T.text,
                            outline: 'none',
                            boxShadow: `inset 0 1px 2px rgba(0,0,0,0.2)`,
                        }}
                    />
                </div>

                {/* List of suggestions */}
                <div style={{ overflowY: 'auto', padding: 4, display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {filteredBlocks.length === 0 ? (
                        <div style={{ padding: 12, textAlign: 'center', fontFamily: F, fontSize: FS.sm, color: T.dim }}>
                            No compatible blocks found.
                        </div>
                    ) : (
                        filteredBlocks.map((block) => {
                            const IconComp = getIcon(block.icon)
                            const accent = block.accent || T.cyan
                            return (
                                <button
                                    key={block.type}
                                    onClick={() => onSelect(block.type)}
                                    onMouseEnter={(e) => { e.currentTarget.style.background = `${accent}15` }}
                                    onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                                    style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 10,
                                        padding: '8px 10px',
                                        background: 'transparent',
                                        border: 'none',
                                        borderRadius: 4,
                                        cursor: 'pointer',
                                        textAlign: 'left',
                                        transition: 'background 0.1s',
                                    }}
                                >
                                    <div
                                        style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            width: 24,
                                            height: 24,
                                            borderRadius: 4,
                                            background: `linear-gradient(135deg, ${T.surface3}, ${T.surface1})`,
                                            border: `1px solid ${T.borderHi}`,
                                        }}
                                    >
                                        <IconComp size={12} color={accent} />
                                    </div>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                            {block.name}
                                        </div>
                                        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                            {block.description}
                                        </div>
                                    </div>
                                </button>
                            )
                        })
                    )}
                </div>
            </motion.div>
        </AnimatePresence>
    )
}
