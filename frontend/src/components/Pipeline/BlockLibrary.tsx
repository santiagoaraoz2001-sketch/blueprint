import { useState, useRef, useCallback, useEffect } from 'react'
import { T, F, FS, CONNECTOR_COLORS, CATEGORY_COLORS } from '@/lib/design-tokens'
import { getBlocksByCategory, getPortColor, type BlockDefinition, getAllBlocks, isPortCompatible, getBlockDefinition } from '@/lib/block-registry'
import { BLOCK_ALIASES, CATEGORY_ALIASES } from '@/lib/search-aliases'
import BlockDetailPanel from './BlockDetailPanel'
import CustomModuleEditor, { loadCustomBlocks, type CustomBlock } from './CustomModuleEditor'
import BlockGeneratorModal from './BlockGeneratorModal'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useIsSimpleMode } from '@/hooks/useIsSimpleMode'
import * as Icons from 'lucide-react'

const { Search, ChevronRight, ChevronDown, Plus, Sparkles, Zap } = Icons

const CATEGORY_ORDER = ['external', 'data', 'model', 'inference', 'training', 'metrics', 'embedding', 'utilities', 'agents', 'interventions', 'endpoints']

const CATEGORY_LABELS: Record<string, string> = {
  external: 'SOURCES',
  data: 'TRANSFORMS',
  model: 'MODEL OPS',
  inference: 'INFERENCE',
  training: 'TRAINING',
  metrics: 'EVALUATION',
  embedding: 'VECTORS',
  utilities: 'FLOW CONTROL',
  agents: 'AGENTS',
  interventions: 'GATES',
  endpoints: 'ENDPOINTS',
}

const SIMPLE_CATEGORIES = new Set(['external', 'data', 'model', 'inference', 'training', 'metrics'])

// Shared badge styles for block status indicators
const BADGE_BASE: React.CSSProperties = {
  fontFamily: F, fontWeight: 700,
  padding: '1px 4px', borderRadius: 3, marginLeft: 4,
  letterSpacing: '0.06em', textTransform: 'uppercase',
  display: 'inline-block', verticalAlign: 'middle',
}

const BADGE_STYLES = {
  deprecated: { ...BADGE_BASE, color: '#F59E0B', background: '#F59E0B15', border: '1px solid #F59E0B30' },
  recommended: { ...BADGE_BASE, color: '#2DD4BF', background: '#2DD4BF15', border: '1px solid #2DD4BF30' },
  beta: { ...BADGE_BASE, color: '#F59E0B', background: '#F59E0B15', border: '1px solid #F59E0B30' },
  experimental: { ...BADGE_BASE, color: '#8B5CF6', background: '#8B5CF615', border: '1px solid #8B5CF630' },
} as const

/** Get the maturity label for a block, or null if stable/absent. */
function getMaturityLabel(block: BlockDefinition): 'BETA' | 'EXP' | null {
  if (block.deprecated) return null
  const maturity = (block as any).maturity
  if (!maturity || maturity === 'stable') return null
  return maturity === 'beta' ? 'BETA' : 'EXP'
}

export default function BlockLibrary() {
  const [search, setSearch] = useState('')
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const blocksByCategory = getBlocksByCategory()
  const isSimple = useIsSimpleMode()
  const searchInputRef = useRef<HTMLInputElement>(null)

  // "/" keyboard shortcut to focus search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return
      if (e.key === '/' && !e.metaKey && !e.ctrlKey) {
        e.preventDefault()
        searchInputRef.current?.focus()
        searchInputRef.current?.select()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  // Smart add: find best open port and auto-wire
  const handleSmartAdd = useCallback((blockType: string) => {
    const state = usePipelineStore.getState()
    const { nodes, edges } = state
    const def = getBlockDefinition(blockType)
    if (!def) return

    // Find the best open port to connect to
    const connectedSources = new Set(edges.map((e) => `${e.source}:${e.sourceHandle}`))
    const connectedTargets = new Set(edges.map((e) => `${e.target}:${e.targetHandle}`))

    // Try to connect to an open output (this block goes downstream)
    for (const node of nodes) {
      const nodeDef = getBlockDefinition(node.data?.type)
      if (!nodeDef) continue
      for (const out of nodeDef.outputs) {
        if (connectedSources.has(`${node.id}:${out.id}`)) continue
        const compatible = def.inputs.some((inp) => isPortCompatible(out.dataType, inp.dataType))
        if (compatible) {
          state.addNodeAndConnect(blockType, { nodeId: node.id, portId: out.id, direction: 'downstream' })
          return
        }
      }
    }

    // Try to connect to an open required input (this block goes upstream)
    for (const node of nodes) {
      const nodeDef = getBlockDefinition(node.data?.type)
      if (!nodeDef) continue
      for (const inp of nodeDef.inputs) {
        if (!inp.required) continue
        if (connectedTargets.has(`${node.id}:${inp.id}`)) continue
        const compatible = def.outputs.some((out) => isPortCompatible(out.dataType, inp.dataType))
        if (compatible) {
          state.addNodeAndConnect(blockType, { nodeId: node.id, portId: inp.id, direction: 'upstream' })
          return
        }
      }
    }

    // No compatible open port — just add at center
    state.addNode(blockType, { x: 300, y: 300 })
  }, [])

  // Custom modules
  const [customBlocks, setCustomBlocks] = useState<CustomBlock[]>(() => loadCustomBlocks())
  const [showCustomEditor, setShowCustomEditor] = useState(false)
  const [duplicateTarget, setDuplicateTarget] = useState<string | undefined>(undefined)
  const [showGenerator, setShowGenerator] = useState(false)

  const refreshCustomBlocks = useCallback(() => {
    setCustomBlocks(loadCustomBlocks())
  }, [])

  // Detail panel state
  const [detailBlock, setDetailBlock] = useState<string | null>(null)
  const [categoryPopup, setCategoryPopup] = useState<string | null>(null)

  // Block documentation hover — dispatches to BlockDoc popover via custom events
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleItemHover = useCallback((blockType: string, rect: DOMRect) => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
    hoverTimerRef.current = setTimeout(() => {
      window.dispatchEvent(new CustomEvent('blueprint:show-block-doc', {
        detail: {
          blockType,
          anchor: { x: rect.right, y: rect.top, width: 0, height: rect.height },
        },
      }))
    }, 300)
  }, [])

  const handleItemLeave = useCallback(() => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
    window.dispatchEvent(new CustomEvent('blueprint:hide-block-doc'))
  }, [])

  const toggleCategory = (cat: string) => {
    setCollapsed((s) => ({ ...s, [cat]: !s[cat] }))
  }

  const onDragStart = (e: React.DragEvent, blockType: string) => {
    e.dataTransfer.setData('application/blueprint-block', blockType)
    e.dataTransfer.effectAllowed = 'move'

    // Custom drag ghost image
    const def = getBlockDefinition(blockType)
    if (def) {
      const ghost = document.createElement('div')
      ghost.style.cssText = `
        display: flex; align-items: center; gap: 6px;
        padding: 6px 12px; border-radius: 6px;
        background: ${T.surface2}; border: 1px solid ${def.accent};
        box-shadow: 0 4px 16px rgba(0,0,0,0.4);
        font-family: ${F}; font-size: 11px; color: ${T.text};
        font-weight: 600; white-space: nowrap;
        position: fixed; top: -100px; left: -100px; z-index: 99999;
        pointer-events: none;
      `
      ghost.textContent = def.name
      document.body.appendChild(ghost)
      e.dataTransfer.setDragImage(ghost, ghost.offsetWidth / 2, ghost.offsetHeight / 2)
      // Clean up after a brief delay (browser captures it synchronously)
      requestAnimationFrame(() => {
        setTimeout(() => document.body.removeChild(ghost), 0)
      })
    }
  }

  // Scored search function for natural language matching
  const scoreBlock = (block: BlockDefinition, query: string): number => {
    const q = query.toLowerCase()
    const useAliases = q.length > 2 // Short queries: name/description only

    const nameLower = block.name.toLowerCase()
    if (nameLower === q) return 100
    if (nameLower.startsWith(q)) return 80
    if (nameLower.includes(q)) return 50
    if (block.description.toLowerCase().includes(q)) return 20
    if (block.inputs.some(i => i.dataType.toLowerCase().includes(q))) return 15
    if (block.outputs.some(o => o.dataType.toLowerCase().includes(q))) return 15

    // Check block-level aliases and tags arrays
    if (block.aliases?.some((a: string) => a.toLowerCase().includes(q))) return 45
    if (block.tags?.some((t: string) => t.toLowerCase().includes(q))) return 35

    if (useAliases) {
      const aliases = BLOCK_ALIASES[block.type] || []
      if (aliases.some(a => a === q)) return 60
      if (aliases.some(a => a.includes(q))) return 40
      const catAliases = CATEGORY_ALIASES[block.category] || []
      if (catAliases.some(a => a.includes(q))) return 10
    }

    return 0
  }

  // Order categories and filter
  const effectiveCategoryOrder = isSimple
    ? CATEGORY_ORDER.filter((cat) => SIMPLE_CATEGORIES.has(cat))
    : CATEGORY_ORDER
  const orderedCategories = effectiveCategoryOrder
    .filter((cat) => blocksByCategory[cat])
    .map((category) => {
      let filtered = blocksByCategory[category]
      if (search) {
        const scored = filtered
          .map(b => ({ block: b, score: scoreBlock(b, search) }))
          .filter(({ score }) => score > 0)
          .sort((a, b) => b.score - a.score)
        filtered = scored.map(({ block }) => block)
      }
      // Sort: recommended first, deprecated last
      filtered = [...filtered].sort((a, b) => {
        if (a.recommended && !b.recommended) return -1
        if (!a.recommended && b.recommended) return 1
        if (a.deprecated && !b.deprecated) return 1
        if (!a.deprecated && b.deprecated) return -1
        return 0
      })
      return { category, blocks: filtered }
    })
    .filter(({ blocks }) => blocks.length > 0)

  return (
    <div
      style={{
        width: 300,
        minWidth: 300,
        height: '100%',
        background: `linear-gradient(180deg, ${T.surface1} 0%, ${T.surface0} 100%)`,
        backdropFilter: 'blur(10px)',
        borderRight: `1px solid ${T.border}`,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        boxShadow: 'inset -1px 0 0 rgba(255,255,255,0.02)',
        position: 'relative',
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
            color: T.dim,
            letterSpacing: '0.16em',
            fontWeight: 900,
            textTransform: 'uppercase',
          }}
        >
          BLOCK LIBRARY
        </span>
      </div>

      {/* Search */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          margin: '10px 10px 4px 10px',
          padding: '6px 12px',
          background: T.surface3,
          border: `1px solid ${T.border}`,
          borderRadius: 6,
          transition: 'all 0.2s',
          boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.1)',
        }}
      >
        <Search size={14} color={T.dim} />
        <input
          ref={searchInputRef}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search components..."
          style={{
            flex: 1,
            background: 'none',
            border: 'none',
            color: T.text,
            fontFamily: F,
            fontSize: FS.sm,
            outline: 'none',
            width: '100%',
          }}
        />
        {!search && (
          <span style={{
            fontFamily: F, fontSize: '9px', color: T.dim,
            background: T.surface4, padding: '1px 5px', borderRadius: 3,
            opacity: 0.6, flexShrink: 0,
          }}>
            /
          </span>
        )}
      </div>

      {/* Generate with AI button */}
      {!isSimple && (
        <button
          onClick={() => setShowGenerator(true)}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            margin: '4px 10px 6px', padding: '7px 12px',
            background: `${T.purple}12`, border: `1px solid ${T.purple}25`,
            borderRadius: 6, cursor: 'pointer', width: 'calc(100% - 20px)',
            transition: 'all 0.15s',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = `${T.purple}22`; e.currentTarget.style.borderColor = `${T.purple}40` }}
          onMouseLeave={(e) => { e.currentTarget.style.background = `${T.purple}12`; e.currentTarget.style.borderColor = `${T.purple}25` }}
        >
          <Sparkles size={12} color={T.purple} />
          <span style={{ fontFamily: F, fontSize: FS.xs, color: T.purple, fontWeight: 700 }}>
            Generate with AI
          </span>
        </button>
      )}

      {/* Block list */}
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 4px', scrollbarWidth: 'thin' }}>

        {/* Custom Modules Section */}
        {!search && !isSimple && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, margin: '0 4px', padding: '6px 8px' }}>
              <button
                onClick={() => toggleCategory('custom')}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  background: 'none', border: 'none', cursor: 'pointer', padding: 0,
                  color: T.cyan, fontFamily: F, fontSize: FS.xs, fontWeight: 900,
                  letterSpacing: '0.12em', textTransform: 'uppercase' as const,
                }}
              >
                {collapsed['custom'] ? <ChevronRight size={10} color={T.dim} /> : <ChevronDown size={10} color={T.dim} />}
                <span style={{ width: 6, height: 6, background: T.cyan, borderRadius: '50%', boxShadow: `0 0 8px ${T.cyan}80` }} />
                CUSTOM
              </button>
              <button
                onClick={() => { setDuplicateTarget(undefined); setShowCustomEditor(true) }}
                style={{
                  marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 3,
                  background: `${T.cyan}15`, border: `1px solid ${T.cyan}30`, borderRadius: 4,
                  color: T.cyan, fontFamily: F, fontSize: FS.xxs, padding: '2px 8px', cursor: 'pointer',
                }}
              >
                <Plus size={8} /> NEW
              </button>
            </div>
            {!collapsed['custom'] && customBlocks.length > 0 && (
              <div style={{ display: 'grid', gap: 2, padding: '4px 0' }}>
                {customBlocks.map((block) => (
                  <BlockItem
                    key={block.type}
                    block={block as BlockDefinition}
                    onDragStart={onDragStart}
                    onMouseEnter={(e) => handleItemHover(block.type, e.currentTarget.getBoundingClientRect())}
                    onMouseLeave={handleItemLeave}
                    onDuplicate={(type) => { setDuplicateTarget(type); setShowCustomEditor(true) }}
                    onSmartAdd={handleSmartAdd}
                  />
                ))}
              </div>
            )}
            {!collapsed['custom'] && customBlocks.length === 0 && (
              <div style={{ padding: '8px 16px', fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                No custom modules yet. Click + NEW to create one.
              </div>
            )}
          </div>
        )}

        {orderedCategories.map(({ category, blocks }) => {
          const catColor = CATEGORY_COLORS[category] || T.dim
          return (
            <div key={category} style={{ marginBottom: 8 }}>
              {/* Category header */}
              <button
                onClick={() => toggleCategory(category)}
                className="hover-glow"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  width: 'calc(100% - 8px)',
                  margin: '0 4px',
                  padding: '6px 8px',
                  background: 'none',
                  border: 'none',
                  color: catColor,
                  fontFamily: F,
                  fontSize: FS.xs,
                  letterSpacing: '0.12em',
                  fontWeight: 900,
                  textTransform: 'uppercase',
                  cursor: 'pointer',
                  borderRadius: 4,
                  transition: 'background 0.2s',
                }}
              >
                {collapsed[category] ? <ChevronRight size={10} color={T.dim} /> : <ChevronDown size={10} color={T.dim} />}
                <span
                  style={{
                    width: 6,
                    height: 6,
                    background: catColor,
                    borderRadius: '50%',
                    flexShrink: 0,
                    boxShadow: `0 0 8px ${catColor}80`,
                  }}
                />
                {CATEGORY_LABELS[category] || category.toUpperCase()}
                <span style={{ color: T.dim, fontWeight: 500, marginLeft: 'auto', background: T.surface3, padding: '2px 6px', borderRadius: 4, fontSize: FS.xxs }}>
                  {blocks.length}
                </span>
              </button>

              {!collapsed[category] &&
                <div style={{ display: 'flex', flexDirection: 'column', padding: '4px 6px', gap: 2 }}>
                  {blocks.map((b) => (
                    <BlockItem
                      key={b.type}
                      block={b}
                      tourId={`block-${category}-${b.type}`}
                      onDragStart={onDragStart}
                      onMouseEnter={(e) => handleItemHover(b.type, e.currentTarget.getBoundingClientRect())}
                      onMouseLeave={handleItemLeave}
                      onSmartAdd={handleSmartAdd}
                      onClick={(type) => setDetailBlock(type)}
                    />
                  ))}
                </div>
              }
            </div>
          )
        })}
      </div>

      {/* Connector type legend bar */}
      <ConnectorLegend onConnectorClick={(ct) => setCategoryPopup(ct)} />

      {/* Connector detail popup */}
      {categoryPopup && (
        <ConnectorDetailPopup
          connectorType={categoryPopup}
          onClose={() => setCategoryPopup(null)}
          onBlockClick={(type) => { setCategoryPopup(null); setDetailBlock(type) }}
        />
      )}

      {/* Custom Module Editor */}
      <CustomModuleEditor
        visible={showCustomEditor}
        onClose={() => setShowCustomEditor(false)}
        duplicateFrom={duplicateTarget}
        onSaved={refreshCustomBlocks}
      />

      {/* Block Generator Modal */}
      <BlockGeneratorModal
        visible={showGenerator}
        onClose={() => setShowGenerator(false)}
      />

      {/* Block Detail Panel */}
      <BlockDetailPanel
        blockType={detailBlock}
        onClose={() => setDetailBlock(null)}
        onAddBlock={(type) => {
          usePipelineStore.getState().addNode(type, { x: 400, y: 300 })
          setDetailBlock(null)
        }}
      />
    </div>
  )
}

function BlockItem({
  block,
  tourId,
  onDragStart,
  onMouseEnter,
  onMouseLeave,
  onDuplicate,
  onClick,
  onSmartAdd,
}: {
  block: BlockDefinition
  tourId?: string
  onDragStart: (e: React.DragEvent, type: string) => void
  onMouseEnter: (e: React.MouseEvent) => void
  onMouseLeave: () => void
  onDuplicate?: (blockType: string) => void
  onClick?: (blockType: string) => void
  onSmartAdd?: (blockType: string) => void
}) {
  const [hovered, setHovered] = useState(false)
  const IconComponent = (Icons as any)[block.icon] || Icons.Box
  const itemRef = useRef<HTMLDivElement>(null)

  return (
    <div
      ref={itemRef}
      draggable
      data-tour={tourId}
      onClick={() => onClick?.(block.type)}
      onDragStart={(e) => onDragStart(e, block.type)}
      onMouseEnter={(e) => {
        setHovered(true)
        if (onMouseEnter) onMouseEnter(e)
      }}
      onMouseLeave={() => {
        setHovered(false)
        if (onMouseLeave) onMouseLeave()
      }}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        margin: '0 8px',
        padding: '8px 12px',
        cursor: 'grab',
        background: hovered ? `${T.surface3}90` : 'transparent',
        borderRadius: 6,
        border: `1px solid ${hovered ? T.borderHi : 'transparent'}`,
        boxShadow: hovered ? `0 4px 12px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.05)` : 'none',
        transform: hovered ? 'translateY(-1px)' : 'none',
        transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Accent glow line inside */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          bottom: 0,
          width: 3,
          background: block.accent,
          opacity: hovered ? 1 : 0.3,
          transition: 'opacity 0.2s',
          boxShadow: hovered ? `0 0 10px ${block.accent}` : 'none',
        }}
      />

      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 28,
        height: 28,
        borderRadius: 6,
        background: `linear-gradient(135deg, ${T.surface3}, ${T.surface1})`,
        border: `1px solid ${T.borderHi}`,
        boxShadow: hovered ? `0 0 12px ${block.accent}40` : 'none',
        transition: 'all 0.2s'
      }}>
        <IconComponent size={14} color={block.accent} style={{ flexShrink: 0 }} />
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontFamily: F,
            fontSize: FS.sm,
            color: block.deprecated ? T.dim : (hovered ? T.text : T.sec),
            fontWeight: 600,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            transition: 'color 0.2s',
            opacity: block.deprecated ? 0.6 : 1,
          }}
        >
          {block.name}
          {block.deprecated && <span style={{ ...BADGE_STYLES.deprecated, fontSize: '7px' }}>DEPRECATED</span>}
          {block.recommended && <span style={{ ...BADGE_STYLES.recommended, fontSize: '7px' }}>RECOMMENDED</span>}
          {(() => { const m = getMaturityLabel(block); return m && <span style={{ ...BADGE_STYLES[m === 'BETA' ? 'beta' : 'experimental'], fontSize: '7px' }}>{m}</span> })()}
        </div>
        <div
          style={{
            fontFamily: F,
            fontSize: FS.xxs,
            color: T.dim,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            marginTop: 2,
            opacity: block.deprecated ? 0.5 : 1,
          }}
        >
          {block.description}
        </div>
      </div>

      {/* Port type dots — two rows: inputs (top) and outputs (bottom) */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 3, flexShrink: 0, paddingLeft: 4 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, alignItems: 'flex-end' }}>
          {/* Input ports row */}
          {block.inputs.length > 0 && (
            <div style={{ display: 'flex', gap: 2, alignItems: 'center' }}>
              <span style={{
                fontFamily: F, fontSize: 6, color: T.dim, letterSpacing: '0.04em',
                fontWeight: 600, textTransform: 'uppercase' as const, marginRight: 1,
              }}>
                IN
              </span>
              {block.inputs.map((p) => {
                const pc = getPortColor(p.dataType)
                return (
                  <span
                    key={`i-${p.id}`}
                    title={`Input: ${p.label} (${p.dataType}) — ${p.required ? 'required' : 'optional'}`}
                    style={{
                      width: 7, height: 7, borderRadius: '50%',
                      background: p.required ? pc : 'transparent',
                      border: p.required ? 'none' : `1.5px solid ${pc}`,
                      display: 'block',
                      boxShadow: p.required ? `0 0 4px ${pc}` : 'none',
                    }}
                  />
                )
              })}
            </div>
          )}
          {/* Output ports row */}
          {block.outputs.length > 0 && (
            <div style={{ display: 'flex', gap: 2, alignItems: 'center' }}>
              <span style={{
                fontFamily: F, fontSize: 6, color: T.dim, letterSpacing: '0.04em',
                fontWeight: 600, textTransform: 'uppercase' as const, marginRight: 1,
              }}>
                OUT
              </span>
              {block.outputs.map((p) => {
                const pc = getPortColor(p.dataType)
                return (
                  <span
                    key={`o-${p.id}`}
                    title={`Output: ${p.label} (${p.dataType}) — ${p.required ? 'required' : 'optional'}`}
                    style={{
                      width: 7, height: 7, borderRadius: '50%',
                      background: p.required ? pc : 'transparent',
                      border: p.required ? 'none' : `1.5px solid ${pc}`,
                      display: 'block',
                      boxShadow: p.required ? `0 0 4px ${pc}` : 'none',
                    }}
                  />
                )
              })}
            </div>
          )}
        </div>
        {hovered && onSmartAdd && (
          <button
            onClick={(e) => { e.stopPropagation(); onSmartAdd(block.type) }}
            title="Add to canvas & auto-connect"
            style={{
              background: `${T.green}18`, border: `1px solid ${T.green}35`, borderRadius: 4,
              color: T.green, cursor: 'pointer', padding: '2px 6px', display: 'flex',
              alignItems: 'center', gap: 2,
            }}
          >
            <Zap size={8} />
            <Plus size={8} />
          </button>
        )}
        {hovered && onDuplicate && (
          <button
            onClick={(e) => { e.stopPropagation(); onDuplicate(block.type) }}
            title="Duplicate as custom module"
            style={{
              background: `${T.cyan}15`, border: `1px solid ${T.cyan}30`, borderRadius: 4,
              color: T.cyan, cursor: 'pointer', padding: '2px 4px', display: 'flex',
            }}
          >
            <Icons.Copy size={10} />
          </button>
        )}
      </div>
    </div>
  )
}

/* ── Category descriptions for detail popup ── */
const CATEGORY_DESCRIPTIONS: Record<string, { summary: string; connectorNote: string }> = {
  external:      { summary: 'Source blocks that ingest data from the outside world — APIs, files, databases, HuggingFace Hub, and web scraping.',         connectorNote: 'Produces dataset, text, model, or config connectors depending on the source type.' },
  data:          { summary: 'Transform blocks for data manipulation — filtering, splitting, chunking, augmenting, and previewing datasets.',             connectorNote: 'Primarily uses dataset and text connectors for structured and unstructured data.' },
  model:         { summary: 'Model ops blocks — loading, selecting, merging (SLERP/DARE/TIES), quantizing, and packaging model weights.',                  connectorNote: 'Uses model connectors for weights and adapters, dataset for batch I/O.' },
  inference:     { summary: 'Inference blocks — LLM prompting, chat, structured output, vision, translation, summarization, and content safety.',       connectorNote: 'Accepts optional model connector, produces text, dataset, or metrics connectors.' },
  training:      { summary: 'Training blocks — fine-tuning (LoRA/QLoRA/Full), alignment (DPO/RLHF), distillation, and hyperparameter sweeps.',           connectorNote: 'Consumes dataset + model connectors, produces model + metrics connectors.' },
  metrics:       { summary: 'Evaluation blocks — LM Eval Harness, MMLU, custom metrics, report generation, and experiment logging.',                     connectorNote: 'Uses metrics connectors for scores and artifact connectors for reports.' },
  embedding:     { summary: 'Vector operation blocks — generating embeddings, building vector stores, similarity search, and clustering.',                connectorNote: 'Uses embedding connectors for vectors, dataset for metadata, config for indices.' },
  utilities:     { summary: 'Flow control blocks — conditional branching, looping, parallel fan-out, aggregation, and artifact viewing.',                 connectorNote: 'Uses any connectors for type-agnostic pass-through routing.' },
  agents:        { summary: 'Autonomous agent blocks — orchestrators, tool registries, chain-of-thought, multi-agent debate, and memory.',               connectorNote: 'Uses agent connectors for agent instances, plus model, dataset, and config.' },
  interventions: { summary: 'Gate blocks — human-in-the-loop review, quality gates, A/B testing, notifications, and rollback points.',                   connectorNote: 'Uses any connectors for type-agnostic gating and pass-through.' },
  endpoints:     { summary: 'Terminal blocks that persist or export pipeline results — save to files, push to APIs, databases, and HuggingFace Hub.',     connectorNote: 'Consumes dataset, text, model, config, or any connectors. No outputs (true sinks).' },
}

/* ── Connector type descriptions for legend popup ── */
const CONNECTOR_DESCRIPTIONS: Record<string, { label: string; summary: string; examples: string }> = {
  dataset:   { label: 'Dataset',   summary: 'Structured tabular data — CSV rows, Parquet tables, HuggingFace datasets. The primary data format for training, evaluation, and transforms.', examples: 'CSV files, Parquet tables, JSONL, HuggingFace datasets' },
  text:      { label: 'Text',      summary: 'Raw text strings — prompts, documents, generated output. Used for LLM input/output and text processing pipelines.', examples: 'Prompts, completions, documents, Markdown' },
  model:     { label: 'Model',     summary: 'Model weights, adapters, and checkpoints. Connects model loading/training to inference or export blocks.', examples: 'LoRA adapters, safetensors, GGUF files, checkpoints' },
  config:    { label: 'Config',    summary: 'Configuration objects and hyperparameters. Passes settings between blocks for consistent pipeline behavior.', examples: 'Generation params, training hyperparams, API settings' },
  metrics:   { label: 'Metrics',   summary: 'Evaluation scores, benchmark results, and statistical outputs. Connects evaluation blocks to reports and loggers.', examples: 'Accuracy scores, BLEU/ROUGE, perplexity, custom metrics' },
  embedding: { label: 'Embedding', summary: 'Vector embeddings for similarity search, clustering, and RAG. Dense numerical representations of text or data.', examples: 'Sentence embeddings, document vectors, index files' },
  artifact:  { label: 'Artifact',  summary: 'Generic files, reports, and exported assets. Catch-all for non-structured outputs like PDFs, images, or packages.', examples: 'PDF reports, ZIP archives, images, HTML files' },
  agent:     { label: 'Agent',     summary: 'Autonomous agent instances with tools and memory. Connects agent orchestrators to downstream processing.', examples: 'ReAct agents, tool-using agents, multi-agent systems' },
  llm:       { label: 'LLM',       summary: 'LLM provider configuration — API keys, model names, and generation settings. Connects model selectors to inference blocks.', examples: 'OpenAI config, Ollama endpoint, HuggingFace model ID' },
  any:       { label: 'Any',       summary: 'Universal connector — accepts or produces any data type. Used by flow control blocks (branching, looping, gates) for type-agnostic routing.', examples: 'Pass-through, conditional routing, fan-out/fan-in' },
}

const CONNECTOR_ORDER = ['dataset', 'text', 'model', 'config', 'metrics', 'embedding', 'artifact', 'agent', 'llm', 'any']

/* ── ConnectorLegend — bottom bar showing connector types as a legend ── */
function ConnectorLegend({ onConnectorClick }: { onConnectorClick: (ct: string) => void }) {
  const [hovered, setHovered] = useState<string | null>(null)
  return (
    <div style={{
      padding: '4px 6px',
      borderTop: `1px solid ${T.border}`,
      display: 'flex',
      flexWrap: 'wrap',
      gap: 1,
      alignItems: 'center',
    }}>
      <span style={{
        fontFamily: F, fontSize: 6, color: T.dim, letterSpacing: '0.08em',
        fontWeight: 700, marginRight: 2, textTransform: 'uppercase',
      }}>
        WIRES
      </span>
      {CONNECTOR_ORDER.map((ct) => {
        const color = CONNECTOR_COLORS[ct] || T.dim
        const isHov = hovered === ct
        const desc = CONNECTOR_DESCRIPTIONS[ct]
        return (
          <button
            key={ct}
            onClick={() => onConnectorClick(ct)}
            onMouseEnter={() => setHovered(ct)}
            onMouseLeave={() => setHovered(null)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 3,
              padding: '2px 5px',
              background: isHov ? `${color}18` : 'transparent',
              border: `1px solid ${isHov ? `${color}40` : 'transparent'}`,
              borderRadius: 3,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              transition: 'all 0.15s',
            }}
          >
            <span style={{
              width: 5,
              height: 5,
              background: color,
              borderRadius: '50%',
              display: 'block',
              boxShadow: isHov ? `0 0 6px ${color}80` : `0 0 3px ${color}40`,
              flexShrink: 0,
            }} />
            <span style={{
              fontFamily: F,
              fontSize: 7,
              color: isHov ? color : T.dim,
              letterSpacing: '0.04em',
              fontWeight: 600,
              transition: 'color 0.15s',
            }}>
              {desc?.label || ct}
            </span>
          </button>
        )
      })}
    </div>
  )
}

/* ── ConnectorDetailPopup — detail overlay for a connector type ── */
function ConnectorDetailPopup({
  connectorType,
  onClose,
  onBlockClick,
}: {
  connectorType: string
  onClose: () => void
  onBlockClick: (blockType: string) => void
}) {
  const color = CONNECTOR_COLORS[connectorType] || T.dim
  const desc = CONNECTOR_DESCRIPTIONS[connectorType]
  if (!desc) return null

  // Find blocks that use this connector type as input or output
  const inputBlocks = getAllBlocks().filter(b => !b.deprecated && b.inputs.some(p => p.dataType === connectorType))
  const outputBlocks = getAllBlocks().filter(b => !b.deprecated && b.outputs.some(p => p.dataType === connectorType))

  return (
    <div
      onClick={onClose}
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 200,
        background: 'rgba(0,0,0,0.6)',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: 280,
          maxHeight: '80%',
          background: `linear-gradient(145deg, ${T.surface2} 0%, ${T.surface0} 100%)`,
          border: `1px solid ${T.borderHi}`,
          borderRadius: 10,
          boxShadow: `0 20px 60px ${T.shadow}, 0 0 30px ${color}15`,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Accent bar */}
        <div style={{ height: 3, background: `linear-gradient(90deg, ${color}, ${color}40, transparent)` }} />

        {/* Header */}
        <div style={{ padding: '14px 16px 10px', borderBottom: `1px solid ${T.border}` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span style={{
              width: 10, height: 10, background: color, borderRadius: '50%',
              boxShadow: `0 0 10px ${color}80`,
            }} />
            <span style={{ fontFamily: F, fontSize: FS.md, color, fontWeight: 900, letterSpacing: '0.08em' }}>
              {desc.label.toUpperCase()}
            </span>
            <span style={{
              marginLeft: 'auto', fontFamily: F, fontSize: FS.xxs, color: T.dim,
              background: T.surface3, padding: '2px 8px', borderRadius: 4,
            }}>
              wire type
            </span>
            <button
              onClick={onClose}
              style={{
                background: 'none', border: 'none', cursor: 'pointer', padding: 2,
                color: T.dim, display: 'flex', alignItems: 'center',
              }}
            >
              <Icons.X size={14} />
            </button>
          </div>
          <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, lineHeight: 1.5 }}>
            {desc.summary}
          </div>
        </div>

        {/* Examples */}
        <div style={{ padding: '8px 16px', borderBottom: `1px solid ${T.border}`, background: `${color}06` }}>
          <div style={{
            fontFamily: F, fontSize: 7, fontWeight: 700, letterSpacing: '0.08em',
            color, textTransform: 'uppercase', marginBottom: 4,
          }}>
            EXAMPLES
          </div>
          <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, lineHeight: 1.4 }}>
            {desc.examples}
          </div>
        </div>

        {/* Blocks that use this connector */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '6px 8px', scrollbarWidth: 'thin' }}>
          {outputBlocks.length > 0 && (
            <>
              <div style={{ fontFamily: F, fontSize: 7, color: T.green, letterSpacing: '0.1em', fontWeight: 700, padding: '4px 8px', marginBottom: 2 }}>
                PRODUCES {desc.label.toUpperCase()} ({outputBlocks.length})
              </div>
              {outputBlocks.slice(0, 8).map(b => {
                const IconComp = (Icons as any)[b.icon] || Icons.Box
                return (
                  <button
                    key={b.type}
                    onClick={() => onBlockClick(b.type)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      width: '100%', padding: '5px 8px',
                      background: 'transparent', border: 'none', borderRadius: 4,
                      cursor: 'pointer', textAlign: 'left',
                      transition: 'background 0.1s',
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = `${color}12` }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                  >
                    <IconComp size={10} color={b.accent} style={{ flexShrink: 0 }} />
                    <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, fontWeight: 500 }}>
                      {b.name}
                    </span>
                  </button>
                )
              })}
              {outputBlocks.length > 8 && (
                <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, padding: '2px 8px' }}>
                  +{outputBlocks.length - 8} more
                </div>
              )}
            </>
          )}
          {inputBlocks.length > 0 && (
            <>
              <div style={{ fontFamily: F, fontSize: 7, color: T.cyan, letterSpacing: '0.1em', fontWeight: 700, padding: '4px 8px', marginTop: 6, marginBottom: 2 }}>
                CONSUMES {desc.label.toUpperCase()} ({inputBlocks.length})
              </div>
              {inputBlocks.slice(0, 8).map(b => {
                const IconComp = (Icons as any)[b.icon] || Icons.Box
                return (
                  <button
                    key={b.type}
                    onClick={() => onBlockClick(b.type)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      width: '100%', padding: '5px 8px',
                      background: 'transparent', border: 'none', borderRadius: 4,
                      cursor: 'pointer', textAlign: 'left',
                      transition: 'background 0.1s',
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = `${color}12` }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
                  >
                    <IconComp size={10} color={b.accent} style={{ flexShrink: 0 }} />
                    <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.sec, fontWeight: 500 }}>
                      {b.name}
                    </span>
                  </button>
                )
              })}
              {inputBlocks.length > 8 && (
                <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, padding: '2px 8px' }}>
                  +{inputBlocks.length - 8} more
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
