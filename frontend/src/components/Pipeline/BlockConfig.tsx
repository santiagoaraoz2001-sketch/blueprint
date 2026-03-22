import { T, F, FS } from '@/lib/design-tokens'
import { usePipelineStore, type BlockNodeData, INHERITABLE_KEYS, CONFIG_PROPAGATION_HANDLES } from '@/stores/pipelineStore'
import { getBlockDefinition, getFileFormatWarning, type ConfigField, type ConnectorType } from '@/lib/block-registry'
import { usePresetStore } from '@/stores/presetStore'
import { motion, AnimatePresence } from 'framer-motion'
import { getIcon } from '@/lib/icon-utils'
import { Trash2, X, Save, ChevronDown, AlertTriangle, GitBranch, FolderOpen } from 'lucide-react'
import type { Node } from '@xyflow/react'
import { useEffect, useMemo, useState, useCallback } from 'react'
import { api } from '@/api/client'
import RecommendedBlocks from './RecommendedBlocks'
import { useIsSimpleMode } from '@/hooks/useIsSimpleMode'
import InheritedFieldBadge from './InheritedFieldBadge'
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

type FieldState = 'local' | 'inherited' | 'default'
interface FieldInfo {
  state: FieldState
  effectiveValue: any
  source?: string
  sourceId?: string
}

function BlockConfigInner({ node }: { node: Node<BlockNodeData> }) {
  const updateNodeConfig = usePipelineStore((s) => s.updateNodeConfig)
  const removeNode = usePipelineStore((s) => s.removeNode)
  const selectNode = usePipelineStore((s) => s.selectNode)
  const edges = usePipelineStore((s) => s.edges)
  const nodes = usePipelineStore((s) => s.nodes)
  const activateInheritanceOverlay = usePipelineStore((s) => s.activateInheritanceOverlay)
  const resolvedConfigs = usePipelineStore((s) => s.resolvedConfigs)
  const propagationKeys = usePipelineStore((s) => s.propagationKeys)
  const def = getBlockDefinition(node.data.type)
  const IconComponent = getIcon(node.data.icon)
  const isSimple = useIsSimpleMode()

  // Resolve-config API inheritance data for this node
  const apiInherited = useMemo(() => {
    return resolvedConfigs[node.id]?._inherited || {}
  }, [resolvedConfigs, node.id])

  // Compute inherited config — merge edge-based (existing) + resolve-config API data
  const incomingEdges = useMemo(() => edges.filter(e => e.target === node.id), [edges, node.id])

  const inheritedConfig = useMemo(() => {
    const inherited: Record<string, { value: any; sourceName: string; sourceId: string }> = {}

    // 1. Edge-based inheritance (model/llm connections)
    for (const edge of incomingEdges) {
      if (!CONFIG_PROPAGATION_HANDLES.has(edge.targetHandle || '')) {
        continue
      }

      const sourceNode = nodes.find(n => n.id === edge.source)
      if (!sourceNode) continue

      const sourceConfig = sourceNode.data.config || {}
      const sourceName = sourceNode.data.label || sourceNode.data.type

      for (const key of INHERITABLE_KEYS) {
        const value = sourceConfig[key]
        if (value !== undefined && value !== null && value !== '') {
          inherited[key] = { value, sourceName, sourceId: edge.source }
        }
      }
    }

    // 2. Resolve-config API inheritance (DAG-based propagation: seed, text_column, etc.)
    for (const [key, entry] of Object.entries(apiInherited)) {
      if (inherited[key]) continue // edge-based takes precedence
      const sourceNode = nodes.find(n => n.id === entry.from_node)
      const sourceName = sourceNode?.data.label || sourceNode?.data.type || entry.from_node
      inherited[key] = { value: entry.value, sourceName, sourceId: entry.from_node }
    }

    return inherited
  }, [incomingEdges, nodes, apiInherited])

  // Determine field state
  function getFieldState(fieldName: string, currentValue: any, defaultValue: any): FieldInfo {
    const locallySet = currentValue !== undefined && currentValue !== null && currentValue !== ''
      && String(currentValue) !== String(defaultValue ?? '')

    if (locallySet) {
      return { state: 'local', effectiveValue: currentValue }
    }

    const inherited = inheritedConfig[fieldName]
    if (inherited) {
      return {
        state: 'inherited',
        effectiveValue: inherited.value,
        source: inherited.sourceName,
        sourceId: inherited.sourceId,
      }
    }

    return { state: 'default', effectiveValue: defaultValue }
  }

  // Collect all propagation key names for preview toast
  const allPropagationKeys = useMemo(() => {
    if (!propagationKeys) return new Set<string>()
    const keys = new Set(propagationKeys.global)
    for (const catKeys of Object.values(propagationKeys.by_category)) {
      catKeys.forEach(k => keys.add(k))
    }
    return keys
  }, [propagationKeys])

  // Find downstream blocks that would be affected by a propagatable field change
  const getDownstreamBlocks = useCallback((fromNodeId: string): string[] => {
    const visited = new Set<string>()
    const queue = [fromNodeId]
    while (queue.length > 0) {
      const current = queue.shift()!
      for (const edge of edges) {
        if (edge.source === current && !visited.has(edge.target)) {
          visited.add(edge.target)
          queue.push(edge.target)
        }
      }
    }
    return Array.from(visited)
  }, [edges])

  const handleConfigChange = (name: string, value: string | number | boolean | undefined | null) => {
    updateNodeConfig(node.id, { [name]: value })

    // Propagation preview toast for propagatable keys
    if (value !== undefined && value !== null && allPropagationKeys.has(name)) {
      const downstreamIds = getDownstreamBlocks(node.id)
      if (downstreamIds.length > 0) {
        const downstreamNames = downstreamIds
          .map(id => nodes.find(n => n.id === id))
          .filter((n): n is Node<BlockNodeData> => !!n)
          .map(n => n.data.label)
          .slice(0, 4)
        const extra = downstreamIds.length > 4 ? `, +${downstreamIds.length - 4} more` : ''
        toast(`${name} will propagate to ${downstreamIds.length} downstream block${downstreamIds.length > 1 ? 's' : ''}: ${downstreamNames.join(', ')}${extra}`, {
          duration: 3000,
          style: {
            fontFamily: F,
            fontSize: `${FS.xs}px`,
            background: T.surface3,
            color: T.text,
            border: `1px solid ${T.blue}40`,
          },
        })
      }
    }
  }

  const [frameworkData, setFrameworkData] = useState<any[]>([])

  useEffect(() => {
    if (def?.type === 'model_selector') {
      api.get<any[]>('/system/models')
        .then(data => {
          if (Array.isArray(data)) {
            setFrameworkData(data)
          }
        })
        .catch(err => console.error('Failed to fetch models', err))
    }
  }, [def?.type])

  // Filter config fields by depends_on and enrich model_id with auto-detected options
  const displayFields = def?.configFields
    .filter(f => {
      if (!f.depends_on) return true
      return node.data.config[f.depends_on.field] === f.depends_on.value
    })
    .map(f => {
      // Auto-populate model_id field with discovered models for the selected source
      if (def.type === 'model_selector' && f.name === 'model_id') {
        const source = (node.data.config.source as string) || 'huggingface'
        const sourceToFramework: Record<string, string> = { ollama: 'ollama', mlx: 'mlx', huggingface: 'pytorch', local_path: '' }
        const fwId = sourceToFramework[source] || ''
        const fwEntry = frameworkData.find((d: any) => d.id === fwId)
        const models: string[] = fwEntry?.models || []
        if (models.length > 0) {
          return { ...f, type: 'select' as const, options: models } as ConfigField
        }
      }
      return f
    })

  // Compute inheritance stats for summary
  const inheritedCount = Object.keys(inheritedConfig).length
  const overriddenCount = displayFields?.filter(f => {
    const info = getFieldState(f.name, node.data.config[f.name], f.default)
    return info.state === 'local' && inheritedConfig[f.name]
  }).length || 0

  // Config Inheritance summary section state
  const [showInheritanceSummary, setShowInheritanceSummary] = useState(false)

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

      {/* Deprecation warning */}
      {def?.deprecated && (
        <div style={{
          margin: '0 16px',
          padding: '8px 12px',
          background: 'rgba(251,191,36,0.08)',
          border: '1px solid rgba(251,191,36,0.3)',
          borderRadius: 8,
          display: 'flex',
          gap: 8,
          alignItems: 'flex-start',
        }}>
          <AlertTriangle size={14} color="#FBBF24" style={{ marginTop: 2, flexShrink: 0 }} />
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: '#FBBF24', lineHeight: 1.4 }}>
            <strong>Deprecated.</strong> {def.deprecatedMessage || 'Use LLM Inference block instead.'}
          </span>
        </div>
      )}

      {/* Inheritance summary banner */}
      {!isSimple && inheritedCount > 0 && (
        <button
          onClick={() => setShowInheritanceSummary(!showInheritanceSummary)}
          style={{
            padding: '8px 16px',
            background: `${T.blue}10`,
            borderTop: 'none',
            borderLeft: 'none',
            borderRight: 'none',
            borderBottom: `1px solid ${T.blue}20`,
            fontSize: FS.xs,
            color: T.blue,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontFamily: F,
            cursor: 'pointer',
            width: '100%',
            textAlign: 'left',
          }}
        >
          <GitBranch size={10} />
          {inheritedCount} inherited
          {overriddenCount > 0 && (
            <span style={{ color: T.orange }}>
              ({overriddenCount} overridden)
            </span>
          )}
          <ChevronDown size={8} style={{
            marginLeft: 'auto',
            transform: showInheritanceSummary ? 'rotate(180deg)' : 'none',
            transition: 'transform 0.2s',
          }} />
        </button>
      )}

      {/* Config Inheritance Summary Panel */}
      <AnimatePresence>
        {showInheritanceSummary && inheritedCount > 0 && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: 'hidden', borderBottom: `1px solid ${T.border}` }}
          >
            <div style={{ padding: '10px 16px', background: `${T.blue}06` }}>
              <div style={{
                fontFamily: F,
                fontSize: FS.xxs,
                color: T.dim,
                letterSpacing: '0.12em',
                fontWeight: 800,
                textTransform: 'uppercase',
                marginBottom: 8,
              }}>
                CONFIG INHERITANCE
              </div>
              {Object.entries(inheritedConfig).map(([key, info]) => {
                const fieldState = getFieldState(key, node.data.config[key], undefined)
                const isOverridden = fieldState.state === 'local'
                return (
                  <div
                    key={key}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '4px 0',
                      borderLeft: `2px solid ${isOverridden ? T.orange : T.blue}`,
                      paddingLeft: 8,
                      marginBottom: 4,
                    }}
                  >
                    <span style={{
                      fontFamily: F,
                      fontSize: FS.xxs,
                      color: T.text,
                      fontWeight: 600,
                      flex: 1,
                    }}>
                      {key}
                    </span>
                    <span style={{
                      fontFamily: F,
                      fontSize: FS.xxs,
                      color: isOverridden ? T.orange : T.blue,
                      opacity: 0.8,
                    }}>
                      {isOverridden ? 'overridden' : `from ${info.sourceName}`}
                    </span>
                  </div>
                )
              })}

              {/* Propagation keys info */}
              {propagationKeys && (
                <div style={{ marginTop: 8, paddingTop: 8, borderTop: `1px solid ${T.border}` }}>
                  <div style={{
                    fontFamily: F,
                    fontSize: FS.xxs,
                    color: T.dim,
                    marginBottom: 4,
                  }}>
                    Propagating keys: {[
                      ...propagationKeys.global,
                      ...Object.values(propagationKeys.by_category).flat()
                    ].join(', ')}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

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
          {displayFields?.map((field) => {
            const fieldInfo = getFieldState(field.name, node.data.config[field.name], field.default)
            const inherited = inheritedConfig[field.name]
            const isPropagatable = INHERITABLE_KEYS.includes(field.name)
            return (
              <ConfigFieldInput
                key={field.name}
                field={field}
                value={node.data.config[field.name] ?? field.default ?? ''}
                onChange={(v) => handleConfigChange(field.name, v)}
                onRevert={inherited ? () => handleConfigChange(field.name, undefined) : undefined}
                onOverride={inherited ? () => {
                  // Set the inherited value as a local override so the field becomes editable
                  handleConfigChange(field.name, inherited.value)
                } : undefined}
                expectedOutputType={def?.outputs[0]?.dataType as ConnectorType | undefined}
                fieldInfo={fieldInfo}
                inherited={inherited}
                hideInheritance={isSimple}
                onShowInheritance={isPropagatable ? () => {
                  // Origin is upstream source if inherited, otherwise this node
                  const originId = inherited ? inherited.sourceId : node.id
                  activateInheritanceOverlay(field.name, originId)
                } : undefined}
              />
            )
          })}
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
  onRevert,
  onOverride,
  expectedOutputType,
  fieldInfo: rawFieldInfo,
  inherited: rawInherited,
  hideInheritance,
  onShowInheritance,
}: {
  field: ConfigField
  value: ConfigValue
  onChange: (v: ConfigValue) => void
  onRevert?: () => void
  onOverride?: () => void
  expectedOutputType?: ConnectorType
  fieldInfo: FieldInfo
  inherited?: { value: any; sourceName: string; sourceId: string }
  hideInheritance?: boolean
  onShowInheritance?: () => void
}) {
  // In simple mode, suppress inheritance visuals
  const fieldInfo: FieldInfo = hideInheritance
    ? { state: 'local', effectiveValue: rawFieldInfo.effectiveValue }
    : rawFieldInfo
  const inherited = hideInheritance ? undefined : rawInherited
  const isInherited = fieldInfo.state === 'inherited'
  const isOverriddenInherited = fieldInfo.state === 'local' && !!inherited

  // Left border accent: blue for inherited, orange for overridden inherited
  const leftBorderColor = isInherited ? T.blue : isOverriddenInherited ? T.orange : 'transparent'

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 12px',
    background: T.surface3,
    border: `1px solid ${isInherited ? `${T.blue}40` : isOverriddenInherited ? `${T.orange}40` : T.borderHi}`,
    borderRadius: 6,
    color: isInherited ? T.dim : fieldInfo.state === 'default' ? T.dim : T.text,
    fontFamily: F,
    fontSize: FS.sm,
    fontStyle: isInherited ? 'italic' : 'normal',
    outline: 'none',
    boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.1)',
    transition: 'border-color 0.2s',
  }

  const inheritedPlaceholder = isInherited
    ? `${fieldInfo.effectiveValue} (from ${fieldInfo.source})`
    : String(field.default ?? '')

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      borderLeft: `2px solid ${leftBorderColor}`,
      paddingLeft: leftBorderColor !== 'transparent' ? 10 : 0,
      transition: 'border-color 0.2s, padding-left 0.2s',
    }}>
      {/* Label with state indicator + InheritedFieldBadge */}
      <label
        onClick={onShowInheritance}
        title={onShowInheritance ? `Show inheritance flow for "${field.name}"` : undefined}
        style={{
          fontFamily: F,
          fontSize: FS.xs,
          color: isInherited ? T.blue
               : fieldInfo.state === 'default' ? T.dim
               : T.sec,
          fontWeight: 600,
          fontStyle: isInherited ? 'italic' : 'normal',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          cursor: onShowInheritance ? 'pointer' : undefined,
        }}
      >
        {field.label}
        {field.mandatory && (
          <span style={{ color: T.red, fontWeight: 900, marginLeft: 2 }}>*</span>
        )}
        {onShowInheritance && (
          <span style={{ fontSize: FS.xxs, color: T.blue, opacity: 0.6 }} title="Click to visualize inheritance">
            &#x25C9;
          </span>
        )}
        {fieldInfo.state === 'default' && (
          <span style={{
            fontSize: FS.xxs,
            color: T.dim,
            fontStyle: 'normal',
            fontWeight: 400,
          }}>
            (default)
          </span>
        )}
        {/* InheritedFieldBadge for inherited or overridden-inherited fields */}
        {inherited && (
          <InheritedFieldBadge
            sourceName={inherited.sourceName}
            isOverridden={isOverriddenInherited}
            onOverride={() => onOverride?.()}
            onResetToInherited={() => onRevert?.()}
          />
        )}
      </label>

      {field.type === 'select' ? (
        <select
          value={isInherited ? String(fieldInfo.effectiveValue) : String(value)}
          onChange={(e) => onChange(e.target.value)}
          style={{
            ...inputStyle,
            color: isInherited ? T.blue : fieldInfo.state === 'default' ? T.dim : T.text,
            fontStyle: isInherited ? 'italic' : 'normal',
          }}
        >
          {isInherited && !field.options?.includes(String(fieldInfo.effectiveValue)) && (
            <option value={String(fieldInfo.effectiveValue)}>
              {fieldInfo.effectiveValue} (from {fieldInfo.source})
            </option>
          )}
          {field.options?.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      ) : field.type === 'boolean' ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            onClick={() => onChange(!value)}
            style={{
              ...inputStyle,
              flex: 1,
              textAlign: 'left',
              color: isInherited ? T.blue : (value ? T.cyan : T.dim),
              cursor: 'pointer',
            }}
          >
            {isInherited ? (fieldInfo.effectiveValue ? 'ON' : 'OFF') : (value ? 'ON' : 'OFF')}
          </button>
        </div>
      ) : field.type === 'text_area' ? (
        <textarea
          value={isInherited ? '' : String(value)}
          placeholder={inheritedPlaceholder}
          onChange={(e) => onChange(e.target.value)}
          style={{
            ...inputStyle,
            minHeight: 50,
            resize: 'vertical',
          }}
        />
      ) : field.type === 'integer' ? (
        <input
          type="number"
          value={isInherited ? '' : (value === '' ? '' : Number(value))}
          placeholder={inheritedPlaceholder}
          onChange={(e) => onChange(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
          min={field.min}
          max={field.max}
          step={1}
          style={inputStyle}
        />
      ) : field.type === 'float' ? (
        <input
          type="number"
          value={isInherited ? '' : (value === '' ? '' : Number(value))}
          placeholder={inheritedPlaceholder}
          onChange={(e) => onChange(e.target.value === '' ? '' : parseFloat(e.target.value))}
          min={field.min}
          max={field.max}
          step={0.01}
          style={inputStyle}
        />
      ) : field.type === 'file_path' ? (
        <FilePathInput
          value={isInherited ? '' : String(value)}
          placeholder={inheritedPlaceholder}
          onChange={onChange}
          inputStyle={inputStyle}
          field={field}
        />
      ) : (
        <input
          type="text"
          value={isInherited ? '' : String(value)}
          placeholder={inheritedPlaceholder}
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

      {field.mandatory && (value === '' || value === undefined || value === null) && (
        <div style={{
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.dim,
          marginTop: 2,
          fontStyle: 'italic',
        }}>
          Required — set a value or connect the input port
        </div>
      )}

      {field.description && (
        <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, lineHeight: 1.4 }}>
          {field.description}
        </span>
      )}
    </div>
  )
}

/* ── File Path Input with Browse Button ── */

/** Infer whether a file_path field expects a directory based on path_mode or field name heuristics */
function inferPathMode(field: ConfigField): 'file' | 'directory' {
  if (field.path_mode) return field.path_mode
  const name = field.name.toLowerCase()
  if (name.includes('dir') || name.includes('directory') || name.includes('folder') || name.includes('output_path')) {
    return 'directory'
  }
  return 'file'
}

/** Build Electron dialog file filters from file_extensions or field context */
function buildFileFilters(field: ConfigField): { name: string; extensions: string[] }[] {
  if (field.file_extensions?.length) {
    return [
      { name: 'Supported files', extensions: field.file_extensions.map((e) => e.replace(/^\./, '')) },
      { name: 'All files', extensions: ['*'] },
    ]
  }
  return []
}

function FilePathInput({
  value,
  placeholder,
  onChange,
  inputStyle,
  field,
}: {
  value: string
  placeholder: string
  onChange: (v: string) => void
  inputStyle: React.CSSProperties
  field: ConfigField
}) {
  const [browsing, setBrowsing] = useState(false)
  const pathMode = inferPathMode(field)

  const handleBrowse = useCallback(async () => {
    if (browsing) return
    setBrowsing(true)

    try {
      let selectedPath: string | null = null

      // Try Electron IPC first, fall back to backend API
      if (window.blueprint?.selectFile) {
        if (pathMode === 'directory') {
          selectedPath = await window.blueprint.selectDirectory({
            title: field.label || 'Select Folder',
            defaultPath: value || undefined,
          })
        } else {
          selectedPath = await window.blueprint.selectFile({
            title: field.label || 'Select File',
            defaultPath: value || undefined,
            filters: buildFileFilters(field),
          })
        }
      } else {
        // Backend fallback for non-Electron environments
        const res = await fetch('/api/system/browse', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mode: pathMode,
            title: field.label || (pathMode === 'directory' ? 'Select Folder' : 'Select File'),
            default_path: value || '',
            file_extensions: field.file_extensions || [],
          }),
        })
        const data = await res.json()
        selectedPath = data.path
      }

      if (selectedPath) {
        onChange(selectedPath)
      }
    } catch (err) {
      console.error('Browse dialog error:', err)
      toast.error('Failed to open file browser')
    } finally {
      setBrowsing(false)
    }
  }, [browsing, pathMode, field, value, onChange])

  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'stretch' }}>
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        style={{ ...inputStyle, flex: 1 }}
      />
      <button
        onClick={handleBrowse}
        disabled={browsing}
        title={pathMode === 'directory' ? 'Browse for folder' : 'Browse for file'}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '0 8px',
          background: `${T.white}08`,
          border: `1px solid ${T.white}15`,
          borderRadius: 4,
          color: browsing ? T.dim : T.cyan,
          cursor: browsing ? 'wait' : 'pointer',
          transition: 'all 0.15s ease',
          flexShrink: 0,
        }}
        onMouseEnter={(e) => {
          if (!browsing) {
            e.currentTarget.style.background = `${T.cyan}18`
            e.currentTarget.style.borderColor = `${T.cyan}40`
          }
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = `${T.white}08`
          e.currentTarget.style.borderColor = `${T.white}15`
        }}
      >
        <FolderOpen size={13} />
      </button>
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
