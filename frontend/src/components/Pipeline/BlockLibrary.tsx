import { useState, useRef, useCallback } from 'react'
import { T, F, FS, CONNECTOR_COLORS, CATEGORY_COLORS } from '@/lib/design-tokens'
import { getBlocksByCategory, getPortColor, type BlockDefinition, BLOCK_REGISTRY } from '@/lib/block-registry'
import { BLOCK_ALIASES, CATEGORY_ALIASES } from '@/lib/search-aliases'
import BlockTooltip from './BlockTooltip'
import BlockDetailPanel from './BlockDetailPanel'
import CustomModuleEditor, { loadCustomBlocks, type CustomBlock } from './CustomModuleEditor'
import BlockGeneratorModal from './BlockGeneratorModal'
import { usePipelineStore } from '@/stores/pipelineStore'
import { useIsSimpleMode } from '@/hooks/useIsSimpleMode'
import * as Icons from 'lucide-react'

const { Search, ChevronRight, ChevronDown, Plus, Sparkles } = Icons

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

  // Tooltip state
  const [tooltipBlock, setTooltipBlock] = useState<string | null>(null)
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleItemHover = useCallback((blockType: string, rect: DOMRect) => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
    hoverTimerRef.current = setTimeout(() => {
      setTooltipBlock(blockType)
      setTooltipPos({ x: rect.right + 8, y: rect.top })
    }, 300)
  }, [])

  const handleItemLeave = useCallback(() => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current)
    setTooltipBlock(null)
  }, [])

  const toggleCategory = (cat: string) => {
    setCollapsed((s) => ({ ...s, [cat]: !s[cat] }))
  }

  const onDragStart = (e: React.DragEvent, blockType: string) => {
    e.dataTransfer.setData('application/blueprint-block', blockType)
    e.dataTransfer.effectAllowed = 'move'

    // Custom drag ghost image
    const def = BLOCK_REGISTRY.find((b) => b.type === blockType)
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
                      onClick={(type) => setDetailBlock(type)}
                    />
                  ))}
                </div>
              }
            </div>
          )
        })}
      </div>

      {/* Category bar */}
      <CategoryBar onCategoryClick={(cat) => setCategoryPopup(cat)} categories={effectiveCategoryOrder} />

      {/* Category detail popup */}
      {categoryPopup && (
        <CategoryDetailPopup
          category={categoryPopup}
          onClose={() => setCategoryPopup(null)}
          onBlockClick={(type) => { setCategoryPopup(null); setDetailBlock(type) }}
        />
      )}

      {/* Hover tooltip rendered as portal-like overlay */}
      {tooltipBlock && (
        <div style={{ position: 'fixed', left: tooltipPos.x, top: tooltipPos.y, zIndex: 9999, pointerEvents: 'none' }}>
          <BlockTooltip blockType={tooltipBlock} visible position={{ x: 0, y: 0 }} />
        </div>
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
}: {
  block: BlockDefinition
  tourId?: string
  onDragStart: (e: React.DragEvent, type: string) => void
  onMouseEnter: (e: React.MouseEvent) => void
  onMouseLeave: () => void
  onDuplicate?: (blockType: string) => void
  onClick?: (blockType: string) => void
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

/* ── CategoryBar — 10 category buttons at the bottom ── */
function CategoryBar({ onCategoryClick, categories }: { onCategoryClick: (cat: string) => void; categories: string[] }) {
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
      {categories.map((cat) => {
        const color = CATEGORY_COLORS[cat] || T.dim
        const isHov = hovered === cat
        return (
          <button
            key={cat}
            onClick={() => onCategoryClick(cat)}
            onMouseEnter={() => setHovered(cat)}
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
              width: 4,
              height: 4,
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
              {cat}
            </span>
          </button>
        )
      })}
    </div>
  )
}

/* ── CategoryDetailPopup — full detail overlay for a category ── */
function CategoryDetailPopup({
  category,
  onClose,
  onBlockClick,
}: {
  category: string
  onClose: () => void
  onBlockClick: (blockType: string) => void
}) {
  const color = CATEGORY_COLORS[category] || T.dim
  const label = CATEGORY_LABELS[category] || category.toUpperCase()
  const desc = CATEGORY_DESCRIPTIONS[category]
  const blocks = Object.values(BLOCK_REGISTRY).filter(b => b.category === category)
  const hasConnector = ['external', 'data', 'model', 'inference', 'training', 'metrics', 'embedding', 'agents', 'endpoints'].includes(category)

  // Collect unique port types used by blocks in this category
  const portTypes = new Set<string>()
  blocks.forEach(b => {
    b.inputs.forEach(p => portTypes.add(p.dataType))
    b.outputs.forEach(p => portTypes.add(p.dataType))
  })

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
              {label}
            </span>
            <span style={{
              marginLeft: 'auto', fontFamily: F, fontSize: FS.xxs, color: T.dim,
              background: T.surface3, padding: '2px 8px', borderRadius: 4,
            }}>
              {blocks.length} blocks
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
            {desc?.summary || ''}
          </div>
        </div>

        {/* Connector info */}
        <div style={{ padding: '8px 16px', borderBottom: `1px solid ${T.border}`, background: `${color}06` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{
              fontFamily: F, fontSize: 7, fontWeight: 700, letterSpacing: '0.08em',
              color: hasConnector ? color : T.dim,
              textTransform: 'uppercase',
            }}>
              {hasConnector ? '● HAS CONNECTOR TYPE' : '○ NO DEDICATED CONNECTOR'}
            </span>
          </div>
          <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 3, lineHeight: 1.4 }}>
            {desc?.connectorNote || ''}
          </div>
          {portTypes.size > 0 && (
            <div style={{ display: 'flex', gap: 4, marginTop: 6, flexWrap: 'wrap' }}>
              {Array.from(portTypes).map(pt => (
                <span key={pt} style={{
                  fontFamily: F, fontSize: 7, color: CONNECTOR_COLORS[pt] || T.dim,
                  background: `${CONNECTOR_COLORS[pt] || T.dim}12`,
                  border: `1px solid ${CONNECTOR_COLORS[pt] || T.dim}25`,
                  padding: '1px 5px', borderRadius: 3,
                }}>
                  {pt}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Block list */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '6px 8px', scrollbarWidth: 'thin' }}>
          <div style={{ fontFamily: F, fontSize: 7, color: T.dim, letterSpacing: '0.1em', fontWeight: 700, padding: '4px 8px', marginBottom: 2 }}>
            BLOCKS IN THIS CATEGORY
          </div>
          {blocks.map(b => {
            const IconComp = (Icons as any)[b.icon] || Icons.Box
            return (
              <button
                key={b.type}
                onClick={() => onBlockClick(b.type)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  width: '100%', padding: '6px 8px',
                  background: 'transparent', border: 'none', borderRadius: 4,
                  cursor: 'pointer', textAlign: 'left',
                  transition: 'background 0.1s',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = `${color}12` }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent' }}
              >
                <IconComp size={11} color={color} style={{ flexShrink: 0 }} />
                <span style={{ fontFamily: F, fontSize: FS.xxs, color: b.deprecated ? T.dim : T.sec, fontWeight: 500, opacity: b.deprecated ? 0.6 : 1 }}>
                  {b.name}
                </span>
                {b.deprecated && <span style={{ ...BADGE_STYLES.deprecated, fontSize: '6px', padding: '0px 3px', borderRadius: 2, marginLeft: 'auto' }}>DEPRECATED</span>}
                {b.recommended && <span style={{ ...BADGE_STYLES.recommended, fontSize: '6px', padding: '0px 3px', borderRadius: 2, marginLeft: 'auto' }}>RECOMMENDED</span>}
                {(() => { const m = getMaturityLabel(b); return m && <span style={{ ...BADGE_STYLES[m === 'BETA' ? 'beta' : 'experimental'], fontSize: '6px', padding: '0px 3px', borderRadius: 2, marginLeft: 'auto' }}>{m}</span> })()}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
