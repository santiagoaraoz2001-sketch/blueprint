import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { T, F, FS } from '@/lib/design-tokens'
import { getBlockDefinition, type BlockDefinition, type ConfigField } from '@/lib/block-registry'
import { CATEGORY_COLORS } from '@/lib/design-tokens'
import { X, Copy, Save, Trash2, Plus } from 'lucide-react'

const STORAGE_KEY = 'blueprint-custom-blocks'

export interface CustomBlock extends BlockDefinition {
    isCustom: true
    baseType: string
}

export function loadCustomBlocks(): CustomBlock[] {
    try {
        const raw = localStorage.getItem(STORAGE_KEY)
        return raw ? JSON.parse(raw) : []
    } catch { return [] }
}

function saveCustomBlocks(blocks: CustomBlock[]) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(blocks))
}

interface Props {
    visible: boolean
    onClose: () => void
    /** Pass a block type to pre-fill from (duplicate) */
    duplicateFrom?: string
    onSaved: () => void
}

export default function CustomModuleEditor({ visible, onClose, duplicateFrom, onSaved }: Props) {
    const base = duplicateFrom
        ? getBlockDefinition(duplicateFrom) || loadCustomBlocks().find(b => b.type === duplicateFrom)
        : null

    const [name, setName] = useState(base ? `${base.name} (Custom)` : 'My Custom Module')
    const [description, setDescription] = useState(base?.description || '')
    const [category, setCategory] = useState(base?.category || 'source')
    const [icon, setIcon] = useState(base?.icon || 'Box')
    const [configFields, setConfigFields] = useState<ConfigField[]>(base?.configFields || [])
    const [defaultConfig, setDefaultConfig] = useState<Record<string, any>>(base?.defaultConfig || {})

    useEffect(() => {
        if (base) {
            setName(`${base.name} (Custom)`)
            setDescription(base.description)
            setCategory(base.category)
            setIcon(base.icon)
            setConfigFields([...base.configFields])
            setDefaultConfig({ ...base.defaultConfig })
        }
    }, [duplicateFrom])

    const handleSave = () => {
        const typeId = `custom_${name.toLowerCase().replace(/[^a-z0-9]/g, '_')}_${Date.now()}`
        const custom: CustomBlock = {
            type: typeId,
            name,
            description,
            category,
            tags: [category, 'custom'],
            aliases: [name.toLowerCase()],
            icon,
            accent: CATEGORY_COLORS[category] || '#94A3B8',
            inputs: base?.inputs ? [...base.inputs] : [],
            outputs: base?.outputs ? [...base.outputs] : [],
            defaultConfig: { ...defaultConfig },
            configFields: [...configFields],
            version: '1.0.0',
            isCustom: true,
            baseType: base?.type || '',
            maturity: 'experimental',
        }

        const existing = loadCustomBlocks()
        saveCustomBlocks([...existing, custom])
        onSaved()
        onClose()
    }

    const handleAddConfigField = () => {
        const newField: ConfigField = { name: `field_${configFields.length + 1}`, label: 'New Field', type: 'string' }
        setConfigFields([...configFields, newField])
    }

    const handleUpdateField = (idx: number, updates: Partial<ConfigField>) => {
        setConfigFields(prev => prev.map((f, i) => i === idx ? { ...f, ...updates } : f))
    }

    const handleRemoveField = (idx: number) => {
        setConfigFields(prev => prev.filter((_, i) => i !== idx))
    }

    if (!visible) return null

    return (
        <AnimatePresence>
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                style={{
                    position: 'fixed', inset: 0, zIndex: 10000,
                    background: T.shadowHeavy, display: 'flex',
                    alignItems: 'center', justifyContent: 'center',
                }}
                onClick={onClose}
            >
                <motion.div
                    initial={{ scale: 0.95, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    exit={{ scale: 0.95, opacity: 0 }}
                    onClick={(e) => e.stopPropagation()}
                    style={{
                        width: 520, maxHeight: '80vh', overflowY: 'auto',
                        background: T.surface1, border: `1px solid ${T.borderHi}`,
                        borderRadius: 8, boxShadow: `0 16px 64px ${T.shadow}`,
                    }}
                >
                    {/* Header */}
                    <div style={{
                        display: 'flex', alignItems: 'center', padding: '14px 18px',
                        borderBottom: `1px solid ${T.border}`, gap: 10,
                    }}>
                        <Copy size={14} color={T.cyan} />
                        <span style={{ fontFamily: F, fontSize: FS.lg, fontWeight: 700, color: T.text, flex: 1 }}>
                            {duplicateFrom ? 'Duplicate & Customize' : 'Create Custom Module'}
                        </span>
                        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.dim }}>
                            <X size={14} />
                        </button>
                    </div>

                    {/* Form */}
                    <div style={{ padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
                        {/* Name */}
                        <div>
                            <label style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 700, letterSpacing: '0.1em', display: 'block', marginBottom: 4 }}>
                                NAME
                            </label>
                            <input value={name} onChange={e => setName(e.target.value)} style={{
                                width: '100%', padding: '8px 12px', background: T.surface3, border: `1px solid ${T.border}`,
                                borderRadius: 6, color: T.text, fontFamily: F, fontSize: FS.sm, outline: 'none', boxSizing: 'border-box',
                            }} />
                        </div>

                        {/* Description */}
                        <div>
                            <label style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 700, letterSpacing: '0.1em', display: 'block', marginBottom: 4 }}>
                                DESCRIPTION
                            </label>
                            <textarea value={description} onChange={e => setDescription(e.target.value)} rows={3} style={{
                                width: '100%', padding: '8px 12px', background: T.surface3, border: `1px solid ${T.border}`,
                                borderRadius: 6, color: T.text, fontFamily: F, fontSize: FS.sm, outline: 'none', resize: 'vertical', boxSizing: 'border-box',
                            }} />
                        </div>

                        {/* Category */}
                        <div>
                            <label style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 700, letterSpacing: '0.1em', display: 'block', marginBottom: 4 }}>
                                CATEGORY
                            </label>
                            <select value={category} onChange={e => setCategory(e.target.value)} style={{
                                width: '100%', padding: '8px 12px', background: T.surface3, border: `1px solid ${T.border}`,
                                borderRadius: 6, color: T.text, fontFamily: F, fontSize: FS.sm, outline: 'none',
                            }}>
                                {['external', 'data', 'model', 'training', 'metrics', 'embedding', 'utilities', 'agents'].map(c => (
                                    <option key={c} value={c}>{c.toUpperCase()}</option>
                                ))}
                            </select>
                        </div>

                        {/* Config Fields */}
                        <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 700, letterSpacing: '0.1em' }}>
                                    CONFIGURATION FIELDS
                                </span>
                                <button onClick={handleAddConfigField} style={{
                                    background: `${T.cyan}15`, border: `1px solid ${T.cyan}30`, borderRadius: 4,
                                    color: T.cyan, fontFamily: F, fontSize: FS.xxs, padding: '2px 8px', cursor: 'pointer',
                                    display: 'flex', alignItems: 'center', gap: 4,
                                }}>
                                    <Plus size={10} /> ADD
                                </button>
                            </div>

                            {configFields.map((field, idx) => (
                                <div key={idx} style={{
                                    display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6,
                                    padding: '6px 8px', background: T.surface2, borderRadius: 6, border: `1px solid ${T.border}`,
                                }}>
                                    <input value={field.label} onChange={e => handleUpdateField(idx, { label: e.target.value })}
                                        placeholder="Label" style={{
                                            flex: 1, background: T.surface3, border: `1px solid ${T.border}`, borderRadius: 4,
                                            padding: '4px 8px', color: T.text, fontFamily: F, fontSize: FS.xxs, outline: 'none',
                                        }} />
                                    <select value={field.type} onChange={e => handleUpdateField(idx, { type: e.target.value as any })} style={{
                                        background: T.surface3, border: `1px solid ${T.border}`, borderRadius: 4,
                                        padding: '4px 6px', color: T.text, fontFamily: F, fontSize: FS.xxs, outline: 'none',
                                    }}>
                                        {['string', 'integer', 'float', 'boolean', 'select', 'text_area', 'file_path'].map(t => (
                                            <option key={t} value={t}>{t}</option>
                                        ))}
                                    </select>
                                    <button onClick={() => handleRemoveField(idx)} style={{
                                        background: 'none', border: 'none', cursor: 'pointer', color: T.dim, padding: 2,
                                    }}>
                                        <Trash2 size={10} />
                                    </button>
                                </div>
                            ))}
                        </div>

                        {/* Default config overrides */}
                        {Object.keys(defaultConfig).length > 0 && (
                            <div>
                                <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, fontWeight: 700, letterSpacing: '0.1em', display: 'block', marginBottom: 6 }}>
                                    DEFAULT VALUES
                                </span>
                                {Object.entries(defaultConfig).map(([key, val]) => (
                                    <div key={key} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                                        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, width: 120 }}>{key}</span>
                                        <input
                                            value={typeof val === 'object' ? JSON.stringify(val) : String(val)}
                                            onChange={e => setDefaultConfig(prev => ({ ...prev, [key]: e.target.value }))}
                                            style={{
                                                flex: 1, padding: '4px 8px', background: T.surface3, border: `1px solid ${T.border}`,
                                                borderRadius: 4, color: T.text, fontFamily: F, fontSize: FS.xxs, outline: 'none',
                                            }}
                                        />
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Footer */}
                    <div style={{
                        display: 'flex', justifyContent: 'flex-end', padding: '12px 18px',
                        borderTop: `1px solid ${T.border}`, gap: 10,
                    }}>
                        <button onClick={onClose} style={{
                            padding: '8px 16px', background: T.surface3, border: `1px solid ${T.border}`,
                            borderRadius: 6, color: T.dim, fontFamily: F, fontSize: FS.sm, cursor: 'pointer',
                        }}>
                            Cancel
                        </button>
                        <button onClick={handleSave} style={{
                            padding: '8px 20px', background: T.cyan, border: 'none',
                            borderRadius: 6, color: '#000', fontFamily: F, fontSize: FS.sm, fontWeight: 700, cursor: 'pointer',
                            display: 'flex', alignItems: 'center', gap: 6,
                        }}>
                            <Save size={12} /> Save Module
                        </button>
                    </div>
                </motion.div>
            </motion.div>
        </AnimatePresence>
    )
}
