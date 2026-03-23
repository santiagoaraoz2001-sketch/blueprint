import { T, F, FS } from '@/lib/design-tokens'
import { usePipelineStore, type BlockNodeData, INHERITABLE_KEYS, CONFIG_PROPAGATION_HANDLES, INHERITANCE_DENY_LIST } from '@/stores/pipelineStore'
import { getBlockDefinition, getFileFormatWarning, type ConfigField, type ConnectorType } from '@/lib/block-registry'
import { usePresetStore } from '@/stores/presetStore'
import { motion, AnimatePresence } from 'framer-motion'
import { getIcon } from '@/lib/icon-utils'
import { Trash2, X, Save, ChevronDown, ChevronRight, AlertTriangle, GitBranch, FolderOpen, Search, Copy, ClipboardPaste, RotateCcw, Info, Zap, ArrowRight, Plus } from 'lucide-react'
import type { Node } from '@xyflow/react'
import { useEffect, useMemo, useState, useCallback } from 'react'
import { api } from '@/api/client'
import RecommendedBlocks, { computeRecommendations } from './RecommendedBlocks'
import { useIsSimpleMode } from '@/hooks/useIsSimpleMode'
import InheritedFieldBadge from './InheritedFieldBadge'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import { useWorkspaceStore } from '@/stores/workspaceStore'
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
  const addNodeAndConnect = usePipelineStore((s) => s.addNodeAndConnect)
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

  // Build set of this block's config field names for dynamic edge inheritance
  const targetFieldNames = useMemo(() => {
    return new Set(def?.configFields.map(f => f.name) || [])
  }, [def])

  const inheritedConfig = useMemo(() => {
    const inherited: Record<string, { value: any; sourceName: string; sourceId: string }> = {}

    // 1. Edge-based inheritance (model/llm connections) — dynamic schema intersection
    for (const edge of incomingEdges) {
      if (!CONFIG_PROPAGATION_HANDLES.has(edge.targetHandle || '')) {
        continue
      }

      const sourceNode = nodes.find(n => n.id === edge.source)
      if (!sourceNode) continue

      const sourceConfig = sourceNode.data.config || {}
      const sourceName = sourceNode.data.label || sourceNode.data.type

      // Dynamic: inherit any key that exists in BOTH source config and target schema,
      // unless it's on the deny list. Falls back to INHERITABLE_KEYS for robustness.
      const keysToCheck = new Set(INHERITABLE_KEYS as string[])
      for (const key of Object.keys(sourceConfig)) {
        if (targetFieldNames.has(key) && !INHERITANCE_DENY_LIST.has(key)) {
          keysToCheck.add(key)
        }
      }

      for (const key of keysToCheck) {
        if (inherited[key]) continue // first edge wins
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
    // Include block-declared propagation keys for this node
    const blockKeys = (propagationKeys as any).by_block?.[node.id]
    if (Array.isArray(blockKeys)) {
      blockKeys.forEach((k: string) => keys.add(k))
    }
    return keys
  }, [propagationKeys, node.id])

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

  // Delete confirmation
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  // Config search
  const [searchQuery, setSearchQuery] = useState('')
  const showSearch = (displayFields?.length || 0) >= 6

  // Filter fields by search, sort mandatory first
  const filteredFields = useMemo(() => {
    if (!displayFields) return []
    let fields = displayFields
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      fields = fields.filter(f =>
        f.name.toLowerCase().includes(q) ||
        f.label.toLowerCase().includes(q) ||
        (f.description || '').toLowerCase().includes(q)
      )
    }
    // Sort: mandatory fields first, then optional
    return [...fields].sort((a, b) => {
      if (a.mandatory && !b.mandatory) return -1
      if (!a.mandatory && b.mandatory) return 1
      return 0
    })
  }, [displayFields, searchQuery])

  // Mandatory field completion tracking
  const mandatoryStats = useMemo(() => {
    if (!displayFields) return { total: 0, filled: 0 }
    const mandatory = displayFields.filter(f => f.mandatory)
    const filled = mandatory.filter(f => {
      const val = node.data.config[f.name]
      const inherited = inheritedConfig[f.name]
      return (val !== undefined && val !== null && val !== '' && String(val) !== String(f.default ?? '')) || !!inherited
    })
    return { total: mandatory.length, filled: filled.length }
  }, [displayFields, node.data.config, inheritedConfig])

  // Group fields by section
  const groupedFields = useMemo(() => {
    const groups: { section: string; fields: typeof filteredFields }[] = []
    const sectionMap = new Map<string, typeof filteredFields>()

    for (const field of filteredFields) {
      const section = field.section || ''
      if (!sectionMap.has(section)) {
        sectionMap.set(section, [])
      }
      sectionMap.get(section)!.push(field)
    }

    // Default/no-section group first, then named sections
    const defaultFields = sectionMap.get('')
    if (defaultFields?.length) {
      groups.push({ section: '', fields: defaultFields })
    }
    for (const [section, fields] of sectionMap) {
      if (section !== '') {
        groups.push({ section, fields })
      }
    }
    return groups
  }, [filteredFields])

  // Copy/paste config
  const handleCopyConfig = useCallback(() => {
    const config = { ...node.data.config }
    delete config._inherited
    navigator.clipboard.writeText(JSON.stringify(config, null, 2))
    toast.success('Config copied to clipboard')
  }, [node.data.config])

  const handlePasteConfig = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText()
      const parsed = JSON.parse(text)
      if (typeof parsed !== 'object' || parsed === null) {
        toast.error('Clipboard does not contain a valid config object')
        return
      }
      // Only paste keys that exist in target block's schema
      const validKeys = new Set(def?.configFields.map(f => f.name) || [])
      const filtered: Record<string, any> = {}
      let count = 0
      for (const [key, value] of Object.entries(parsed)) {
        if (validKeys.has(key)) {
          filtered[key] = value
          count++
        }
      }
      if (count === 0) {
        toast.error('No matching config fields found')
        return
      }
      updateNodeConfig(node.id, filtered)
      toast.success(`Pasted ${count} config field${count > 1 ? 's' : ''}`)
    } catch {
      toast.error('Failed to paste — invalid JSON in clipboard')
    }
  }, [def, node.id, updateNodeConfig])

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
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginBottom: 12,
          }}
        >
          <span
            style={{
              fontFamily: F,
              fontSize: FS.xs,
              color: T.dim,
              letterSpacing: '0.16em',
              fontWeight: 900,
              textTransform: 'uppercase',
            }}
          >
            CONFIGURATION
          </span>
          {mandatoryStats.total > 0 && (
            <span style={{
              fontFamily: F,
              fontSize: FS.xxs,
              color: mandatoryStats.filled === mandatoryStats.total ? T.green : T.amber,
              fontWeight: 600,
              whiteSpace: 'nowrap',
            }}>
              {mandatoryStats.filled}/{mandatoryStats.total} required
            </span>
          )}
          <div style={{ flex: 1, height: 1, background: T.border }} />
          {/* Copy/Paste buttons */}
          <button
            onClick={handleCopyConfig}
            title="Copy config to clipboard"
            style={{
              background: 'none',
              border: 'none',
              color: T.dim,
              cursor: 'pointer',
              padding: 2,
              display: 'flex',
              transition: 'color 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.color = T.text}
            onMouseLeave={e => e.currentTarget.style.color = T.dim}
          >
            <Copy size={11} />
          </button>
          <button
            onClick={handlePasteConfig}
            title="Paste config from clipboard"
            style={{
              background: 'none',
              border: 'none',
              color: T.dim,
              cursor: 'pointer',
              padding: 2,
              display: 'flex',
              transition: 'color 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.color = T.text}
            onMouseLeave={e => e.currentTarget.style.color = T.dim}
          >
            <ClipboardPaste size={11} />
          </button>
        </div>

        {/* Search */}
        {showSearch && (
          <div style={{ position: 'relative', marginBottom: 12 }}>
            <Search size={11} color={T.dim} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' }} />
            <input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search fields..."
              style={{
                width: '100%',
                padding: '6px 10px 6px 28px',
                background: T.surface3,
                border: `1px solid ${T.border}`,
                borderRadius: 6,
                color: T.text,
                fontFamily: F,
                fontSize: FS.xs,
                outline: 'none',
                transition: 'border-color 0.2s',
              }}
              onFocus={e => e.currentTarget.style.borderColor = T.blue}
              onBlur={e => e.currentTarget.style.borderColor = T.border}
            />
          </div>
        )}

        {/* Preset selector */}
        {def && <PresetSelector blockType={def.type} nodeId={node.id} currentConfig={node.data.config} />}

        {/* Grouped config fields */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {groupedFields.map(({ section, fields }) => (
            <ConfigSection
              key={section || '__default'}
              title={section}
              fieldCount={fields.length}
              forceExpanded={!!searchQuery.trim()}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {fields.map((field) => {
                  const fieldInfo = getFieldState(field.name, node.data.config[field.name], field.default)
                  const inherited = inheritedConfig[field.name]
                  const isPropagatable = allPropagationKeys.has(field.name) || INHERITABLE_KEYS.includes(field.name) || field.propagate
                  return (
                    <ConfigFieldInput
                      key={field.name}
                      field={field}
                      value={node.data.config[field.name] ?? field.default ?? ''}
                      onChange={(v) => handleConfigChange(field.name, v)}
                      onRevert={inherited ? () => handleConfigChange(field.name, undefined) : undefined}
                      onOverride={inherited ? () => {
                        handleConfigChange(field.name, inherited.value)
                      } : undefined}
                      onResetToDefault={
                        fieldInfo.state === 'local' && field.default !== undefined
                          ? () => handleConfigChange(field.name, field.default)
                          : undefined
                      }
                      expectedOutputType={def?.outputs[0]?.dataType as ConnectorType | undefined}
                      fieldInfo={fieldInfo}
                      inherited={inherited}
                      hideInheritance={isSimple}
                      onShowInheritance={isPropagatable ? () => {
                        const originId = inherited ? inherited.sourceId : node.id
                        activateInheritanceOverlay(field.name, originId)
                      } : undefined}
                    />
                  )
                })}
              </div>
            </ConfigSection>
          ))}
        </div>

        {/* Next Steps — recommend blocks to add & auto-wire */}
        <NextStepsSection nodeId={node.id} nodes={nodes} edges={edges} addNodeAndConnect={addNodeAndConnect} />

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
          onClick={() => setShowDeleteConfirm(true)}
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

      <ConfirmDialog
        open={showDeleteConfirm}
        title="Delete Block"
        message={`Remove "${node.data.label}" from the pipeline? This will also remove its connections.`}
        confirmLabel="Delete"
        confirmColor={T.red}
        onConfirm={() => { setShowDeleteConfirm(false); removeNode(node.id) }}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </motion.div>
  )
}

/* ── Collapsible Config Section ── */
function ConfigSection({ title, fieldCount, forceExpanded, children }: {
  title: string
  fieldCount: number
  forceExpanded?: boolean
  children: React.ReactNode
}) {
  // "advanced" sections start collapsed, others start expanded
  const [collapsed, setCollapsed] = useState(title.toLowerCase() === 'advanced')

  // No header for the default (empty title) section
  if (!title) {
    return <div style={{ marginBottom: 8 }}>{children}</div>
  }

  const isExpanded = forceExpanded || !collapsed

  return (
    <div style={{ marginTop: 8 }}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          width: '100%',
          padding: '6px 0',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          color: T.dim,
          fontFamily: F,
          fontSize: FS.xxs,
          fontWeight: 700,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          textAlign: 'left',
        }}
      >
        {isExpanded
          ? <ChevronDown size={10} style={{ transition: 'transform 0.2s' }} />
          : <ChevronRight size={10} style={{ transition: 'transform 0.2s' }} />
        }
        {title}
        <span style={{ opacity: 0.5, fontWeight: 400 }}>({fieldCount})</span>
        <div style={{ flex: 1, height: 1, background: T.border, marginLeft: 4 }} />
      </button>
      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{ paddingTop: 8 }}>{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

type ConfigValue = string | number | boolean

function ConfigFieldInput({
  field,
  value,
  onChange,
  onRevert,
  onOverride,
  onResetToDefault,
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
  onResetToDefault?: () => void
  expectedOutputType?: ConnectorType
  fieldInfo: FieldInfo
  inherited?: { value: any; sourceName: string; sourceId: string }
  hideInheritance?: boolean
  onShowInheritance?: () => void
}) {
  const [hovered, setHovered] = useState(false)
  const [tooltipVisible, setTooltipVisible] = useState(false)

  // In simple mode, suppress inheritance visuals
  const fieldInfo: FieldInfo = hideInheritance
    ? { state: 'local', effectiveValue: rawFieldInfo.effectiveValue }
    : rawFieldInfo
  const inherited = hideInheritance ? undefined : rawInherited
  const isInherited = fieldInfo.state === 'inherited'
  const isOverriddenInherited = fieldInfo.state === 'local' && !!inherited

  // Inline validation
  const validationError = useMemo(() => {
    if (isInherited) return null
    const isEmpty = value === '' || value === undefined || value === null
    if (field.mandatory && isEmpty) return 'Required'
    if (!isEmpty && (field.type === 'integer' || field.type === 'float') && typeof value === 'number') {
      if (field.min !== undefined && value < field.min) return `Min: ${field.min}`
      if (field.max !== undefined && value > field.max) return `Max: ${field.max}`
    }
    return null
  }, [field, value, isInherited])

  const hasError = !!validationError

  // Mandatory empty field highlight
  const isMandatoryEmpty = field.mandatory && !isInherited && (value === '' || value === undefined || value === null)

  // Left border accent: red for error, amber for mandatory empty, blue for inherited, orange for overridden inherited
  const leftBorderColor = hasError ? T.red : isMandatoryEmpty ? T.amber : isInherited ? T.blue : isOverriddenInherited ? T.orange : 'transparent'

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 12px',
    background: T.surface3,
    border: `1px solid ${hasError ? `${T.red}60` : isInherited ? `${T.blue}40` : isOverriddenInherited ? `${T.orange}40` : T.borderHi}`,
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
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        borderLeft: `2px solid ${leftBorderColor}`,
        paddingLeft: leftBorderColor !== 'transparent' ? 10 : 0,
        transition: 'border-color 0.2s, padding-left 0.2s',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Label row */}
      <label
        onClick={onShowInheritance}
        title={onShowInheritance ? `Show inheritance flow for "${field.name}"` : undefined}
        style={{
          fontFamily: F,
          fontSize: FS.xs,
          color: hasError ? T.red
               : isInherited ? T.blue
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
          <>
            <span style={{ color: T.red, fontWeight: 900, marginLeft: 2 }}>*</span>
            {isMandatoryEmpty && (
              <span style={{
                fontFamily: F, fontSize: '7px', color: T.amber, fontWeight: 700,
                padding: '1px 4px', background: `${T.amber}12`, border: `1px solid ${T.amber}25`,
                borderRadius: 3, letterSpacing: '0.06em',
              }}>
                REQUIRED
              </span>
            )}
          </>
        )}
        {/* Description tooltip icon */}
        {field.description && (
          <span
            style={{ position: 'relative', display: 'inline-flex' }}
            onMouseEnter={() => setTooltipVisible(true)}
            onMouseLeave={() => setTooltipVisible(false)}
          >
            <Info size={10} color={T.dim} style={{ cursor: 'help', opacity: 0.6 }} />
            {tooltipVisible && (
              <div style={{
                position: 'absolute',
                bottom: '100%',
                left: '50%',
                transform: 'translateX(-50%)',
                marginBottom: 6,
                padding: '6px 10px',
                background: T.surface2,
                border: `1px solid ${T.borderHi}`,
                borderRadius: 6,
                boxShadow: `0 4px 16px ${T.shadow}`,
                fontFamily: F,
                fontSize: FS.xxs,
                color: T.sec,
                lineHeight: 1.4,
                fontWeight: 400,
                fontStyle: 'normal',
                whiteSpace: 'normal',
                width: 220,
                maxWidth: 260,
                zIndex: 50,
                pointerEvents: 'none',
              }}>
                {field.description}
              </div>
            )}
          </span>
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
        {/* Reset to default button — shown on hover when locally changed */}
        {hovered && onResetToDefault && !inherited && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onResetToDefault()
            }}
            title="Reset to default"
            style={{
              background: 'none',
              border: 'none',
              color: T.dim,
              cursor: 'pointer',
              padding: 0,
              display: 'flex',
              alignItems: 'center',
              marginLeft: 'auto',
              transition: 'color 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.color = T.text}
            onMouseLeave={e => e.currentTarget.style.color = T.dim}
          >
            <RotateCcw size={9} />
          </button>
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            onClick={() => onChange(!value)}
            style={{
              position: 'relative',
              width: 36,
              height: 20,
              borderRadius: 10,
              border: 'none',
              background: (isInherited ? fieldInfo.effectiveValue : value)
                ? `${T.cyan}40`
                : T.surface4,
              cursor: 'pointer',
              transition: 'background 0.2s',
              flexShrink: 0,
              padding: 0,
            }}
          >
            <div style={{
              position: 'absolute',
              top: 2,
              left: (isInherited ? fieldInfo.effectiveValue : value) ? 18 : 2,
              width: 16,
              height: 16,
              borderRadius: '50%',
              background: (isInherited ? fieldInfo.effectiveValue : value) ? T.cyan : T.dim,
              transition: 'left 0.2s, background 0.2s',
              boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
            }} />
          </button>
          <span style={{
            fontFamily: F,
            fontSize: FS.xs,
            color: isInherited ? T.blue : ((isInherited ? fieldInfo.effectiveValue : value) ? T.cyan : T.dim),
            fontWeight: 600,
          }}>
            {(isInherited ? fieldInfo.effectiveValue : value) ? 'ON' : 'OFF'}
          </span>
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
        <div>
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
          {field.min !== undefined && field.max !== undefined && (
            <NumberSlider
              value={isInherited ? fieldInfo.effectiveValue : value}
              min={field.min}
              max={field.max}
              step={1}
              onChange={(v) => onChange(Math.round(v))}
            />
          )}
        </div>
      ) : field.type === 'float' ? (
        <div>
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
          {field.min !== undefined && field.max !== undefined && (
            <NumberSlider
              value={isInherited ? fieldInfo.effectiveValue : value}
              min={field.min}
              max={field.max}
              step={0.01}
              onChange={(v) => onChange(parseFloat(v.toFixed(2)))}
            />
          )}
        </div>
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

      {/* Validation error */}
      {validationError && (
        <div style={{
          fontFamily: F,
          fontSize: FS.xxs,
          color: T.red,
          display: 'flex',
          alignItems: 'center',
          gap: 4,
        }}>
          <AlertTriangle size={9} />
          {validationError}
        </div>
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
  const { paths, autoFillEnabled } = useWorkspaceStore()

  // Determine if workspace auto-fill applies to this field
  const workspacePath = useMemo(() => {
    if (!autoFillEnabled || Object.keys(paths).length === 0) return null
    // Check if this field has a workspace path based on common field names
    const fieldName = field.name.toLowerCase()
    if (fieldName.includes('output') || fieldName === 'save_path' || fieldName === 'export_path') {
      return paths.outputs_exports || paths.outputs_inference || null
    }
    if (fieldName === 'cache_dir' || fieldName === 'model_path' || fieldName === 'local_path') {
      return paths.models_base || null
    }
    if (fieldName === 'file_path' || fieldName === 'data_path' || fieldName === 'input_path') {
      return paths.datasets_raw || null
    }
    return null
  }, [autoFillEnabled, paths, field.name])

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

  const isDefaultValue = !value || value === './output' || value === field.default

  return (
    <div>
      <div style={{ display: 'flex', gap: 4, alignItems: 'stretch' }}>
        <input
          type="text"
          value={value}
          placeholder={workspacePath && isDefaultValue ? workspacePath : placeholder}
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
            background: `${T.text}08`,
            border: `1px solid ${T.text}15`,
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
            e.currentTarget.style.background = `${T.text}08`
            e.currentTarget.style.borderColor = `${T.text}15`
          }}
        >
          <FolderOpen size={13} />
        </button>
      </div>
      {workspacePath && isDefaultValue && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 4, marginTop: 4,
          fontFamily: F, fontSize: '8px', color: T.green, lineHeight: 1.3,
        }}>
          <FolderOpen size={8} />
          <span>Workspace auto-fill: {workspacePath.split('/').slice(-2).join('/')}</span>
        </div>
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

/* ── Number Slider for bounded fields ── */
function NumberSlider({ value, min, max, step, onChange }: {
  value: any
  min: number
  max: number
  step: number
  onChange: (v: number) => void
}) {
  const numValue = typeof value === 'number' ? value : (typeof value === 'string' && value !== '' ? parseFloat(value) : min)
  const percent = max > min ? ((numValue - min) / (max - min)) * 100 : 0

  return (
    <div style={{ marginTop: 6 }}>
      <div style={{ position: 'relative', height: 20, display: 'flex', alignItems: 'center' }}>
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={numValue}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          style={{
            width: '100%',
            height: 4,
            appearance: 'none',
            WebkitAppearance: 'none',
            background: `linear-gradient(to right, ${T.cyan} 0%, ${T.cyan} ${percent}%, ${T.surface4} ${percent}%, ${T.surface4} 100%)`,
            borderRadius: 2,
            outline: 'none',
            cursor: 'pointer',
          }}
        />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span style={{ fontFamily: F, fontSize: '7px', color: T.dim }}>{min}</span>
        <span style={{ fontFamily: F, fontSize: '7px', color: T.dim }}>{max}</span>
      </div>
    </div>
  )
}

/* ── Next Steps Section — shows recommended blocks scoped to current node ── */
function NextStepsSection({ nodeId, nodes, edges, addNodeAndConnect }: {
  nodeId: string
  nodes: any[]
  edges: any[]
  addNodeAndConnect: (type: string, connectTo: { nodeId: string; portId: string; direction: 'upstream' | 'downstream' }) => void
}) {
  const recs = useMemo(() => {
    if (nodes.length === 0) return []
    const { inputBlocks, outputBlocks } = computeRecommendations(nodes, edges)
    // Filter to only recs that connect to THIS node
    const relevant = [...inputBlocks, ...outputBlocks].filter(
      (r) => r.connectTo?.nodeId === nodeId
    )
    return relevant.slice(0, 3)
  }, [nodes, edges, nodeId])

  if (recs.length === 0) return null

  return (
    <div style={{ marginTop: 24 }}>
      <span
        style={{
          fontFamily: F, fontSize: FS.xs, color: T.dim,
          letterSpacing: '0.16em', fontWeight: 900, textTransform: 'uppercase',
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
        }}
      >
        <Zap size={10} color={T.green} />
        NEXT STEPS
        <div style={{ flex: 1, height: 1, background: T.border }} />
      </span>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {recs.map((rec) => {
          const IconComp = getIcon(rec.block.icon)
          const accent = rec.block.accent || T.cyan
          return (
            <button
              key={rec.block.type}
              onClick={() => {
                if (rec.connectTo) {
                  addNodeAndConnect(rec.block.type, rec.connectTo)
                }
              }}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '8px 10px',
                background: `${T.green}08`,
                border: `1px solid ${T.green}20`,
                borderRadius: 6,
                cursor: 'pointer',
                textAlign: 'left',
                transition: 'all 0.15s',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = `${T.green}15`
                e.currentTarget.style.borderColor = `${T.green}40`
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = `${T.green}08`
                e.currentTarget.style.borderColor = `${T.green}20`
              }}
            >
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 20, height: 20, borderRadius: 4,
                background: `${accent}15`, flexShrink: 0,
              }}>
                <IconComp size={10} color={accent} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontFamily: F, fontSize: FS.xs, color: T.text,
                  fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}>
                  {rec.block.name}
                </div>
                <div style={{ fontFamily: F, fontSize: '7px', color: T.dim, lineHeight: 1.3 }}>
                  {rec.reason}
                </div>
              </div>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 3,
                padding: '3px 8px', borderRadius: 4,
                background: `${T.green}15`, border: `1px solid ${T.green}30`,
                flexShrink: 0,
              }}>
                <Plus size={8} color={T.green} />
                <span style={{ fontFamily: F, fontSize: '7px', color: T.green, fontWeight: 700 }}>
                  ADD
                </span>
                <ArrowRight size={7} color={T.green} />
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
