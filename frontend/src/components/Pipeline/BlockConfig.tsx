import { T, F, FS } from '@/lib/design-tokens'
import { usePipelineStore, type BlockNodeData } from '@/stores/pipelineStore'
import { getBlockDefinition, getFileFormatWarning, type ConfigField, type ConnectorType } from '@/lib/block-registry'
import { usePresetStore } from '@/stores/presetStore'
import { motion, AnimatePresence } from 'framer-motion'
import { getIcon } from '@/lib/icon-utils'
import { Trash2, X, Save, ChevronDown, AlertTriangle } from 'lucide-react'
import type { Node } from '@xyflow/react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '@/api/client'
import RecommendedBlocks from './RecommendedBlocks'
import toast from 'react-hot-toast'

export default function BlockConfig() {
  const nodes = usePipelineStore((s) => s.nodes)
  const selectedNodeId = usePipelineStore((s) => s.selectedNodeId)
  const node = nodes.find((n) => n.id === selectedNodeId)

  // Show RecommendedBlocks when no block is selected
  if (!node) {
    return <RecommendedBlocks />
  }

  return (
    <AnimatePresence mode="wait">
      <BlockConfigInner key={node.id} node={node} />
    </AnimatePresence>
  )
}

function BlockConfigInner({ node }: { node: Node<BlockNodeData> }) {
  const updateNodeConfig = usePipelineStore((s) => s.updateNodeConfig)
  const removeNode = usePipelineStore((s) => s.removeNode)
  const selectNode = usePipelineStore((s) => s.selectNode)
  const def = getBlockDefinition(node.data.type)
  const IconComponent = getIcon(node.data.icon)

  const handleConfigChange = (name: string, value: string | number | boolean) => {
    updateNodeConfig(node.id, { [name]: value })
  }

  const [availableModels, setAvailableModels] = useState<Record<string, any[]>>({})

  useEffect(() => {
    if (def?.type === 'llm_inference') {
      api.get<Record<string, any[]>>('/models/available')
        .then(data => {
          if (data && typeof data === 'object') {
            setAvailableModels(data)
          }
        })
        .catch(() => {
          // Fallback to /models/local
          api.get<any[]>('/models/local')
            .then(data => {
              if (Array.isArray(data)) {
                setAvailableModels({ ollama: data.map(m => ({ name: typeof m === 'string' ? m : (m.name || m.id || '') })) })
              }
            })
            .catch(err => console.error('Failed to fetch models', err))
        })
    }
  }, [def?.type])

  // Filter config fields by depends_on and enrich model_name with auto-detected options
  const displayFields = def?.configFields
    .filter(f => {
      if (!f.depends_on) return true
      return node.data.config[f.depends_on.field] === f.depends_on.value
    })
    .map(f => {
      // Auto-populate model_name / model_path with detected models
      if (def.type === 'llm_inference' && (f.name === 'model_name' || f.name === 'model_path' || f.name === 'file_path')) {
        const backend = node.data.config.backend || 'ollama'
        const models = availableModels[backend] || []
        if (models.length > 0) {
          const modelNames = models.map((m: any) => m.name || m.path || String(m))
          return { ...f, type: 'select' as const, options: modelNames } as ConfigField
        }
      }
      return f
    })

  return (
    <motion.div
      data-tour="config-panel"
      initial={{ opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 24 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      style={{
        width: 320,
        minWidth: 320,
        height: '100%',
        background: `linear-gradient(180deg, ${T.surface1} 0%, ${T.surface0} 100%)`,
        backdropFilter: 'blur(10px)',
        borderLeft: `1px solid ${T.border}`,
        boxShadow: `inset 1px 0 0 rgba(255,255,255,0.02), -8px 0 24px ${T.shadow}`,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      {/* Decorative vertical bar tied to node accent */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          bottom: 0,
          width: 3,
          background: node.data.accent,
          boxShadow: `0 0 12px ${node.data.accent}40`,
          opacity: 0.8,
        }}
      />

      {/* Header */}
      <div
        style={{
          padding: '16px 20px',
          borderBottom: `1px solid ${T.border}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'rgba(255,255,255,0.01)',
          position: 'relative',
          zIndex: 1,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 32,
            height: 32,
            borderRadius: 8,
            background: `linear-gradient(135deg, ${T.surface3}, ${T.surface1})`,
            border: `1px solid ${T.borderHi}`,
            boxShadow: `0 2px 8px ${T.shadowLight}`
          }}>
            <IconComponent size={16} color={node.data.accent} />
          </div>
          <div>
            <div
              style={{
                fontFamily: F,
                fontSize: FS.md,
                color: T.text,
                fontWeight: 700,
                letterSpacing: '0.04em',
              }}
            >
              {node.data.label}
            </div>
            <div
              style={{
                fontFamily: F,
                fontSize: FS.xxs,
                color: node.data.accent,
                letterSpacing: '0.14em',
                textTransform: 'uppercase',
                fontWeight: 600,
                marginTop: 2,
              }}
            >
              {node.data.category}
            </div>
          </div>
        </div>
        <button
          onClick={() => selectNode(null)}
          style={{
            background: 'none',
            border: 'none',
            color: T.dim,
            display: 'flex',
            padding: 4,
            cursor: 'pointer',
            transition: 'color 0.15s'
          }}
          onMouseEnter={e => e.currentTarget.style.color = T.text}
          onMouseLeave={e => e.currentTarget.style.color = T.dim}
        >
          <X size={14} />
        </button>
      </div>

      {/* Config fields */}
      <div style={{ flex: 1, overflow: 'auto', padding: '20px', scrollbarWidth: 'thin' }}>
        <span
          style={{
            fontFamily: F,
            fontSize: FS.xs,
            color: T.dim,
            letterSpacing: '0.16em',
            fontWeight: 900,
            textTransform: 'uppercase',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginBottom: 16,
          }}
        >
          CONFIGURATION
          <div style={{ flex: 1, height: 1, background: T.border }} />
        </span>

        {/* Preset selector */}
        {def && <PresetSelector blockType={def.type} nodeId={node.id} currentConfig={node.data.config} />}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {displayFields?.map((field) => (
            <ConfigFieldInput
              key={field.name}
              field={field}
              value={node.data.config[field.name] ?? field.default ?? ''}
              onChange={(v) => handleConfigChange(field.name, v)}
              expectedOutputType={def?.outputs[0]?.dataType as ConnectorType | undefined}
            />
          ))}
        </div>

        {/* Inputs/Outputs info */}
        {def && (def.inputs.length > 0 || def.outputs.length > 0) && (
          <div style={{ marginTop: 32 }}>
            <span
              style={{
                fontFamily: F,
                fontSize: FS.xs,
                color: T.dim,
                letterSpacing: '0.16em',
                fontWeight: 900,
                textTransform: 'uppercase',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                marginBottom: 16,
              }}
            >
              PORTS
              <div style={{ flex: 1, height: 1, background: T.border }} />
            </span>

            <div style={{ display: 'grid', gap: 10 }}>
              {def.inputs.map((p) => (
                <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: `${T.cyan}0a`, border: `1px solid ${T.cyan}20`, borderRadius: 6 }}>
                  <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.cyan, fontWeight: 800, letterSpacing: '0.1em' }}>IN</span>
                  <span style={{ flex: 1, fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 500 }}>{p.label}</span>
                  <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>({p.dataType})</span>
                </div>
              ))}
              {def.outputs.map((p) => (
                <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: `${T.green}0a`, border: `1px solid ${T.green}20`, borderRadius: 6 }}>
                  <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.green, fontWeight: 800, letterSpacing: '0.1em' }}>OUT</span>
                  <span style={{ flex: 1, fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 500 }}>{p.label}</span>
                  <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>({p.dataType})</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div
        style={{
          padding: '16px 20px',
          borderTop: `1px solid ${T.border}`,
          background: T.shadowLight,
        }}
      >
        <button
          onClick={() => removeNode(node.id)}
          className="hover-glow"
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            padding: '8px 12px',
            background: `${T.red}1a`,
            border: `1px solid ${T.red}33`,
            borderRadius: 6,
            color: T.red,
            fontFamily: F,
            fontSize: FS.xs,
            fontWeight: 800,
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          onMouseEnter={e => e.currentTarget.style.background = `${T.red}2a`}
          onMouseLeave={e => e.currentTarget.style.background = `${T.red}1a`}
        >
          <Trash2 size={12} />
          DELETE BLOCK
        </button>
      </div>
    </motion.div>
  )
}

type ConfigValue = string | number | boolean

function ConfigFieldInput({
  field,
  value,
  onChange,
  expectedOutputType,
}: {
  field: ConfigField
  value: ConfigValue
  onChange: (v: ConfigValue) => void
  expectedOutputType?: ConnectorType
}) {
  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 12px',
    background: T.surface3,
    border: `1px solid ${T.borderHi}`,
    borderRadius: 6,
    color: T.text,
    fontFamily: F,
    fontSize: FS.sm,
    outline: 'none',
    boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.1)',
    transition: 'border-color 0.2s',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label
        style={{
          fontFamily: F,
          fontSize: FS.xs,
          color: T.sec,
          fontWeight: 600,
          display: 'block',
        }}
      >
        {field.label}
      </label>

      {field.type === 'select' ? (
        <select
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
          style={inputStyle}
        >
          {field.options?.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      ) : field.type === 'boolean' ? (
        <button
          onClick={() => onChange(!value)}
          style={{
            ...inputStyle,
            textAlign: 'left',
            color: value ? T.cyan : T.dim,
            cursor: 'pointer',
          }}
        >
          {value ? 'ON' : 'OFF'}
        </button>
      ) : field.type === 'text_area' ? (
        <textarea
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
          style={{ ...inputStyle, minHeight: 50, resize: 'vertical' }}
        />
      ) : field.type === 'integer' ? (
        <input
          type="number"
          value={value === '' ? '' : Number(value)}
          onChange={(e) => onChange(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
          min={field.min}
          max={field.max}
          step={1}
          style={inputStyle}
        />
      ) : field.type === 'float' ? (
        <input
          type="number"
          value={value === '' ? '' : Number(value)}
          onChange={(e) => onChange(e.target.value === '' ? '' : parseFloat(e.target.value))}
          min={field.min}
          max={field.max}
          step={0.01}
          style={inputStyle}
        />
      ) : (
        <input
          type="text"
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
          style={inputStyle}
        />
      )}

      {/* File format compatibility warning */}
      {field.type === 'file_path' && expectedOutputType && typeof value === 'string' && value.length > 2 && (() => {
        const warning = getFileFormatWarning(value, expectedOutputType)
        if (!warning) return null
        return (
          <div style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 6,
            padding: '6px 8px',
            background: `${T.amber}12`,
            border: `1px solid ${T.amber}30`,
            borderRadius: 4,
          }}>
            <AlertTriangle size={11} color={T.amber} style={{ marginTop: 1, flexShrink: 0 }} />
            <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.amber, lineHeight: 1.4 }}>
              {warning}
            </span>
          </div>
        )
      })()}

      {field.description && (
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, lineHeight: 1.4 }}>
          {field.description}
        </span>
      )}
    </div>
  )
}

/* ── Preset Selector ── */
function PresetSelector({ blockType, nodeId, currentConfig }: { blockType: string; nodeId: string; currentConfig: Record<string, any> }) {
  const allPresets = usePresetStore((s) => s.presets)
  const presets = useMemo(() => allPresets.filter((p) => p.blockType === blockType), [allPresets, blockType])
  const savePreset = usePresetStore((s) => s.savePreset)
  const deletePreset = usePresetStore((s) => s.deletePreset)
  const updateNodeConfig = usePipelineStore((s) => s.updateNodeConfig)
  const [showSaveForm, setShowSaveForm] = useState(false)
  const [presetName, setPresetName] = useState('')
  const [presetDesc, setPresetDesc] = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)

  const handleLoadPreset = (preset: { config: Record<string, any>; name: string }) => {
    updateNodeConfig(nodeId, preset.config)
    setDropdownOpen(false)
    toast.success(`Loaded preset "${preset.name}"`)
  }

  const handleSave = () => {
    if (!presetName.trim()) {
      toast.error('Preset name required')
      return
    }
    savePreset(blockType, presetName.trim(), presetDesc.trim(), currentConfig)
    toast.success(`Preset "${presetName}" saved`)
    setPresetName('')
    setPresetDesc('')
    setShowSaveForm(false)
  }

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '6px 8px',
    background: T.surface3,
    border: `1px solid ${T.border}`,
    borderRadius: 4,
    color: T.text,
    fontFamily: F,
    fontSize: FS.xs,
    outline: 'none',
  }

  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        {/* Preset dropdown */}
        <div style={{ flex: 1, position: 'relative' }}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '5px 8px',
              background: T.surface3,
              border: `1px solid ${T.border}`,
              borderRadius: 4,
              color: presets.length > 0 ? T.sec : T.dim,
              fontFamily: F,
              fontSize: FS.xs,
              cursor: 'pointer',
            }}
          >
            <span>{presets.length > 0 ? `${presets.length} preset${presets.length > 1 ? 's' : ''} available` : 'No presets'}</span>
            <ChevronDown size={10} />
          </button>
          {dropdownOpen && presets.length > 0 && (
            <div style={{
              position: 'absolute',
              top: '100%',
              left: 0,
              right: 0,
              zIndex: 100,
              marginTop: 2,
              background: T.surface2,
              border: `1px solid ${T.borderHi}`,
              borderRadius: 4,
              maxHeight: 200,
              overflow: 'auto',
              boxShadow: `0 8px 24px ${T.shadow}`,
            }}>
              {presets.map((p) => (
                <div
                  key={p.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '6px 8px',
                    cursor: 'pointer',
                    borderBottom: `1px solid ${T.border}`,
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = T.surface3 }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                >
                  <div onClick={() => handleLoadPreset(p)} style={{ flex: 1 }}>
                    <div style={{ fontFamily: F, fontSize: FS.xs, color: T.text, fontWeight: 600 }}>{p.name}</div>
                    {p.description && <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>{p.description}</div>}
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); deletePreset(p.id); toast.success('Deleted') }}
                    style={{ background: 'none', border: 'none', color: T.dim, cursor: 'pointer', padding: 2 }}
                  >
                    <Trash2 size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
        {/* Save preset button */}
        <button
          onClick={() => setShowSaveForm(!showSaveForm)}
          title="Save current config as preset"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            padding: '5px 8px',
            background: `${T.cyan}14`,
            border: `1px solid ${T.cyan}33`,
            borderRadius: 4,
            color: T.cyan,
            fontFamily: F,
            fontSize: FS.xxs,
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          <Save size={10} />
          SAVE
        </button>
      </div>

      {/* Save form */}
      {showSaveForm && (
        <div style={{ marginTop: 8, padding: 10, background: T.surface2, border: `1px solid ${T.border}`, borderRadius: 6 }}>
          <input
            value={presetName}
            onChange={(e) => setPresetName(e.target.value)}
            placeholder="Preset name"
            style={{ ...inputStyle, marginBottom: 6 }}
            autoFocus
          />
          <input
            value={presetDesc}
            onChange={(e) => setPresetDesc(e.target.value)}
            placeholder="Description (optional)"
            style={{ ...inputStyle, marginBottom: 8 }}
          />
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              onClick={handleSave}
              style={{
                flex: 1,
                padding: '5px 8px',
                background: T.cyan,
                border: 'none',
                borderRadius: 4,
                color: '#000',
                fontFamily: F,
                fontSize: FS.xxs,
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              SAVE PRESET
            </button>
            <button
              onClick={() => setShowSaveForm(false)}
              style={{
                padding: '5px 8px',
                background: 'none',
                border: `1px solid ${T.border}`,
                borderRadius: 4,
                color: T.dim,
                fontFamily: F,
                fontSize: FS.xxs,
                cursor: 'pointer',
              }}
            >
              CANCEL
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
