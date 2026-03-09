import { useState, useMemo } from 'react'
import { T, F, FS, FD, CATEGORY_COLORS } from '@/lib/design-tokens'
import { BLOCK_REGISTRY, type BlockDefinition, getBlocksByCategory, getPortColor } from '@/lib/block-registry'
import { getIcon } from '@/lib/icon-utils'
import PanelCard from '@/components/shared/PanelCard'
import BlockDetailPage from '@/components/Marketplace/BlockDetailPage'
import RecipeDetailPage from '@/components/Marketplace/RecipeDetailPage'
import { Search, Package, LayoutTemplate, PlusCircle, ArrowRight, Bookmark, Trash2 } from 'lucide-react'
import { COMMUNITY_RECIPES, type Recipe } from '@/lib/recipes'
import { usePresetStore } from '@/stores/presetStore'
import { usePipelineStore } from '@/stores/pipelineStore'
import { AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'

type Tab = 'library' | 'recipes' | 'presets'
type SubView = 'browse' | 'block-detail' | 'recipe-detail'

const CATEGORY_ORDER = ['external', 'data', 'model', 'inference', 'training', 'metrics', 'embedding', 'utilities', 'agents', 'interventions', 'endpoints']
const CATEGORY_LABELS: Record<string, string> = {
  external: 'Sources', data: 'Transforms', model: 'Model Ops', inference: 'Inference', training: 'Training',
  metrics: 'Evaluation', embedding: 'Vectors', utilities: 'Flow Control', agents: 'Agents',
  interventions: 'Gates', endpoints: 'Endpoints',
}

export default function MarketplaceView() {
  const [search, setSearch] = useState('')
  const [activeTab, setActiveTab] = useState<Tab>('library')
  const [categoryFilter, setCategoryFilter] = useState<string>('')

  // Sub-view navigation state
  const [subView, setSubView] = useState<SubView>('browse')
  const [selectedBlock, setSelectedBlock] = useState<BlockDefinition | null>(null)
  const [selectedRecipe, setSelectedRecipe] = useState<Recipe | null>(null)

  const applyGeneratedWorkflow = usePipelineStore((s) => s.applyGeneratedWorkflow)

  const filtered = useMemo(() => {
    return BLOCK_REGISTRY.filter((b) => {
      const q = search.toLowerCase()
      const matchSearch =
        !search ||
        b.name.toLowerCase().includes(q) ||
        b.description.toLowerCase().includes(q) ||
        b.type.toLowerCase().includes(q) ||
        b.aliases?.some((a: string) => a.toLowerCase().includes(q)) ||
        b.tags?.some((t: string) => t.toLowerCase().includes(q))
      const matchCategory = !categoryFilter || b.category === categoryFilter
      return matchSearch && matchCategory
    })
  }, [search, categoryFilter])

  // Handle block detail navigation
  const handleBlockClick = (block: BlockDefinition) => {
    setSelectedBlock(block)
    setSubView('block-detail')
  }

  // Handle recipe detail navigation
  const handleRecipeClick = (recipe: Recipe) => {
    setSelectedRecipe(recipe)
    setSubView('recipe-detail')
  }

  // Handle back from detail pages
  const handleBackFromBlock = () => {
    setSubView('browse')
    setSelectedBlock(null)
  }

  const handleBackFromRecipe = () => {
    setSubView('browse')
    setSelectedRecipe(null)
  }

  // Handle navigating from recipe detail to block detail (cross-nav)
  const handleSelectBlockFromRecipe = (block: BlockDefinition) => {
    setSelectedBlock(block)
    setSubView('block-detail')
  }

  // If in block-detail or recipe-detail, render the full-page detail
  if (subView === 'block-detail' && selectedBlock) {
    return (
      <AnimatePresence mode="wait">
        <BlockDetailPage
          key={`block-${selectedBlock.type}`}
          block={selectedBlock}
          onBack={handleBackFromBlock}
          onSelectBlock={handleBlockClick}
        />
      </AnimatePresence>
    )
  }

  if (subView === 'recipe-detail' && selectedRecipe) {
    return (
      <AnimatePresence mode="wait">
        <RecipeDetailPage
          key={`recipe-${selectedRecipe.id}`}
          recipe={selectedRecipe}
          onBack={handleBackFromRecipe}
          onSelectBlock={handleSelectBlockFromRecipe}
        />
      </AnimatePresence>
    )
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        borderBottom: `1px solid ${T.border}`,
        flexShrink: 0,
      }}>
        <h2 style={{
          fontFamily: FD,
          fontSize: FS.xl * 1.5,
          fontWeight: 600,
          color: T.text,
          margin: 0,
          letterSpacing: '0.04em',
        }}>
          MODULE LIBRARY
        </h2>
        <div style={{ flex: 1 }} />

        {/* Tabs */}
        {[
          { id: 'library' as Tab, label: 'ALL BLOCKS', icon: Package },
          { id: 'recipes' as Tab, label: 'RECIPES HUB', icon: LayoutTemplate },
          { id: 'presets' as Tab, label: 'PRESETS', icon: Bookmark },
        ].map((tab) => {
          const Icon = tab.icon
          const active = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '6px 12px',
                background: active ? `${T.cyan}15` : 'transparent',
                border: active ? `1px solid ${T.cyan}40` : `1px solid ${T.border}`,
                borderRadius: 4,
                color: active ? T.cyan : T.dim,
                fontFamily: F, fontSize: FS.xs, letterSpacing: '0.08em',
                cursor: 'pointer',
              }}
            >
              <Icon size={10} />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>
        {activeTab === 'library' && (
          <>
            {/* Category sidebar */}
            <div style={{
              width: 200, minWidth: 200, borderRight: `1px solid ${T.border}`,
              display: 'flex', flexDirection: 'column', overflow: 'auto',
              background: T.surface0, padding: '12px 0',
            }}>
              {/* Search */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: 6,
                margin: '0 10px 12px', padding: '6px 10px',
                background: T.surface2, border: `1px solid ${T.border}`, borderRadius: 6,
              }}>
                <Search size={12} color={T.dim} />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search blocks..."
                  style={{
                    flex: 1, background: 'none', border: 'none',
                    color: T.text, fontFamily: F, fontSize: FS.sm, outline: 'none',
                  }}
                />
              </div>

              {/* All */}
              <CategoryButton
                label="All Blocks"
                color={T.cyan}
                count={BLOCK_REGISTRY.length}
                active={categoryFilter === ''}
                onClick={() => setCategoryFilter('')}
              />

              {CATEGORY_ORDER.map(cat => {
                const blocks = getBlocksByCategory()[cat]
                if (!blocks) return null
                const color = CATEGORY_COLORS[cat] || T.dim
                return (
                  <CategoryButton
                    key={cat}
                    label={CATEGORY_LABELS[cat] || cat}
                    color={color}
                    count={blocks.length}
                    active={categoryFilter === cat}
                    onClick={() => setCategoryFilter(cat)}
                  />
                )
              })}
            </div>

            {/* Block grid */}
            <div style={{ flex: 1, overflow: 'auto', padding: 20 }}>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                gap: 12,
              }}>
                {filtered.map((block) => (
                  <BlockCard key={block.type} block={block} onClick={() => handleBlockClick(block)} />
                ))}
              </div>
              {filtered.length === 0 && (
                <div style={{ padding: 60, textAlign: 'center' }}>
                  <span style={{ fontFamily: F, fontSize: FS.md, color: T.dim }}>
                    No blocks match your search
                  </span>
                </div>
              )}
            </div>
          </>
        )}

        {/* Presets */}
        {activeTab === 'presets' && <PresetsTab />}

        {/* Recipes */}
        {activeTab === 'recipes' && (
          <div style={{ flex: 1, padding: 24, overflow: 'auto' }}>
            <div style={{ maxWidth: 900, margin: '0 auto' }}>
              <h3 style={{ fontFamily: FD, fontSize: FS.xl, color: T.text, marginBottom: 8 }}>Community Recipes</h3>
              <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, marginBottom: 24 }}>
                Pre-built, peer-reviewed pipeline definitions that you can instantly drop into your canvas.
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16 }}>
                {COMMUNITY_RECIPES.map(recipe => (
                  <PanelCard key={recipe.id} accent={T.cyan} onClick={() => handleRecipeClick(recipe)}>
                    <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <h4 style={{ fontFamily: FD, fontSize: FS.lg, color: T.text, margin: '0 0 6px 0' }}>{recipe.name}</h4>
                          <div style={{ display: 'flex', gap: 6 }}>
                            {recipe.tags.map(tag => (
                              <span key={tag} style={{
                                padding: '2px 8px', background: T.surface3, borderRadius: 12,
                                fontSize: FS.xxs, fontFamily: F, color: T.sec, border: `1px solid ${T.border}`
                              }}>{tag}</span>
                            ))}
                          </div>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            const idSuffix = '_' + Date.now()
                            const newNodes = recipe.nodes.map(n => ({ ...n, id: n.id + idSuffix }))
                            const newEdges = recipe.edges.map(e => ({
                              ...e, id: e.id + idSuffix,
                              source: e.source + idSuffix, target: e.target + idSuffix
                            }))
                            applyGeneratedWorkflow(newNodes, newEdges)
                            toast.success(`Installed recipe: ${recipe.name}`)
                          }}
                          className="hover-glow"
                          style={{
                            background: `${T.cyan}1A`, color: T.cyan, border: `1px solid ${T.cyan}50`,
                            padding: '6px 14px', borderRadius: 4, fontFamily: FD, fontSize: FS.sm,
                            fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase',
                            display: 'flex', alignItems: 'center', cursor: 'pointer', gap: 6,
                          }}
                        >
                          <PlusCircle size={14} /> Install to Canvas
                        </button>
                      </div>
                      <p style={{ fontFamily: F, fontSize: FS.sm, color: T.sec, margin: 0, lineHeight: 1.5 }}>
                        {recipe.description}
                      </p>
                      <div style={{ fontFamily: F, fontSize: FS.xs, color: T.dim, marginTop: 8 }}>
                        Includes: {recipe.nodes.map(n => n.data.label).join(' \u2192 ')}
                      </div>
                    </div>
                  </PanelCard>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Category sidebar button ──
function CategoryButton({ label, color, count, active, onClick }: {
  label: string; color: string; count: number; active: boolean; onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        width: '100%', padding: '8px 16px',
        background: active ? `${color}12` : 'transparent',
        border: 'none', borderLeft: active ? `3px solid ${color}` : '3px solid transparent',
        color: active ? T.text : T.sec,
        fontFamily: F, fontSize: FS.sm, fontWeight: active ? 700 : 500,
        cursor: 'pointer', textAlign: 'left',
        transition: 'all 0.15s',
      }}
    >
      <span style={{
        width: 8, height: 8, borderRadius: '50%',
        background: color, flexShrink: 0,
        boxShadow: active ? `0 0 8px ${color}` : 'none',
      }} />
      {label}
      <span style={{
        marginLeft: 'auto', fontFamily: F, fontSize: FS.xxs, color: T.dim,
        background: T.surface3, padding: '1px 6px', borderRadius: 4,
      }}>{count}</span>
    </button>
  )
}

// ── Block card ──
function BlockCard({ block, onClick }: { block: BlockDefinition; onClick: () => void }) {
  const IconComponent = getIcon(block.icon)
  const accent = block.accent || T.cyan
  const maturity = (block as any).maturity

  return (
    <PanelCard accent={accent} onClick={onClick}>
      <div style={{ padding: '14px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 36, height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: `${accent}14`, border: `1px solid ${accent}33`, borderRadius: 8,
          }}>
            <IconComponent size={18} color={accent} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontFamily: F, fontSize: FS.md, fontWeight: 700, color: T.text }}>
                {block.name}
              </span>
              {maturity && maturity !== 'stable' && (
                <span style={{
                  fontFamily: F, fontSize: '7px', fontWeight: 700, padding: '1px 5px',
                  borderRadius: 3, letterSpacing: '0.06em', textTransform: 'uppercase' as const,
                  ...(maturity === 'beta'
                    ? { color: '#F59E0B', background: '#F59E0B15', border: '1px solid #F59E0B30' }
                    : { color: '#8B5CF6', background: '#8B5CF615', border: '1px solid #8B5CF630' }),
                }}>
                  {maturity === 'beta' ? 'BETA' : 'EXP'}
                </span>
              )}
            </div>
            <div style={{
              fontFamily: F, fontSize: FS.xxs, color: accent,
              textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600,
            }}>
              {block.category}
            </div>
          </div>
        </div>

        {/* Description */}
        <p style={{
          fontFamily: F, fontSize: FS.sm, color: T.sec, margin: '8px 0',
          lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 3,
          WebkitBoxOrient: 'vertical', overflow: 'hidden',
        }}>
          {block.description}
        </p>

        {/* Port indicators + config count */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {block.inputs.map((p) => {
              const pc = getPortColor(p.dataType)
              return (
                <span key={`i-${p.id}`} title={`${p.label} (${p.dataType})`} style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: p.required ? pc : 'transparent',
                  border: p.required ? 'none' : `1.5px solid ${pc}`,
                  display: 'block',
                }} />
              )
            })}
            <ArrowRight size={8} color={T.dim} />
            {block.outputs.map((p) => {
              const pc = getPortColor(p.dataType)
              return (
                <span key={`o-${p.id}`} title={`${p.label} (${p.dataType})`} style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: p.required ? pc : 'transparent',
                  border: p.required ? 'none' : `1.5px solid ${pc}`,
                  display: 'block',
                }} />
              )
            })}
          </div>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
            {block.inputs.length} in / {block.outputs.length} out
          </span>
          <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginLeft: 'auto' }}>
            {block.configFields.length} params
          </span>
        </div>
      </div>
    </PanelCard>
  )
}

// ── Presets Tab ──
function PresetsTab() {
  const presets = usePresetStore((s) => s.presets)
  const { deletePreset, publishPreset, unpublishPreset } = usePresetStore()
  const [searchFilter, setSearchFilter] = useState('')

  const grouped = presets.reduce<Record<string, typeof presets>>((acc, p) => {
    if (!acc[p.blockType]) acc[p.blockType] = []
    acc[p.blockType].push(p)
    return acc
  }, {})

  const filteredTypes = Object.keys(grouped).filter(bt => {
    if (!searchFilter) return true
    const q = searchFilter.toLowerCase()
    return bt.toLowerCase().includes(q) || grouped[bt].some(p => p.name.toLowerCase().includes(q))
  })

  return (
    <div style={{ flex: 1, padding: 24, overflow: 'auto' }}>
      <div style={{ maxWidth: 900, margin: '0 auto' }}>
        <h3 style={{ fontFamily: FD, fontSize: FS.xl, color: T.text, marginBottom: 8 }}>Config Presets</h3>
        <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim, marginBottom: 16 }}>
          Saved block configurations that you can reuse across pipelines. Save presets from any block&apos;s config panel.
        </p>

        <input
          value={searchFilter}
          onChange={(e) => setSearchFilter(e.target.value)}
          placeholder="Search presets..."
          style={{
            width: '100%',
            padding: '8px 12px',
            background: T.surface3,
            border: `1px solid ${T.border}`,
            borderRadius: 4,
            color: T.text,
            fontFamily: F,
            fontSize: FS.sm,
            marginBottom: 20,
            outline: 'none',
          }}
        />

        {filteredTypes.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Bookmark size={32} color={T.dim} style={{ marginBottom: 12 }} />
            <p style={{ fontFamily: F, fontSize: FS.sm, color: T.dim }}>
              {presets.length === 0
                ? 'No presets saved yet. Select a block in the pipeline editor and save its config as a preset.'
                : 'No presets match your search.'}
            </p>
          </div>
        ) : (
          filteredTypes.map(blockType => {
            const blockDef = BLOCK_REGISTRY.find(b => b.type === blockType)
            const blockName = blockDef?.name || blockType
            const accent = blockDef?.accent || T.dim
            return (
              <div key={blockType} style={{ marginBottom: 20 }}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8,
                  padding: '6px 0', borderBottom: `1px solid ${T.border}`,
                }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: accent }} />
                  <span style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                    {blockName}
                  </span>
                  <span style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim }}>
                    ({grouped[blockType].length})
                  </span>
                </div>
                {grouped[blockType].map(preset => (
                  <div
                    key={preset.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '10px 12px',
                      background: T.surface2,
                      border: `1px solid ${T.border}`,
                      borderRadius: 6,
                      marginBottom: 6,
                    }}
                  >
                    <div style={{ flex: 1 }}>
                      <div style={{ fontFamily: F, fontSize: FS.sm, color: T.text, fontWeight: 600 }}>{preset.name}</div>
                      {preset.description && (
                        <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 2 }}>{preset.description}</div>
                      )}
                      <div style={{ fontFamily: F, fontSize: FS.xxs, color: T.dim, marginTop: 4 }}>
                        {Object.keys(preset.config).length} config fields &middot; {new Date(preset.createdAt).toLocaleDateString()}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button
                        onClick={() => preset.isPublished ? unpublishPreset(preset.id) : publishPreset(preset.id)}
                        style={{
                          padding: '4px 8px',
                          background: preset.isPublished ? `${T.green}20` : 'transparent',
                          border: `1px solid ${preset.isPublished ? T.green + '50' : T.border}`,
                          borderRadius: 4,
                          color: preset.isPublished ? T.green : T.dim,
                          fontFamily: F,
                          fontSize: FS.xxs,
                          cursor: 'pointer',
                        }}
                      >
                        {preset.isPublished ? 'PUBLISHED' : 'PUBLISH'}
                      </button>
                      <button
                        onClick={() => deletePreset(preset.id)}
                        style={{
                          padding: '4px 6px',
                          background: 'none',
                          border: `1px solid ${T.border}`,
                          borderRadius: 4,
                          color: T.dim,
                          cursor: 'pointer',
                        }}
                      >
                        <Trash2 size={10} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

